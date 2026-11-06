FROM docker.io/library/python:3.11-alpine
LABEL org.opencontainers.image.source="https://github.com/manshaaazar/yt-dlp-mcp" \
      org.opencontainers.image.licenses="MIT"

# ffmpeg: merging, MP3 conversion, clips. nodejs: JS runtime yt-dlp needs for YouTube.
RUN apk add --no-cache ffmpeg nodejs ca-certificates

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp/home

# Dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Output folders are bind-mounted from the host by run-podman.sh at the same
# paths, so the file paths the tools return are valid on the host.
ENTRYPOINT ["ytdlp-mcp"]
