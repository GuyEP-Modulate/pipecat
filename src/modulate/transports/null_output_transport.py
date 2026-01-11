"""Dummy (NULL) audio output transport implementation for Pipecat.

This module provides a do-nothing audio output implementation.
"""

from typing import Optional

import numpy as np
from loguru import logger

from pipecat.frames.frames import StartFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams


class NullAudioOutputTransport(BaseOutputTransport):
    """Dummy audio output transport.

    Performs no audio output.
    """

    _params: TransportParams

    def __init__(self, params: TransportParams):
        """Initialize the dummy audio output transport.

        Args:
            params: Transport configuration parameters.
        """
        super().__init__(params)

    async def start(self, frame: StartFrame):
        """Start the audio output stream.

        Args:
            frame: The start frame containing initialization parameters.
        """
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def cleanup(self):
        """Stop and cleanup the audio output stream."""
        await super().cleanup()

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        """Write an audio frame to the output stream.

        Args:
            frame: The audio frame to write to the output device.

        Returns:
            True, always (this is a sink).
        """
        return True