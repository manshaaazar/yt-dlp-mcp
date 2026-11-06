#!/bin/sh
# Launch the yt-dlp MCP server in an isolated Docker container.
# Claude Code (or any MCP client) runs this as a stdio MCP server.
# Linux and macOS (Docker Desktop). Pulls ghcr.io/manshaaazar/yt-dlp-mcp.
set -eu

IMAGE="${YTDLP_MCP_IMAGE:-ghcr.io/manshaaazar/yt-dlp-mcp:latest}"
VIDEO_DIR="${YTDLP_VIDEO_DIR:-$HOME/Videos}"
AUDIO_DIR="${YTDLP_AUDIO_DIR:-$HOME/Music}"
STATE_DIR="${YTDLP_MCP_DATA_DIR:-$HOME/.local/share/yt-dlp-mcp}"

mkdir -p "$VIDEO_DIR" "$AUDIO_DIR" "$STATE_DIR"

# Host folders are mounted at the same path inside the container, so the
# saved-file paths the server reports are real paths on the host. The container
# runs as your user so the files are owned by you.
exec docker run -i --rm --name "ytdlp-mcp-$$" \
  --user "$(id -u):$(id -g)" \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 1g --pids-limit 256 \
  -v "$VIDEO_DIR:$VIDEO_DIR" \
  -v "$AUDIO_DIR:$AUDIO_DIR" \
  -v "$STATE_DIR:$STATE_DIR" \
  -e YTDLP_VIDEO_DIR="$VIDEO_DIR" \
  -e YTDLP_AUDIO_DIR="$AUDIO_DIR" \
  -e YTDLP_MCP_DATA_DIR="$STATE_DIR" \
  -e YTDLP_MCP_LOG_LEVEL="${YTDLP_MCP_LOG_LEVEL:-INFO}" \
  "$IMAGE"
