"""URL helpers."""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_CHANNEL_PATH = re.compile(r"^/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)(/[^/]+)?/?$")


def is_channel_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname in _YOUTUBE_HOSTS and bool(_CHANNEL_PATH.match(parts.path))


def normalize_channel_url(url: str) -> str:
    """Point a bare YouTube channel URL at its Videos tab.

    A bare channel URL lists the channel's tabs (Videos, Shorts, Live), not videos.
    """
    parts = urlsplit(url)
    match = _CHANNEL_PATH.match(parts.path) if parts.hostname in _YOUTUBE_HOSTS else None
    if not match or match.group(2):
        return url
    return urlunsplit(parts._replace(path=f"/{match.group(1)}/videos"))
