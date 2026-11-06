# yt-dlp MCP Server for YouTube: download videos, audio, transcripts and playlists with Claude

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-black.svg)](https://modelcontextprotocol.io/)
[![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![Container image](https://img.shields.io/badge/ghcr.io-yt--dlp--mcp-blue?logo=docker)](https://github.com/manshaaazar/yt-dlp-mcp/pkgs/container/yt-dlp-mcp)
[![Build](https://github.com/manshaaazar/yt-dlp-mcp/actions/workflows/container.yml/badge.svg)](https://github.com/manshaaazar/yt-dlp-mcp/actions/workflows/container.yml)

A **YouTube MCP server** built on [yt-dlp](https://github.com/yt-dlp/yt-dlp).
It lets Claude Code, Claude Desktop, Cursor, Windsurf, VS Code and any other
[Model Context Protocol](https://modelcontextprotocol.io/) client download
videos and audio, read transcripts, inspect videos, search YouTube, and sync
whole playlists or channels, all by asking in plain language. It works with
YouTube and the 1,800+ other sites yt-dlp supports (Vimeo, TikTok, Twitter/X,
Twitch, SoundCloud, Reddit and more).

Videos are saved as MP4 to your **Videos** folder. Audio is saved as MP3, with
cover art, title, artist and chapters embedded, to your **Music** folder.

```text
You:    Download the audio of this lecture and split it by chapter
Claude: Saved 12 MP3 tracks to ~/Music/Lecture Title/ ...

You:    Summarize what this video says about rate limiting
Claude: (reads the transcript with get_transcript, no download needed) ...

You:    Sync my "Watch later" playlist to my Videos folder
Claude: Downloaded 3 new videos, 41 already present and skipped ...
```

**Contents:**
[Why this server](#why-this-yt-dlp-mcp-server) •
[Tools](#tools) •
[Requirements](#requirements) •
[Install](#install) •
[Client setup](#mcp-client-setup) •
[Docker / Podman](#run-in-a-container-docker-or-podman) •
[Configuration](#configuration) •
[Examples](#what-you-can-ask) •
[FAQ](#faq)

## Why this yt-dlp MCP server

There are several yt-dlp and YouTube MCP servers. This one focuses on being a
reliable downloader and research tool for daily use:

- **Background downloads with job tracking.** Long downloads never block the
  conversation. Short ones return the file path directly; long ones return a
  `job_id` you can check or cancel. Two run at a time, the rest queue.
- **Playlist and channel sync.** A download archive remembers what you already
  have, so re-running `download_playlist` only fetches new uploads.
- **Transcripts without downloading.** Timestamped text from real subtitles or
  auto-captions, paged so long videos fit in context.
- **Music-library quality audio.** MP3 with embedded cover art, title, artist
  and chapters. Optionally split an album upload into one track per chapter.
- **Clips and SponsorBlock.** Save just a `start`/`end` range, or strip sponsor
  segments automatically.
- **Files land where you expect.** Videos go to `~/Videos`, music to `~/Music`,
  playlists into their own subfolder, with readable file names.
- **Bundled yt-dlp.** yt-dlp is a Python dependency of this package, so you do
  not install or update it separately. One command upgrades it.
- **Ready-made container image.** Pull `ghcr.io/manshaaazar/yt-dlp-mcp` and run
  it with Docker or rootless Podman with only your media folders mounted. No
  Python, ffmpeg or Node on the host. Rebuilt weekly with the latest yt-dlp.
- **Tested against the real protocol.** The test suite launches the server over
  stdio exactly as an MCP client does.

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
  chapter splitting. On Windows: `winget install Gyan.FFmpeg`. On macOS:
  `brew install ffmpeg`. On Debian/Ubuntu: `sudo apt install ffmpeg`. The server
  also finds ffmpeg in winget's install folders even when your PATH has not refreshed.
- **Node.js** (or Deno). YouTube now requires a JavaScript runtime for yt-dlp to
  solve its player challenges. The server passes the Node it finds on PATH.

## Install

Clone the repository and create the environment:

```powershell
git clone https://github.com/manshaaazar/yt-dlp-mcp.git
cd yt-dlp-mcp
uv sync
```

This creates a `ytdlp-mcp` executable inside `.venv` that MCP clients launch over
stdio:

- Windows: `C:\path\to\yt-dlp-mcp\.venv\Scripts\ytdlp-mcp.exe`
- macOS / Linux: `/path/to/yt-dlp-mcp/.venv/bin/ytdlp-mcp`

You can also run it without cloning, straight from GitHub with `uvx`:

```bash
uvx --from git+https://github.com/manshaaazar/yt-dlp-mcp ytdlp-mcp
```

## MCP client setup

The server speaks MCP over stdio, so it works with every MCP client. Replace the
path below with the executable from [Install](#install).

### Claude Code

Register it for all projects:

```powershell
claude mcp add --scope user yt-dlp -- "C:\path\to\yt-dlp-mcp\.venv\Scripts\ytdlp-mcp.exe"
claude mcp list
```

### Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yt-dlp": {
      "command": "C:\\path\\to\\yt-dlp-mcp\\.venv\\Scripts\\ytdlp-mcp.exe"
    }
  }
}
```

### Cursor, Windsurf, VS Code and other clients

Use the same JSON shape in the client's MCP settings (`.cursor/mcp.json`,
`~/.codeium/windsurf/mcp_config.json`, or VS Code's `mcp.json`). For `uvx`
without a clone:

```json
{
  "mcpServers": {
    "yt-dlp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/manshaaazar/yt-dlp-mcp", "ytdlp-mcp"]
    }
  }
}
```

## Run in a container (Docker or Podman)

A multi-arch image (amd64 and arm64) is published to GitHub Container Registry
on every release and rebuilt weekly with the latest yt-dlp:

```text
ghcr.io/manshaaazar/yt-dlp-mcp:latest
```

It bundles Python, yt-dlp, ffmpeg and Node, so nothing else is installed on
the host. The `run-docker.sh` and `run-podman.sh` scripts in this repo start it
the way an MCP client expects (stdio), mount only `~/Videos`, `~/Music` and
`~/.local/share/yt-dlp-mcp` at the same paths inside the container, and run it
as your user, so the file paths the tools return are real host paths and the
files are owned by you. The container is read-only, drops all capabilities and
is memory-limited.

Works on Linux and macOS (Docker Desktop or Podman). On Windows the mounted
paths differ inside the container, so use the [native install](#install) there.

**Docker**

```bash
git clone https://github.com/manshaaazar/yt-dlp-mcp.git
claude mcp add --scope user yt-dlp -- "$PWD/yt-dlp-mcp/run-docker.sh"
```

Or without the scripts, in any client's MCP config (adjust the two folders):

```json
{
  "mcpServers": {
    "yt-dlp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--user", "1000:1000",
        "-v", "/home/you/Videos:/home/you/Videos",
        "-v", "/home/you/Music:/home/you/Music",
        "-e", "YTDLP_VIDEO_DIR=/home/you/Videos",
        "-e", "YTDLP_AUDIO_DIR=/home/you/Music",
        "ghcr.io/manshaaazar/yt-dlp-mcp:latest"
      ]
    }
  }
}
```

**Rootless Podman (Linux)**

```bash
sudo apt install -y podman
git clone https://github.com/manshaaazar/yt-dlp-mcp.git
claude mcp add --scope user yt-dlp -- "$PWD/yt-dlp-mcp/run-podman.sh"
```

Both scripts accept `YTDLP_MCP_IMAGE` to pin a tag (for example
`ghcr.io/manshaaazar/yt-dlp-mcp:0.2`) or to use a local build:

```bash
podman build -t ytdlp-mcp .
YTDLP_MCP_IMAGE=localhost/ytdlp-mcp:latest ./run-podman.sh
```

To update, pull the image again (`docker pull ghcr.io/manshaaazar/yt-dlp-mcp:latest`)
and restart your MCP client.

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

## What you can ask

Once connected, talk to your assistant normally. Some prompts that map to the
tools above:

- "Download this YouTube video in 1080p."
- "Save just the part from 12:30 to 15:00 of this video."
- "Get the audio of this song as MP3 with the album art."
- "This upload is a full album. Download it and split it into tracks."
- "Download this talk but skip the sponsor segments."
- "Give me the transcript of this video and summarize the main points."
- "What does the speaker say about X? Quote the timestamps."
- "Search YouTube for the best Rust async tutorials and list the links."
- "List every video in this channel uploaded after 2025-01-01."
- "Download this playlist. Later, run it again to get only the new videos."
- "How are my downloads going?" / "Cancel that download."

## Keeping yt-dlp current

YouTube changes often, and yt-dlp releases fixes quickly. When downloads start
failing, update:

```powershell
uv lock --upgrade-package yt-dlp
uv sync
```

Then restart your MCP client. If you use the container image, pull it again
instead; it is rebuilt weekly with the current yt-dlp.

## Tests

```powershell
uv run pytest                 # everything, including live downloads (needs network + ffmpeg)
uv run pytest -m "not live"   # offline unit tests only
```

`tests/test_stdio.py` launches the real server over stdio, the way an MCP client
does, which catches any stray output that would corrupt the protocol stream.

## FAQ

**Does this work with sites other than YouTube?**
Yes. Anything yt-dlp supports: Vimeo, TikTok, Twitter/X, Twitch VODs,
SoundCloud, Bandcamp, Reddit, Instagram and
[1,800+ others](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

**Do I need to install yt-dlp myself?**
No. yt-dlp is a dependency of this package and is installed by `uv sync`. You
only need ffmpeg and Node.js on the machine.

**Can Claude read a video without downloading it?**
Yes. `get_transcript` returns the timestamped transcript from subtitles or
auto-captions, and `get_video_info` returns metadata and chapters. Neither saves
the video.

**Why does a download tool return a `job_id`?**
Downloads run in the background so the conversation is not blocked. The tool
waits up to 50 seconds; if the download takes longer, it hands back a `job_id`
to check with `check_downloads`.

**Downloads suddenly fail with a YouTube error.**
YouTube changed something and yt-dlp has likely already shipped a fix. See
[Keeping yt-dlp current](#keeping-yt-dlp-current).

**Where do files go?**
Videos to `~/Videos`, audio to `~/Music`, playlists into a subfolder named after
the playlist. Change this with `YTDLP_VIDEO_DIR` and `YTDLP_AUDIO_DIR`.

**Is it safe to run?**
The server only talks to your MCP client over stdio and writes to your media
folders. With the [container image](#run-in-a-container-docker-or-podman) it
runs read-only, as your user, with all capabilities dropped and only those
folders mounted.

## Contributing

Issues and pull requests are welcome. If this server is useful to you, a star
helps other people find it.

## Notes

Respect the terms of service of the sites you download from, and only download
content you have the right to save.

## License

[MIT](LICENSE)

---

*Keywords: YouTube MCP server, yt-dlp MCP, Model Context Protocol, Claude MCP
YouTube downloader, Claude Code YouTube, Claude Desktop YouTube, Cursor MCP
video download, YouTube transcript MCP, download YouTube video with AI, MP3
from YouTube with Claude, playlist downloader MCP, Python MCP server, Docker MCP server, yt-dlp Docker
image.*
