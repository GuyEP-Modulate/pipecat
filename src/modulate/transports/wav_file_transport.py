"""WAV file audio transport implementation for Pipecat.

This module reads audio from a WAV file for audio input.
"""

import asyncio
import wave
from datetime import timedelta
from typing import Optional

import numpy as np
from loguru import logger

from modulate.transports.null_output_transport import NullAudioOutputTransport
from pipecat.audio.utils import create_file_resampler
from pipecat.frames.frames import InputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams


class WavAudioTransportParams(TransportParams):
    """Configuration parameters for WAV audio transport.

    Parameters:
        wav_file_path: Path to the WAV file to read.
    """

    wav_file_path: str


class WavAudioInputTransport(BaseInputTransport):
    """WAV audio input transport.

    Reads samples from a WAV file and converts it to InputAudioRawFrame objects for processing in
    the pipeline.
    """

    _params: WavAudioTransportParams

    def __init__(self, params: WavAudioTransportParams):
        """Initialize the WAV audio input transport.

        Args:
            params: Transport configuration parameters.
        """
        super().__init__(params)
        self._resampler = create_file_resampler()

        self._in_stream: Optional[wave.Wave_read] = None
        self._sample_rate: int = 0
        self._receive_audio_task = None

    async def start(self, frame: StartFrame):
        """Start the audio input stream.

        Args:
            frame: The start frame containing initialization parameters.
        """
        await super().start(frame)

        if self._in_stream:
            return

        self._sample_rate = self._params.audio_in_sample_rate or frame.audio_in_sample_rate

        in_stream = wave.open(self._params.wav_file_path, "rb")

        if in_stream.getsampwidth() != 2:
            raise ValueError("Expected 16-bit PCM WAV (sampwidth=2)")

        self._in_stream = in_stream
        self._receive_audio_task = self.create_task(self._receive_audio())

        await self.set_transport_ready(frame)

    async def cleanup(self):
        """Stop and cleanup the audio input stream."""
        await super().cleanup()

        if self._in_stream:
            self._in_stream.close()
            self._in_stream = None

        if self._receive_audio_task:
            self._receive_audio_task.cancel()
            self._receive_audio_task = None

    async def _receive_audio(self):
        """Background task for receiving audio frames from WAV."""
        try:
            audio_iterator = self._read_audio_frame()

            async for audio_frame in audio_iterator:
                if audio_frame:
                    await self.push_audio_frame(audio_frame)

        except Exception as e:
            logger.error(f"{self} exception reading data: {e.__class__.__name__} ({e})")

    async def _read_audio_frame(self):
        """Read 20ms of audio frames from the WAV file and yield them as InputAudioRawFrame objects.

        Audio is resampled if needed using create_file_resampler().

        Yields:
            InputAudioRawFrame objects containing audio data from the WAV.
        """
        target_rate = self._sample_rate
        wav_rate = self._in_stream.getframerate()
        wav_channels = self._in_stream.getnchannels()

        # 20ms chunks at input rate
        chunk_ms = 20
        frames_per_chunk = int(wav_rate * chunk_ms / 100)

        while pcm_bytes := self._in_stream.readframes(frames_per_chunk):
            # If WAV is stereo, downmix to mono first.
            if wav_channels > 1:
                pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
                pcm = pcm.reshape(-1, wav_channels).mean(axis=1).astype(np.int16)
                pcm_bytes = pcm.tobytes()

            # Resample if needed
            if wav_rate != target_rate:
                pcm_bytes = await self._resampler.resample(
                    pcm_bytes,
                    in_rate=wav_rate,
                    out_rate=target_rate,
                )

            yield InputAudioRawFrame(
                audio=pcm_bytes,
                sample_rate=target_rate,
                num_channels=1,
            )

            # pace in real time
            await asyncio.sleep(timedelta(milliseconds=chunk_ms).total_seconds())


class WavAudioTransport(BaseTransport):
    """WAV audio transport with input capabilities.

    Provides an interface for reading audio from a WAV file for audio capture.
    """

    def __init__(self, params: WavAudioTransportParams):
        """Initialize the WAV audio transport.

        Args:
            params: Transport configuration parameters.
        """
        super().__init__()
        self._params = params

        self._input: Optional[WavAudioInputTransport] = None
        self._output: Optional[NullAudioOutputTransport] = None

    ############################################################################
    # BaseTransport Overrides
    ############################################################################
    def input(self) -> FrameProcessor:
        """Get the input frame processor for this transport.

        Returns:
            The audio input transport processor.
        """
        if not self._input:
            self._input = WavAudioInputTransport(self._params)

        return self._input

    def output(self) -> FrameProcessor:
        """Get the output frame processor for this transport.

        Returns:
            The audio output transport processor.
        """
        if not self._output:
            self._output = NullAudioOutputTransport(self._params)

        return self._output
