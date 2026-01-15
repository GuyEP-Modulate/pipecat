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
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from modulate.opus_clip_writer import OpusClipWriter
from modulate.processors.echo_raw_audio_input_to_output_processor import (
    EchoRawAudioInputToOutputProcessor,
)
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
    input_echo = EchoRawAudioInputToOutputProcessor()
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
