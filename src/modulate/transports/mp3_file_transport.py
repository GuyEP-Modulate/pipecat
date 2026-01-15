"""
MP3 file audio transport implementation for Pipecat.

This module reads audio from an MP3 file for audio input.
"""

import asyncio
from datetime import timedelta
from typing import Optional

from loguru import logger
from pydub import AudioSegment

from modulate.transports.null_output_transport import NullAudioOutputTransport
from pipecat.frames.frames import InputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams


class Mp3AudioTransportParams(TransportParams):
    """Configuration parameters for MP3 audio transport.

    Parameters:
        mp3_file_path: Path to the MP3 file to read.
    """

    mp3_file_path: str


class Mp3AudioInputTransport(BaseInputTransport):
    """MP3 audio input transport.

    Decodes audio from an MP3 file and converts it to InputAudioRawFrame objects for processing in
    the pipeline.
    """

    _params: Mp3AudioTransportParams

    def __init__(self, params: Mp3AudioTransportParams):
        super().__init__(params)

        self._sample_rate: int = 0
        self._receive_audio_task = None

        # Decoded PCM16 mono bytes, filled at start()
        self._pcm_bytes: Optional[bytes] = None
        self._cursor: int = 0

    async def start(self, frame: StartFrame):
        """Start the audio input stream.

        Args:
            frame: The start frame containing initialization parameters.
        """
        await super().start(frame)

        if self._receive_audio_task:
            return

        self._sample_rate = self._params.audio_in_sample_rate or frame.audio_in_sample_rate

        # Decode MP3 -> PCM16 mono at target sample rate
        # NOTE: pydub uses ffmpeg under the hood for MP3 decoding.
        logger.info(
            f"{self} decoding MP3 '{self._params.mp3_file_path}' "
            f"to {self._sample_rate} Hz mono PCM16"
        )

        audio = (
            AudioSegment
                .from_mp3(self._params.mp3_file_path)
                .set_frame_rate(self._sample_rate)
                .set_channels(1)
                .set_sample_width(2)  # PCM16
        )

        self._pcm_bytes = audio.raw_data
        self._cursor = 0

        self._receive_audio_task = self.create_task(self._receive_audio())
        await self.set_transport_ready(frame)

    async def cleanup(self):
        """Stop and cleanup the audio input stream."""
        await super().cleanup()
        self._pcm_bytes = None
        self._cursor = 0
        self._receive_audio_task = None

    async def _receive_audio(self):
        """Background task for receiving audio frames from MP3."""
        try:
            audio_iterator = self._read_audio_frame()

            async for audio_frame in audio_iterator:
                if audio_frame:
                    await self.push_audio_frame(audio_frame)

        except Exception as e:
            logger.error(f"{self} exception reading data: {e.__class__.__name__} ({e})")

    async def _read_audio_frame(self):
        """Yield 20ms InputAudioRawFrame chunks from the decoded MP3."""

        if self._pcm_bytes is None:
            return

        chunk_ms = 20
        # frames per chunk @ target sample rate
        frames_per_chunk = int(self._sample_rate * chunk_ms / 1000)
        # PCM16 mono => 2 bytes per frame
        bytes_per_chunk = frames_per_chunk * 2

        while self._cursor < len(self._pcm_bytes):
            chunk = self._pcm_bytes[self._cursor : self._cursor + bytes_per_chunk]
            self._cursor += len(chunk)

            # If we got a partial final chunk, we can either:
            # - send it as-is (fine), or
            # - pad with zeros to full chunk (sometimes helps VAD consistency)
            if len(chunk) < bytes_per_chunk:
                chunk += b"\x00" * (bytes_per_chunk - len(chunk))

            yield InputAudioRawFrame(
                audio=chunk,
                sample_rate=self._sample_rate,
                num_channels=1,
            )

            # pace in real time
            await asyncio.sleep(timedelta(milliseconds=chunk_ms).total_seconds())


class Mp3AudioTransport(BaseTransport):
    """MP3 audio transport with input capabilities.

    Provides an interface for reading audio from an MP3 file for audio capture.
    """

    def __init__(self, params: Mp3AudioTransportParams):
        super().__init__()
        self._params = params

        self._input: Optional[Mp3AudioInputTransport] = None
        self._output: Optional[NullAudioOutputTransport] = None

    ############################################################################
    # BaseTransport Overrides
    ############################################################################
    def input(self) -> FrameProcessor:
        if not self._input:
            self._input = Mp3AudioInputTransport(self._params)
        return self._input

    def output(self) -> FrameProcessor:
        if not self._output:
            self._output = NullAudioOutputTransport(self._params)
        return self._output
