"""Subtitle track selection and parsing into readable, paged transcripts."""
from __future__ import annotations

import html
import re

Segment = tuple[float, str]

USABLE_EXTS = ("json3", "vtt")
_TAG = re.compile(r"<[^>]+>")
_VTT_TIME = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})\s+-->")


def parse_json3(data: dict) -> list[Segment]:
    segments: list[Segment] = []
    for event in data.get("events", []):
        text = "".join(seg.get("utf8", "") for seg in event.get("segs") or [])
        text = " ".join(text.split())
        if text:
            segments.append((event.get("tStartMs", 0) / 1000, text))
    return segments


def parse_vtt(text: str) -> list[Segment]:
    """Parse WebVTT, dropping lines repeated from the previous cue (rolling captions)."""
    segments: list[Segment] = []
    previous: set[str] = set()
    for block in re.split(r"\r?\n\s*\r?\n", text):
        lines = block.strip().splitlines()
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        match = _VTT_TIME.match(lines[timing].strip())
        if not match:
            continue
        hours, minutes, seconds, millis = match.groups()
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000
        current: set[str] = set()
        for raw in lines[timing + 1:]:
            line = " ".join(html.unescape(_TAG.sub("", raw)).split())
            if not line:
                continue
            current.add(line)
            if line not in previous:
                segments.append((start, line))
        previous = current
    return segments


def _usable_format(formats: list[dict]) -> dict | None:
    for ext in USABLE_EXTS:
        for fmt in formats:
            if fmt.get("ext") == ext and fmt.get("url"):
                return fmt
    return None


def _matching_keys(tracks: dict, lang: str, exact_first: tuple[str, ...]) -> list[str]:
    lang = lang.lower()
    keys = [k for k in tracks if k != "live_chat"]
    ordered = [k for want in exact_first for k in keys if k.lower() == want]
    ordered += sorted(k for k in keys if k.lower().startswith(lang + "-") and k not in ordered)
    return ordered


def pick_track(subtitles: dict, automatic: dict, lang: str) -> tuple[str, str, dict] | None:
    """Choose (source, language key, format): real subtitles first, then auto-captions.

    Among auto-captions, '<lang>-orig' is the original speech; plain '<lang>' may be
    a machine translation.
    """
    lang = lang.lower()
    plan = [
        ("subtitles", subtitles or {}, (lang,)),
        ("automatic_captions", automatic or {}, (f"{lang}-orig", lang)),
    ]
    for source, tracks, exact in plan:
        for key in _matching_keys(tracks, lang, exact):
            fmt = _usable_format(tracks[key])
            if fmt:
                return source, key, fmt
    return None


def group_paragraphs(segments: list[Segment], window: float = 30.0) -> list[Segment]:
    paragraphs: list[tuple[float, list[str]]] = []
    for start, text in segments:
        if paragraphs and start - paragraphs[-1][0] < window:
            paragraphs[-1][1].append(text)
        else:
            paragraphs.append((start, [text]))
    return [(start, " ".join(parts)) for start, parts in paragraphs]


def _stamp(seconds: float, with_hours: bool) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if with_hours else f"{m:02d}:{s:02d}"


def format_transcript(paragraphs: list[Segment]) -> str:
    with_hours = any(start >= 3600 for start, _ in paragraphs)
    return "\n".join(f"[{_stamp(start, with_hours)}] {text}" for start, text in paragraphs)


def page(text: str, offset: int, max_chars: int) -> dict:
    """Return one page of text, cut on a line boundary where possible."""
    offset = max(0, offset)
    end = offset + max_chars
    if end >= len(text):
        chunk, next_offset = text[offset:], None
    else:
        chunk = text[offset:end]
        newline = chunk.rfind("\n")
        if newline > 0:
            chunk = chunk[: newline + 1]
        next_offset = offset + len(chunk)
    return {"text": chunk, "offset": offset, "next_offset": next_offset, "total_chars": len(text)}
