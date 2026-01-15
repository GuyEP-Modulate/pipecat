#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Quickstart Example.

The example runs a simple voice AI bot that you can connect to using your
browser and speak with it. You can also deploy this bot to Pipecat Cloud.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py

This quickstart records 5-second Opus clips into examples/quickstart/recordings.
Opus encoding requires the `webrtc` extra (PyAV via aiortc).
"""
import asyncio
import datetime
import itertools
from pathlib import Path

import av
from dotenv import load_dotenv
from loguru import logger
from modulate.processors.input_audio_echo import InputAudioEchoProcessor
from modulate.transports.mp3_file_transport import Mp3AudioTransport, Mp3AudioTransportParams
from modulate.transports.wav_file_transport import WavAudioTransport, WavAudioTransportParams
from pipecat.processors.logger import FrameLogger

print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (20 seconds, first run only)\n")

logger.info("Loading Local Smart Turn Analyzer V3...")
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

logger.info("✅ Local Smart Turn Analyzer V3 loaded")
logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer

logger.info("✅ Silero VAD model loaded")

from pipecat.audio.vad.vad_analyzer import VADParams

logger.info("Loading pipeline components...")
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.whisper.stt import Model, WhisperSTTService
from pipecat.transports.base_transport import BaseTransport, TransportParams

logger.info("✅ All components loaded successfully!")

load_dotenv(override=True)

AUDIO_FILE_DIRECTORY = Path(__file__).resolve().parent / "audio"

WAV_SAMPLE_PATH = str(AUDIO_FILE_DIRECTORY / "audacity_forum_theresa_martin_121724.wav")
MP3_SAMPLE_PATH = str(AUDIO_FILE_DIRECTORY / "bbc_6min_boredom_140821.mp3")

OPUS_RECORDINGS_DIR = Path(__file__).resolve().parent / "recordings"
OPUS_CLIP_SECONDS = 5
OPUS_SAMPLE_RATE = 48_000
OPUS_CHANNELS = 1
OPUS_FRAME_MS = 20


def encode_opus_clip(audio: bytes, sample_rate: int, num_channels: int, filename: Path) -> None:
    if num_channels not in (1, 2):
        raise ValueError(f"Unsupported channel count for Opus: {num_channels}")

    container = av.open(str(filename), mode="w", format="ogg")
    stream = container.add_stream("libopus", rate=sample_rate)
    stream.layout = "mono" if num_channels == 1 else "stereo"

    samples_per_frame = max(1, int(sample_rate * OPUS_FRAME_MS / 1000))
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


class OpusClipWriter:
    def __init__(self, recordings_dir: Path, clip_seconds: int):
        self._recordings_dir = recordings_dir
        self._clip_seconds = clip_seconds
        self._pending = bytearray()
        self._clip_index = itertools.count(1)

    def _bytes_per_clip(self, sample_rate: int, num_channels: int) -> int:
        return int(sample_rate * num_channels * 2 * self._clip_seconds)

    async def append_audio(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        if not audio:
            return

        self._pending.extend(audio)
        bytes_per_clip = self._bytes_per_clip(sample_rate, num_channels)

        while len(self._pending) >= bytes_per_clip:
            clip_audio = bytes(self._pending[:bytes_per_clip])
            del self._pending[:bytes_per_clip]
            await self._write_clip(clip_audio, sample_rate, num_channels)

    async def finalize(self, sample_rate: int, num_channels: int) -> None:
        if not self._pending:
            return

        bytes_per_clip = self._bytes_per_clip(sample_rate, num_channels)
        clip_audio = bytes(self._pending).ljust(bytes_per_clip, b"\x00")
        self._pending = bytearray()
        await self._write_clip(clip_audio, sample_rate, num_channels)

    async def _write_clip(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_index = next(self._clip_index)
        filename = self._recordings_dir / f"clip_{timestamp}_{clip_index:04d}.opus"
        await asyncio.to_thread(encode_opus_clip, audio, sample_rate, num_channels, filename)
        logger.info(f"Saved Opus clip to {filename}")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    whisper_stt = WhisperSTTService(model=Model.LARGE_V3_TURBO)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    frame_logger = FrameLogger("Transcription In")

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_out_enabled=True,
        ),
    }

    rtc_transport = await create_transport(runner_args, transport_params)

    opus_recorder = OpusClipWriter(OPUS_RECORDINGS_DIR, OPUS_CLIP_SECONDS)
    audio_buffer = AudioBufferProcessor(
        sample_rate=OPUS_SAMPLE_RATE,
        num_channels=OPUS_CHANNELS,
        buffer_size=int(OPUS_SAMPLE_RATE * OPUS_CHANNELS * 2 * OPUS_CLIP_SECONDS),
    )
    input_echo = InputAudioEchoProcessor(suppress_interruptions=True)
    last_audio_format = {"sample_rate": OPUS_SAMPLE_RATE, "num_channels": OPUS_CHANNELS}

    pipeline = Pipeline(
        [
            # rtc_transport.input(),  # RTC transport input.
            transport.input(),  # Transport user input
            rtvi,  # RTVI event stream processor.
            frame_logger,
            ParallelPipeline(
                [
                    whisper_stt,
                ],
                [
                    audio_buffer,
                    input_echo,
                ],
            ),
            # transport.output()
            rtc_transport.output(),  # Transport output.
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @rtc_transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("WebRTC client connected")
        await audio_buffer.start_recording()

    @rtc_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("WebRTC client disconnected")
        await audio_buffer.stop_recording()
        await opus_recorder.finalize(
            last_audio_format["sample_rate"],
            last_audio_format["num_channels"],
        )
        await task.cancel()

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        last_audio_format["sample_rate"] = sample_rate
        last_audio_format["num_channels"] = num_channels
        await opus_recorder.append_audio(audio, sample_rate, num_channels)

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(task, frame):
        await audio_buffer.stop_recording()
        await opus_recorder.finalize(
            last_audio_format["sample_rate"],
            last_audio_format["num_channels"],
        )

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the bot starter."""

    # transport_params = {
    #     "webrtc": lambda: TransportParams(
    #         audio_in_enabled=True,
    #         audio_out_enabled=True,
    #         vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
    #         turn_analyzer=LocalSmartTurnAnalyzerV3(),
    #     ),
    # }
    #
    # transport = await create_transport(runner_args, transport_params)
    wav_transport = WavAudioTransport(
        WavAudioTransportParams(
            audio_in_enabled=True,
            wav_file_path=WAV_SAMPLE_PATH,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
        )
    )
    mp3_transport = Mp3AudioTransport(
        Mp3AudioTransportParams(
            audio_in_enabled=True,
            mp3_file_path=MP3_SAMPLE_PATH,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
        )
    )

    await run_bot(mp3_transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
