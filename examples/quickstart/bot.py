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
"""
import os
from pathlib import Path

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
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.whisper.stt import WhisperSTTService, Model
from pipecat.transports.base_transport import BaseTransport, TransportParams

logger.info("✅ All components loaded successfully!")

load_dotenv(override=True)

AUDIO_FILE_DIRECTORY = Path(__file__).resolve().parent / "audio"

WAV_SAMPLE_PATH = str(AUDIO_FILE_DIRECTORY / "audacity_forum_theresa_martin_121724.wav")
MP3_SAMPLE_PATH = str(AUDIO_FILE_DIRECTORY / "bbc_6min_boredom_140821.mp3")

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
    input_echo = InputAudioEchoProcessor(suppress_interruptions=True)

    pipeline = Pipeline(
        [
            # rtc_transport.input(),  # RTC transport input.
            transport.input(),  # Transport user input
            frame_logger,
            rtvi,  # RTVI event stream processor.
            whisper_stt,
            input_echo,
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

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

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
