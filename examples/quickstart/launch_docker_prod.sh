#!/usr/bin/env bash

docker run -p8080:8080 --env-file .env -it localhost/modulate/mpa-pipecat:latest
