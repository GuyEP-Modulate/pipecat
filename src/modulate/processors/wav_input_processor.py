import asyncio, wave
from typing import cast

from loguru import logger

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import InputAudioRawFrame, UserStartedSpeakingFrame, \
    UserStoppedSpeakingFrame, StartFrame, VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport

class WavInputProcessor(FrameProcessor):
    def __init__(self, transport: BaseTransport, wav_path: str, chunk_ms: int = 20):
        super().__init__()
        self.transport = transport
        self.wav_path = wav_path
        self.chunk_ms = chunk_ms
        self._started = False

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)  # forward everything

        # Start emitting once we see the pipeline StartFrame (or any trigger you prefer)
        if not self._started and isinstance(frame, StartFrame):
            logger.debug("[WavInputProcessor] Starting.")
            self._started = True
            asyncio.create_task(self._stream_wav())

    async def _stream_wav(self):
        with wave.open(self.wav_path, "rb") as wave_file:
            sample_rate = wave_file.getframerate()
            channel_count = wave_file.getnchannels()
            sample_width = wave_file.getsampwidth()

            if sample_width != 2:
                raise ValueError("Expected 16-bit PCM WAV (sampwidth=2)")

            frames_per_chunk = int(sample_rate * (self.chunk_ms / 1000.0))

            frame_index = 0

            while True:
                audio_frames = wave_file.readframes(frames_per_chunk)  # bytes

                if not audio_frames:
                    break

                audio_frame = InputAudioRawFrame(
                    audio=audio_frames,
                    sample_rate=sample_rate,
                    num_channels=channel_count,
                )

                frame_index += 1

                logger.debug(f"[WavInputProcessor] Pushing frame '{frame_index}'.")
                #await cast(BaseInputTransport, self.transport.input()).push_audio_frame(audio_frame)
                await self.push_frame(audio_frame, FrameDirection.DOWNSTREAM)

                # pace in real time
                await asyncio.sleep(self.chunk_ms / 1000.0)

