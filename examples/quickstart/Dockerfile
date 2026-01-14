FROM dailyco/pipecat-base:latest

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Copy quickstart metadata first (cache-friendly)
COPY examples/quickstart/pyproject.toml examples/quickstart/uv.lock ./

# Copy sample audio
COPY examples/quickstart/audio/ ./audio

# Copy the editable dependency *under* the project directory
COPY ../../ ./pipecat-ai

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY examples/quickstart/bot.py ./bot.py

# Install ffmpeg for Pydub
RUN set -eux; \
    apt-get update; \
    apt-get install --yes \
      ffmpeg \
    ; \
    rm -rf /var/lib/apt/lists/*; \
    apt-get purge -y --auto-remove; \
    apt-get autoremove; \
    apt-get clean
