# yt-dlp MCP server

An MCP server that gives Claude (or any MCP client) the power of
[yt-dlp](https://github.com/yt-dlp/yt-dlp): download video and audio, read
transcripts, inspect videos, search YouTube, and sync whole playlists or channels.
It works with YouTube and the 1,800+ other sites yt-dlp supports.

Videos are saved as MP4 to your **Videos** folder. Audio is saved as MP3, with
cover art, title, artist and chapters embedded, to your **Music** folder.

## Tools

| Tool | What it does |
|------|--------------|
| `download_video` | One video as MP4, best quality by default. Optional `max_height` (e.g. 1080), `start`/`end` to save a clip, `remove_sponsors` (SponsorBlock). |
| `download_audio` | One video's audio (MP3 by default) with embedded cover art and metadata. Optional clip range, `split_chapters` (album uploads become separate tracks), `remove_sponsors`. |
| `get_transcript` | Timestamped transcript from real subtitles or auto-captions, without downloading the video. Paged for long videos (`offset` / `next_offset`). |
| `get_video_info` | Title, channel, length, upload date, chapters, available qualities, subtitle languages. |
| `search_youtube` | Search YouTube and get video URLs. |
| `list_playlist` | List a playlist's or channel's videos without downloading. |
| `download_playlist` | Download a playlist or channel into a subfolder named after it. A download archive skips items you already have, so re-running it syncs only new uploads. Supports `limit` and `after_date`. |
| `check_downloads` | Progress and results of background downloads. |
| `cancel_download` | Cancel a background download. |

Every download runs as a background job. The tool waits up to 50 seconds; short
downloads return the saved file path directly, longer ones return a `job_id` to
check with `check_downloads`. Two downloads run at a time; more are queued.

A link to a video inside a playlist downloads only that video. Links to whole
playlists or channels are refused by the single-video tools; use
`download_playlist` for those.

## Requirements

- Windows, macOS or Linux with Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- **ffmpeg** for merging best-quality video, MP3 conversion, clips, SponsorBlock and
  chapter splitting. On Windows: `winget install Gyan.FFmpeg`. The server also
  finds ffmpeg in winget's install folders even when your PATH has not refreshed.
- **Node.js** (or Deno). YouTube now requires a JavaScript runtime for yt-dlp to
  solve its player challenges. The server passes the Node it finds on PATH.

## Install

```powershell
cd yt-dlp-mcp
uv sync
```

Register it with Claude Code for all projects:

```powershell
claude mcp add --scope user yt-dlp -- "C:\path\to\yt-dlp-mcp\.venv\Scripts\ytdlp-mcp.exe"
claude mcp list
```

For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yt-dlp": {
      "command": "C:\\path\\to\\yt-dlp-mcp\\.venv\\Scripts\\ytdlp-mcp.exe"
    }
  }
}
```

### Linux (isolated, with rootless Podman)

Runs the server in a throwaway container, so ffmpeg, Node and Python stay off
the host. Only `~/Videos`, `~/Music` and `~/.local/share/yt-dlp-mcp` are
mounted, at the same paths inside the container, so the file paths the tools
return are valid on the host and files are owned by your user.

```bash
sudo apt install -y podman
cd yt-dlp-mcp
podman build -t ytdlp-mcp .
claude mcp add --scope user yt-dlp -- "$PWD/run-podman.sh"
```

Rebuild the image (`podman build -t ytdlp-mcp .`) to pick up code or yt-dlp updates.

### Linux (directly on the host)

```bash
sudo apt install -y ffmpeg nodejs
uv sync
claude mcp add --scope user yt-dlp -- "$PWD/.venv/bin/ytdlp-mcp"
```

## Configuration

All settings are optional environment variables.

| Variable | Default | Purpose |
|----------|---------|---------|
| `YTDLP_VIDEO_DIR` | `~/Videos` | Where videos are saved |
| `YTDLP_AUDIO_DIR` | `~/Music` | Where audio is saved |
| `YTDLP_MCP_DATA_DIR` | `%LOCALAPPDATA%\yt-dlp-mcp` on Windows, `$XDG_DATA_HOME/yt-dlp-mcp` (default `~/.local/share/yt-dlp-mcp`) elsewhere | Holds `archive.txt`, the record of playlist items already downloaded |
| `YTDLP_FFMPEG` | auto-detected | Full path to the ffmpeg executable |
| `YTDLP_NODE` | `node` on PATH | Full path to the Node.js executable |
| `YTDLP_MCP_WAIT_SECONDS` | `50` | How long a download tool waits before returning a `job_id` |
| `YTDLP_MCP_LOG_LEVEL` | `INFO` | Log level; logs go to stderr |

The server ignores your personal `yt-dlp.conf` so results stay predictable.

To download a playlist item again after deleting it, remove its line from
`archive.txt`. Single-video downloads never use the archive.

## Keeping yt-dlp current

YouTube changes often, and yt-dlp releases fixes quickly. When downloads start
failing, update:

```powershell
uv lock --upgrade-package yt-dlp
uv sync
```

Then restart your MCP client.

## Tests

```powershell
uv run pytest                 # everything, including live downloads (needs network + ffmpeg)
uv run pytest -m "not live"   # offline unit tests only
```

`tests/test_stdio.py` launches the real server over stdio, the way an MCP client
does, which catches any stray output that would corrupt the protocol stream.

## Notes

Respect the terms of service of the sites you download from, and only download
content you have the right to save.
