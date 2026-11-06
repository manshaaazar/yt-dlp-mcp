"""Folder locations and external tool discovery."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, MutableMapping


@dataclass(frozen=True)
class Settings:
    video_dir: Path
    audio_dir: Path
    data_dir: Path
    ffmpeg: Path | None
    node: str | None

    @property
    def archive_file(self) -> Path:
        return self.data_dir / "archive.txt"


def _default_data_dir(env: Mapping[str, str], home: Path) -> Path:
    """%LOCALAPPDATA% on Windows; $XDG_DATA_HOME or ~/.local/share elsewhere."""
    base = env.get("LOCALAPPDATA")
    if base:
        return Path(base) / "yt-dlp-mcp"
    xdg = env.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "yt-dlp-mcp"


def load_settings(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Settings:
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    return Settings(
        video_dir=Path(env.get("YTDLP_VIDEO_DIR") or home / "Videos"),
        audio_dir=Path(env.get("YTDLP_AUDIO_DIR") or home / "Music"),
        data_dir=Path(env.get("YTDLP_MCP_DATA_DIR") or _default_data_dir(env, home)),
        ffmpeg=find_ffmpeg(env, which),
        node=find_node(env, which),
    )


def find_ffmpeg(
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    """Locate ffmpeg without trusting PATH alone.

    The MCP server inherits its environment from the client, which may have
    started before ffmpeg was installed, so also look where winget puts it.
    """
    env = os.environ if env is None else env

    override = env.get("YTDLP_FFMPEG")
    if override and Path(override).is_file():
        return Path(override)

    on_path = which("ffmpeg")
    if on_path:
        return Path(on_path)

    local = env.get("LOCALAPPDATA")
    if local:
        winget = Path(local) / "Microsoft" / "WinGet"
        link = winget / "Links" / "ffmpeg.exe"
        if link.is_file():
            return link
        for candidate in sorted(winget.glob("Packages/*FFmpeg*/**/bin/ffmpeg.exe"), reverse=True):
            return candidate
    return None


def ensure_on_path(ffmpeg: Path | None, env: MutableMapping[str, str] | None = None) -> None:
    """Put ffmpeg's folder on PATH.

    yt-dlp's clip downloader (FFmpegFD) checks PATH only and ignores ffmpeg_location,
    and the client may have started this server before ffmpeg was installed.
    """
    if ffmpeg is None:
        return
    env = os.environ if env is None else env
    folder = str(Path(ffmpeg).parent)
    entries = [e for e in env.get("PATH", "").split(os.pathsep) if e]
    if os.path.normcase(folder) not in {os.path.normcase(e) for e in entries}:
        env["PATH"] = os.pathsep.join([folder, *entries])


def ensure_dirs(settings: Settings) -> None:
    """Create output and data folders; yt-dlp cannot write archive.txt into a missing folder."""
    for folder in (settings.video_dir, settings.audio_dir, settings.data_dir):
        folder.mkdir(parents=True, exist_ok=True)


def find_node(
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    """Node.js solves YouTube's JavaScript challenges for yt-dlp."""
    env = os.environ if env is None else env
    return env.get("YTDLP_NODE") or which("node")
