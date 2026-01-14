#!/usr/bin/env bash

docker run -p7860:7860 --env-file .env -it localhost/modulate/mpa-pipecat:latest python /app/bot.py --host=0.0.0.0
