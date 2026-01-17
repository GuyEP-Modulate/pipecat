"""Implementation of BaseOpusClipWriter."""

from abc import ABC
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, Union

import av


class BaseOpusClipWriter(ABC):
    """Base class for utility objects that write audio out to fixed-length Opus-encoded audio files.

    Audio is buffered internally as PCM16 audio in 20 msec frames, but the length of each Opus audio clip is
    configurable. Each writer buffers raw audio and then writes full clips once enough data arrives. The final clip is
    padded on to ensure every file is a consistent length.
    """
    _OPUS_FRAME_MS = 20

    def __init__(self, clip_length: timedelta) -> None:
        """Create a writer for fixed-length Opus clips.

        Args:
            clip_length: Duration of each clip.
        """
        self._clip_length = clip_length
        self._buffered_audio = bytearray()

    async def append_audio(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        """Append PCM16 audio and write any full clips that are ready."""
        if not audio:
            return

        self._buffered_audio.extend(audio)
        bytes_per_clip = self._calculate_bytes_per_clip(sample_rate, num_channels)

        while len(self._buffered_audio) >= bytes_per_clip:
            clip_audio = bytes(self._buffered_audio[:bytes_per_clip])
            del self._buffered_audio[:bytes_per_clip]
            await self._write_clip(clip_audio, sample_rate, num_channels)

    async def finalize(self, sample_rate: int, num_channels: int) -> None:
        """Flush remaining audio, padding to a full clip length."""
        if not self._buffered_audio:
            return

        bytes_per_clip = self._calculate_bytes_per_clip(sample_rate, num_channels)
        clip_audio = bytes(self._buffered_audio).ljust(bytes_per_clip, b"\x00")
        self._buffered_audio = bytearray()
        await self._write_clip(clip_audio, sample_rate, num_channels)

    def _calculate_bytes_per_clip(self, sample_rate: int, num_channels: int) -> int:
        return int(sample_rate * num_channels * 2 * self._clip_length.total_seconds())

    async def _write_clip(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        """Write out a single Opus clip to disk."""
        pass

    @classmethod
    def _encode_opus_clip(
        cls, audio: bytes, sample_rate: int, num_channels: int, output: Union[Path, str, BinaryIO]
    ) -> None:
        """Encode PCM16 audio into an Opus audio file.

        Args:
            audio: The PCM16 audio bytes to write out.
            sample_rate: The sampling frequency of the audio.
            num_channels: The number of distinct audio channels.
            output: The destination path (as either a Path or str) or binary stream to which to write the encoded data.
        """
        if num_channels not in (1, 2):
            raise ValueError(f"Unsupported channel count for Opus: {num_channels}")

        container_target = str(output) if isinstance(output, Path) else output
        container = av.open(container_target, mode="w", format="opus")
        stream = container.add_stream("libopus", rate=sample_rate)
        layout = "mono" if num_channels == 1 else "stereo"
        stream.layout = layout

        samples_per_frame = max(1, int(sample_rate * cls._OPUS_FRAME_MS / 1000))
        bytes_per_frame = samples_per_frame * num_channels * 2

        for offset in range(0, len(audio), bytes_per_frame):
            chunk = audio[offset : offset + bytes_per_frame]

            if len(chunk) < bytes_per_frame:
                chunk += b"\x00" * (bytes_per_frame - len(chunk))

            frame = av.AudioFrame(format="s16", layout=layout, samples=samples_per_frame)
            frame.sample_rate = sample_rate
            frame.planes[0].update(chunk)

            for packet in stream.encode(frame):
                container.mux(packet)

        for packet in stream.encode(None):
            container.mux(packet)

        container.close()
