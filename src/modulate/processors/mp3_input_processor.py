import asyncio
from pydub import AudioSegment
from loguru import logger

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import InputAudioRawFrame, EndFrame, UserStartedSpeakingFrame, \
    UserStoppedSpeakingFrame


class Mp3InputProcessor(FrameProcessor):
    def __init__(self, mp3_path: str, sample_rate=16000, chunk_ms=20):
        super().__init__()
        self.mp3_path = mp3_path
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self._started = False

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

        # Start emitting once we see the pipeline StartFrame (or any trigger you prefer)
        if not self._started and isinstance(frame, StartFrame):
            logger.debug("[Mp3InputProcessor] Starting.")
            self._started = True
            asyncio.create_task(self._stream_mp3())

    async def _stream_mp3(self):
        audio = (
            AudioSegment.from_mp3(self.mp3_path)
            .set_frame_rate(self.sample_rate)
            .set_channels(1)
            .set_sample_width(2)  # PCM16
        )

        chunk_size = int(self.sample_rate * self.chunk_ms / 1000) * 2

        raw = audio.raw_data

        await self.push_frame(UserStartedSpeakingFrame(emulated=True), FrameDirection.DOWNSTREAM)

        for i in range(0, len(raw), chunk_size):
            chunk = raw[i:i + chunk_size]

            frame = InputAudioRawFrame(
                audio=chunk,
                sample_rate=self.sample_rate,
                num_channels=1,
            )

            logger.debug(f"[Mp3InputProcessor] Pushing frame '{i}'.")
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)
            await asyncio.sleep(self.chunk_ms / 1000)

        await self.push_frame(UserStoppedSpeakingFrame(emulated=True),
                              FrameDirection.DOWNSTREAM)
