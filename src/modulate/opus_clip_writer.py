"""Utility object for writing fixed-duration Opus audio clips."""

import asyncio
import datetime
import itertools
from pathlib import Path

import av
from loguru import logger


class OpusClipWriter:
    """Accumulates PCM16 audio and emits fixed-duration Opus clips.

    The writer buffers raw audio, writes full clips once enough data arrives, and pads the final clip on finalize so
    every file is a consistent length.
    """
    _OPUS_FRAME_MS = 20

    def __init__(self, recordings_dir: Path, clip_seconds: int):
        """Create a writer for fixed-length Opus clips.

        Args:
            recordings_dir: Output directory for saved .opus files.
            clip_seconds: Duration of each clip in seconds.
        """
        self._recordings_dir = recordings_dir
        self._clip_seconds = clip_seconds
        self._pending = bytearray()
        self._clip_index = itertools.count(1)

    async def append_audio(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        """Append PCM16 audio and write any full clips that are ready."""
        if not audio:
            return

        self._pending.extend(audio)
        bytes_per_clip = self._calculate_bytes_per_clip(sample_rate, num_channels)

        while len(self._pending) >= bytes_per_clip:
            clip_audio = bytes(self._pending[:bytes_per_clip])
            del self._pending[:bytes_per_clip]
            await self._write_clip(clip_audio, sample_rate, num_channels)

    async def finalize(self, sample_rate: int, num_channels: int) -> None:
        """Flush remaining audio, padding to a full clip length."""
        if not self._pending:
            return

        bytes_per_clip = self._calculate_bytes_per_clip(sample_rate, num_channels)
        clip_audio = bytes(self._pending).ljust(bytes_per_clip, b"\x00")
        self._pending = bytearray()
        await self._write_clip(clip_audio, sample_rate, num_channels)

    def _calculate_bytes_per_clip(self, sample_rate: int, num_channels: int) -> int:
        return int(sample_rate * num_channels * 2 * self._clip_seconds)

    async def _write_clip(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        """Write a single Opus clip to disk."""
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_index = next(self._clip_index)
        filename = self._recordings_dir / f"clip_{timestamp}_{clip_index:04d}.opus"
        await asyncio.to_thread(self._encode_opus_clip, audio, sample_rate, num_channels, filename)
        logger.info(f"Saved Opus clip to {filename}")

    @classmethod
    def _encode_opus_clip(cls, audio: bytes, sample_rate: int, num_channels: int, filename: Path) -> None:
        """Encode PCM16 audio into an Opus-in-Ogg file."""
        if num_channels not in (1, 2):
            raise ValueError(f"Unsupported channel count for Opus: {num_channels}")

        container = av.open(str(filename), mode="w", format="ogg")
        stream = container.add_stream("libopus", rate=sample_rate)
        stream.layout = "mono" if num_channels == 1 else "stereo"

        samples_per_frame = max(1, int(sample_rate * cls._OPUS_FRAME_MS / 1000))
        bytes_per_frame = samples_per_frame * num_channels * 2

        for offset in range(0, len(audio), bytes_per_frame):
            chunk = audio[offset : offset + bytes_per_frame]

            if len(chunk) < bytes_per_frame:
                chunk += b"\x00" * (bytes_per_frame - len(chunk))

            frame = av.AudioFrame(format="s16", layout=stream.layout, samples=samples_per_frame)
            frame.sample_rate = sample_rate
            frame.planes[0].update(chunk)

            for packet in stream.encode(frame):
                container.mux(packet)

        for packet in stream.encode(None):
            container.mux(packet)

        container.close()
