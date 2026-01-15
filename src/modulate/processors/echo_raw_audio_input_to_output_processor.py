"""Echo input audio to the output transport for debugging."""

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class EchoRawAudioInputToOutputProcessor(FrameProcessor):
    """Copies input audio to bot output for debugging."""

    async def process_frame(self, frame, direction: FrameDirection):
        """Process a frame, copying raw audio input to raw audio output.

        Args:
            frame: The frame to process.
            direction: The direction the frame is moving through the pipeline.
        """
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
