#!/bin/sh
# Launch the yt-dlp MCP server in an isolated rootless Podman container.
# Claude Code runs this as a stdio MCP server.
set -eu

VIDEO_DIR="${YTDLP_VIDEO_DIR:-$HOME/Videos}"
AUDIO_DIR="${YTDLP_AUDIO_DIR:-$HOME/Music}"
STATE_DIR="${YTDLP_MCP_DATA_DIR:-$HOME/.local/share/yt-dlp-mcp}"

mkdir -p "$VIDEO_DIR" "$AUDIO_DIR" "$STATE_DIR"

# Host folders are mounted at the same path inside the container, so the
# saved-file paths the server reports are real paths on the host.
exec podman run -i --rm --name "ytdlp-mcp-$$" \
  --userns=keep-id \
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
  localhost/ytdlp-mcp:latest
