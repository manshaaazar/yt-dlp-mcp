"""Calls into yt-dlp. All yt-dlp output goes to logging (stderr), never stdout,
because stdout carries the MCP JSON-RPC stream."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import ExistingVideoReached, MaxDownloadsReached, RejectedVideoReached

from .argv import build_query_argv, to_ydl_opts
from .config import Settings, ensure_dirs, ensure_on_path
from .jobs import Job
from .transcript import format_transcript, group_paragraphs, page, parse_json3, parse_vtt, pick_track
from .urls import normalize_channel_url

log = logging.getLogger("ytdlp_mcp.yt_dlp")

ARCHIVE_SKIP = "has already been recorded in the archive"
QUIET = {"quiet": True, "noprogress": True}


class _Logger:
    """Receives everything yt-dlp would print; remembers errors and archive skips."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.archive_skips = 0

    def debug(self, msg: str) -> None:
        if ARCHIVE_SKIP in msg:
            self.archive_skips += 1
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg.removeprefix("ERROR: ").strip())
        log.error(msg)


class _Collector(PostProcessor):
    """Runs after files reach their final folder and records their paths."""

    def __init__(self, sink: list[dict]):
        super().__init__(None)
        self.sink = sink

    def run(self, info):
        chapters = [c["filepath"] for c in info.get("chapters") or [] if c.get("filepath")]
        self.sink.append(
            {
                "id": info.get("id"),
                "title": info.get("title"),
                "duration_seconds": _int(info.get("duration")),
                "paths": [p for p in [info.get("filepath"), *chapters] if p],
            }
        )
        return [], info


def _int(value) -> int | None:
    return int(round(value)) if isinstance(value, (int, float)) else None


def _date(value: str | None) -> str | None:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if value and len(value) == 8 else value


def _stamp(seconds) -> str | None:
    if not isinstance(seconds, (int, float)):
        return None
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _file_entry(path: str) -> dict[str, Any]:
    p = Path(path)
    size = p.stat().st_size if p.exists() else 0
    return {"path": str(p), "size_mb": round(size / 1_048_576, 2)}


def _entry_url(entry: dict) -> str | None:
    url = entry.get("url") or entry.get("webpage_url")
    if url and url.startswith("http"):
        return url
    if entry.get("ie_key") == "Youtube" and entry.get("id"):
        return f"https://www.youtube.com/watch?v={entry['id']}"
    return url


class Downloader:
    def __init__(self, settings: Settings):
        self.settings = settings
        ensure_on_path(settings.ffmpeg)

    def _ydl(self, argv: list[str], logger: _Logger | None = None, **extra) -> YoutubeDL:
        opts = to_ydl_opts(argv)
        opts.update(QUIET)
        opts["logger"] = logger or _Logger()
        opts.update(extra)
        return YoutubeDL(opts)

    # --- read-only ----------------------------------------------------------

    def _extract(self, url: str, *flags: str) -> dict:
        logger = _Logger()
        with self._ydl(build_query_argv(self.settings, *flags), logger) as ydl:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)

    def info(self, url: str) -> dict[str, Any]:
        info = self._extract(url, "--no-playlist", "--flat-playlist")
        if info.get("_type") == "playlist":
            return {
                "type": "playlist",
                "title": info.get("title"),
                "url": info.get("webpage_url") or url,
                "entry_count": info.get("playlist_count"),
                "hint": "This is a playlist or channel. Use list_playlist to see its videos.",
            }
        heights = sorted(
            {f["height"] for f in info.get("formats") or [] if f.get("height") and f.get("vcodec") != "none"},
            reverse=True,
        )
        description = info.get("description") or ""
        subs = sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat")
        auto = info.get("automatic_captions") or {}
        return {
            "type": "video",
            "id": info.get("id"),
            "title": info.get("title"),
            "url": info.get("webpage_url") or url,
            "site": info.get("extractor_key"),
            "channel": info.get("channel") or info.get("uploader"),
            "channel_url": info.get("channel_url") or info.get("uploader_url"),
            "duration_seconds": _int(info.get("duration")),
            "duration": _stamp(info.get("duration")),
            "upload_date": _date(info.get("upload_date")),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "is_live": bool(info.get("is_live")),
            "available_heights": heights,
            "chapters": [
                {"start": _stamp(c.get("start_time")), "title": c.get("title")}
                for c in info.get("chapters") or []
            ],
            "subtitle_languages": subs,
            "auto_caption_languages": sorted(k.removesuffix("-orig") for k in auto if k.endswith("-orig")),
            "has_auto_captions": bool(auto),
            "description": description[:1500] + ("…" if len(description) > 1500 else ""),
            "thumbnail": info.get("thumbnail"),
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 25))
        info = self._extract(f"ytsearch{limit}:{query}", "--flat-playlist")
        return [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "url": _entry_url(e),
                "channel": e.get("channel") or e.get("uploader"),
                "duration": _stamp(e.get("duration")),
                "view_count": e.get("view_count"),
            }
            for e in info.get("entries") or []
        ]

    def list_playlist(self, url: str, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        url = normalize_channel_url(url)
        info = self._extract(url, "--yes-playlist", "--flat-playlist", "--playlist-end", str(limit))
        entries = list(info.get("entries") or [])
        total = info.get("playlist_count")
        return {
            "title": info.get("title"),
            "url": info.get("webpage_url") or url,
            "channel": info.get("channel") or info.get("uploader"),
            "entry_count": total,
            "shown": len(entries),
            "truncated": total is None or total > len(entries),
            "entries": [
                {
                    "index": i,
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "url": _entry_url(e),
                    "duration": _stamp(e.get("duration")),
                    "upload_date": _date(e.get("upload_date")),
                }
                for i, e in enumerate(entries, start=1)
            ],
        }

    def transcript(self, url: str, lang: str = "en", offset: int = 0, max_chars: int = 40_000) -> dict[str, Any]:
        logger = _Logger()
        with self._ydl(build_query_argv(self.settings, "--no-playlist"), logger) as ydl:
            info = ydl.extract_info(url, download=False)
            subs, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
            choice = pick_track(subs, auto, lang)
            if choice is None:
                have = sorted(k for k in subs if k != "live_chat")
                orig = sorted(k.removesuffix("-orig") for k in auto if k.endswith("-orig"))
                raise ValueError(
                    f"No '{lang}' transcript for this video. Subtitles: {have or 'none'}; "
                    f"auto-captions (original language): {orig or 'none'}."
                )
            source, key, fmt = choice
            raw = ydl.urlopen(fmt["url"]).read().decode("utf-8", errors="replace")

        segments = parse_json3(json.loads(raw)) if fmt["ext"] == "json3" else parse_vtt(raw)
        text = format_transcript(group_paragraphs(segments))
        return {
            "id": info.get("id"),
            "title": info.get("title"),
            "language": key.removesuffix("-orig"),
            "source": "subtitles" if source == "subtitles" else "auto-captions",
            **page(text, offset, max_chars),
        }

    # --- downloads ----------------------------------------------------------

    def download(self, url: str, argv: list[str], job: Job | None = None) -> dict[str, Any]:
        ensure_dirs(self.settings)
        single = "--no-playlist" in argv
        if not single:
            url = normalize_channel_url(url)
        logger = _Logger()
        collected: list[dict] = []

        def on_progress(d: dict) -> None:
            if job is None:
                return
            job.raise_if_cancelled()
            info = d.get("info_dict") or {}
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            job.update_progress(
                stage=d.get("status"),
                title=info.get("title"),
                item=f"{info['playlist_index']}/{info.get('n_entries') or '?'}" if info.get("playlist_index") else None,
                percent=round(done * 100 / total, 1) if total else None,
                downloaded_mb=round(done / 1_048_576, 1),
                total_mb=round(total / 1_048_576, 1) if total else None,
                speed_mb_s=round(d["speed"] / 1_048_576, 2) if d.get("speed") else None,
                eta_seconds=d.get("eta"),
            )

        def on_postprocess(d: dict) -> None:
            if job is None:
                return
            job.raise_if_cancelled()
            if d.get("status") == "started":
                job.update_progress(stage=f"processing ({d.get('postprocessor')})", percent=None, eta_seconds=None)

        ydl = self._ydl(argv, logger, progress_hooks=[on_progress], postprocessor_hooks=[on_postprocess])
        ydl.add_post_processor(_Collector(collected), when="after_move")
        with ydl:
            if single:
                ie_result = ydl.extract_info(url, download=False, process=False)
                if ie_result is None:
                    # yt-dlp swallowed an extraction error (e.g. video unavailable) and logged it.
                    raise RuntimeError(logger.errors[-1] if logger.errors else "Could not read that video")
                if ie_result.get("_type") == "playlist":
                    raise ValueError(
                        "That link is a playlist or channel. Use download_playlist, "
                        "or list_playlist to see what it contains."
                    )
                ydl.process_ie_result(ie_result, download=True)
            else:
                try:
                    ydl.extract_info(url, download=True)
                except (RejectedVideoReached, ExistingVideoReached, MaxDownloadsReached) as stop:
                    # A filter told yt-dlp to stop early (e.g. reached videos older than after_date).
                    log.info("Stopped early: %s", stop)

        if single and not collected and logger.errors:
            raise RuntimeError(logger.errors[-1])

        files = [_file_entry(p) for item in collected for p in item["paths"]]
        result: dict[str, Any] = {
            "files": files,
            "videos": [{k: v for k, v in item.items() if k != "paths"} for item in collected],
            "skipped_already_downloaded": logger.archive_skips,
        }
        if logger.errors:
            result["errors"] = logger.errors
        return result
