"""Turn tool arguments into a yt-dlp command line, then into YoutubeDL options.

Building CLI flags and letting yt-dlp's own parser produce the options dict
keeps postprocessor ordering and keys exactly as yt-dlp expects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import yt_dlp

from .config import Settings

AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "wav", "aac", "vorbis", "alac")
SPONSOR_CATEGORIES = "sponsor,selfpromo,interaction,intro,outro"

NAME = "%(title)s [%(id)s]"
PLAYLIST_DIR = "%(playlist_title,playlist_id)s/"
PLAYLIST_NAME = "%(upload_date>%Y-%m-%d|unknown-date)s - " + NAME
CHAPTER_NAME = NAME + "/%(section_number)02d - %(section_title)s.%(ext)s"

_TIMESTAMP = re.compile(r"^(\d+)(?::(\d{1,2}))?(?::(\d{1,2}))?(\.\d+)?$")


@dataclass(frozen=True)
class PlaylistOptions:
    limit: int | None = None
    after_date: str | None = None
    newest_first: bool = False  # True for channels: stop at the first video older than after_date


def parse_timestamp(text: str) -> float:
    """Parse '83', '1:23', '01:02:03' or '0:07.25' into seconds."""
    match = _TIMESTAMP.match(text.strip())
    if not match:
        raise ValueError(f"Invalid timestamp {text!r}; use seconds, MM:SS or HH:MM:SS")
    parts = [int(p) for p in match.groups()[:3] if p is not None]
    if any(p >= 60 for p in parts[1:]):
        raise ValueError(f"Invalid timestamp {text!r}; minutes and seconds must be below 60")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds + float(match.group(4) or 0)


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _section(start: str | None, end: str | None) -> tuple[str, str] | None:
    """Return (download-sections value, filename suffix) for a clip, or None."""
    if start is None and end is None:
        return None
    s = parse_timestamp(start) if start is not None else 0.0
    e = parse_timestamp(end) if end is not None else None
    if e is not None and e <= s:
        raise ValueError("Clip end must be after clip start")
    e_arg, e_name = (_num(e), _num(e)) if e is not None else ("inf", "end")
    return f"*{_num(s)}-{e_arg}", f"({_num(s)}-{e_name})"


def _yyyymmdd(text: str) -> str:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y%m%d")
        except ValueError:
            pass
    raise ValueError(f"Invalid date {text!r}; use YYYY-MM-DD")


def _base(settings: Settings, home) -> list[str]:
    argv = ["--ignore-config", "--paths", f"home:{home}", "--no-mtime"]
    if settings.ffmpeg:
        argv += ["--ffmpeg-location", str(settings.ffmpeg)]
    argv += ["--js-runtimes", f"node:{settings.node}" if settings.node else "node"]
    if settings.proxy:
        argv += ["--proxy", settings.proxy]
    return argv


def _scope(settings: Settings, playlist: PlaylistOptions | None) -> list[str]:
    if playlist is None:
        return ["--no-playlist"]
    argv = ["--yes-playlist", "--download-archive", str(settings.archive_file)]
    if playlist.limit is not None:
        if playlist.limit < 1:
            raise ValueError("limit must be at least 1")
        argv += ["--playlist-end", str(playlist.limit)]
    if playlist.after_date:
        date = _yyyymmdd(playlist.after_date)
        argv += ["--dateafter", date]
        if playlist.newest_first:
            argv += ["--break-match-filters", f"upload_date>={date}"]
    return argv


def _template(playlist: PlaylistOptions | None, clip_suffix: str | None) -> str:
    if playlist is not None:
        return PLAYLIST_DIR + PLAYLIST_NAME + ".%(ext)s"
    if clip_suffix:
        return f"{NAME} {clip_suffix}.%(ext)s"
    return NAME + ".%(ext)s"


def _clip_and_sponsors(section, remove_sponsors: bool) -> list[str]:
    argv = []
    if section:
        argv += ["--download-sections", section[0], "--force-keyframes-at-cuts"]
    if remove_sponsors:
        argv += ["--sponsorblock-remove", SPONSOR_CATEGORIES]
    return argv


def build_video_argv(
    settings: Settings,
    *,
    max_height: int | None = None,
    start: str | None = None,
    end: str | None = None,
    remove_sponsors: bool = False,
    playlist: PlaylistOptions | None = None,
) -> list[str]:
    section = _section(start, end)
    if max_height is not None and not 144 <= max_height <= 4320:
        raise ValueError("max_height must be between 144 and 4320")
    sort = (f"res:{max_height}," if max_height else "res,") + "fps,vcodec:h264,acodec:aac"
    argv = _base(settings, settings.video_dir) + _scope(settings, playlist)
    argv += ["-S", sort, "--merge-output-format", "mp4"]
    argv += _clip_and_sponsors(section, remove_sponsors)
    argv += ["-o", _template(playlist, section[1] if section else None)]
    return argv


def build_audio_argv(
    settings: Settings,
    *,
    audio_format: str = "mp3",
    start: str | None = None,
    end: str | None = None,
    split_chapters: bool = False,
    remove_sponsors: bool = False,
    playlist: PlaylistOptions | None = None,
) -> list[str]:
    if audio_format not in AUDIO_FORMATS:
        raise ValueError(f"audio_format must be one of {', '.join(AUDIO_FORMATS)}")
    section = _section(start, end)
    argv = _base(settings, settings.audio_dir) + _scope(settings, playlist)
    argv += ["-x", "--audio-format", audio_format, "--audio-quality", "0"]
    argv += ["--embed-thumbnail", "--embed-metadata", "--embed-chapters"]
    argv += _clip_and_sponsors(section, remove_sponsors)
    argv += ["-o", _template(playlist, section[1] if section else None)]
    if split_chapters:
        prefix = PLAYLIST_DIR if playlist is not None else ""
        argv += ["--split-chapters", "-o", f"chapter:{prefix}{CHAPTER_NAME}"]
    return argv


def build_query_argv(settings: Settings, *flags: str) -> list[str]:
    """Options for read-only calls (info, search, listing, transcripts)."""
    return _base(settings, settings.video_dir) + list(flags)


def to_ydl_opts(argv: list[str]) -> dict:
    return yt_dlp.parse_options(argv).ydl_opts
