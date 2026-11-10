#!/bin/sh
# Launch the yt-dlp MCP server in an isolated rootless Podman container.
# Claude Code (or any MCP client) runs this as a stdio MCP server, one private
# container per client. With YTDLP_MCP_TRANSPORT=http it instead starts a single
# container that every client shares at http://127.0.0.1:8642/mcp; run it from
# systemd/ytdlp-mcp.service rather than from the MCP client.
# Pulls ghcr.io/manshaaazar/yt-dlp-mcp by default. To use a local build
# (podman build -t ytdlp-mcp .), set YTDLP_MCP_IMAGE=localhost/ytdlp-mcp:latest.
set -eu

IMAGE="${YTDLP_MCP_IMAGE:-ghcr.io/manshaaazar/yt-dlp-mcp:latest}"
VIDEO_DIR="${YTDLP_VIDEO_DIR:-$HOME/Videos}"
AUDIO_DIR="${YTDLP_AUDIO_DIR:-$HOME/Music}"
STATE_DIR="${YTDLP_MCP_DATA_DIR:-$HOME/.local/share/yt-dlp-mcp}"

mkdir -p "$VIDEO_DIR" "$AUDIO_DIR" "$STATE_DIR"

# With a proxy configured, let host.containers.internal (169.254.1.2, Podman's
# default) reach services bound to the host's loopback, such as a local SOCKS
# proxy. Without a proxy the container keeps the default, tighter mapping.
NETWORK=""
if [ -n "${YTDLP_PROXY:-}" ]; then
  NETWORK="--network pasta:--map-host-loopback,169.254.1.2"
fi

TRANSPORT="${YTDLP_MCP_TRANSPORT:-stdio}"
PORT="${YTDLP_MCP_PORT:-8642}"
if [ "$TRANSPORT" = "http" ]; then
  # One fixed name, so a second start replaces the container instead of adding
  # another. The port is published on the host's loopback only; inside the
  # container the server has to bind 0.0.0.0 to be reachable through it.
  # Whoever started this script (systemd) records its output, so Podman's own
  # log driver is off; otherwise every line is stored twice.
  MODE="--name ytdlp-mcp --replace --log-driver none -p 127.0.0.1:$PORT:$PORT -e YTDLP_MCP_HOST=0.0.0.0 -e YTDLP_MCP_PORT=$PORT"
else
  MODE="-i --name ytdlp-mcp-$$"
fi

# Host folders are mounted at the same path inside the container, so the
# saved-file paths the server reports are real paths on the host.
exec podman run --rm $MODE \
  --userns=keep-id \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 1g --pids-limit 256 \
  $NETWORK \
  -v "$VIDEO_DIR:$VIDEO_DIR" \
  -v "$AUDIO_DIR:$AUDIO_DIR" \
  -v "$STATE_DIR:$STATE_DIR" \
  -e YTDLP_VIDEO_DIR="$VIDEO_DIR" \
  -e YTDLP_AUDIO_DIR="$AUDIO_DIR" \
  -e YTDLP_MCP_DATA_DIR="$STATE_DIR" \
  -e YTDLP_MCP_LOG_LEVEL="${YTDLP_MCP_LOG_LEVEL:-INFO}" \
  -e YTDLP_MCP_TRANSPORT="$TRANSPORT" \
  -e YTDLP_PROXY="${YTDLP_PROXY:-}" \
  "$IMAGE"
