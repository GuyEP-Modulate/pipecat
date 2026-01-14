"""Echo input audio to the output transport for debugging."""

from pipecat.frames.frames import InputAudioRawFrame, InterruptionFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class InputAudioEchoProcessor(FrameProcessor):
    """Copies input audio to output and optionally suppresses interruptions."""

    def __init__(self, *, suppress_interruptions: bool = True, **kwargs):
        super().__init__(**kwargs)
        self._suppress_interruptions = suppress_interruptions

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
            echo_frame = OutputAudioRawFrame(
                audio=frame.audio,
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
            )
            echo_frame.transport_destination = frame.transport_destination
            await self.push_frame(echo_frame, FrameDirection.DOWNSTREAM)
            await self.push_frame(frame, direction)
            return

        if (
            self._suppress_interruptions
            and isinstance(frame, InterruptionFrame)
            and direction == FrameDirection.DOWNSTREAM
        ):
            return

        await self.push_frame(frame, direction)
