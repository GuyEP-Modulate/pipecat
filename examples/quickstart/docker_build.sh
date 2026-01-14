#!/usr/bin/env bash

# Builds a Pipecat Docker image from this folder, passing the entire Pipecat folder as context.
podman build -t modulate/mpa-pipecat:latest -f Dockerfile ../..
