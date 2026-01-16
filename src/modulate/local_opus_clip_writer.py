"""Implementation of LocalOpusClipWriter."""

import asyncio
import datetime
import itertools
from datetime import timedelta
from pathlib import Path

from loguru import logger

from modulate.base_opus_clip_writer import BaseOpusClipWriter


class LocalOpusClipWriter(BaseOpusClipWriter):
    """An Opus Clip Writer that saves clips to the local filesystem."""

    def __init__(self, recordings_dir: Path, clip_length: timedelta):
        """Create a writer for fixed-length Opus clips.

        Args:
            recordings_dir: Output directory for saved .opus files.
            clip_length: Duration of each clip.
        """
        super().__init__(clip_length)

        self._recordings_dir = recordings_dir

        self._start_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._clip_index = itertools.count(1)

    async def _write_clip(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        """Write a single Opus clip to disk."""
        self._recordings_dir.mkdir(parents=True, exist_ok=True)

        clip_index = next(self._clip_index)
        filename = self._recordings_dir / f"clip_{self._start_time}_{clip_index:04d}.opus"

        await asyncio.to_thread(self._encode_opus_clip, audio, sample_rate, num_channels, filename)

        logger.info(f"Saved Opus clip to '{filename}'.")
