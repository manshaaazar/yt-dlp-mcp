"""End-to-end tests against real YouTube. Need network and ffmpeg.

Skip with: uv run pytest -m "not live"
"""
import pytest

from ytdlp_mcp.argv import PlaylistOptions, build_audio_argv, build_video_argv
from ytdlp_mcp.config import Settings, find_ffmpeg, find_node
from ytdlp_mcp.core import Downloader

pytestmark = pytest.mark.live

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19 seconds
ZOO_CHANNEL = "https://www.youtube.com/@jawed"


@pytest.fixture
def settings(tmp_path):
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.fail("ffmpeg not found; live tests need it")
    return Settings(
        video_dir=tmp_path / "Videos",
        audio_dir=tmp_path / "Music",
        data_dir=tmp_path / "data",
        ffmpeg=ffmpeg,
        node=find_node(),
    )


@pytest.fixture
def dl(settings):
    return Downloader(settings)


def test_info(dl):
    info = dl.info(ZOO)
    assert info["id"] == "jNQXAC9IVRw"
    assert info["title"] == "Me at the zoo"
    assert info["duration_seconds"] == 19
    assert info["available_heights"]


def test_search(dl):
    results = dl.search("me at the zoo jawed", limit=3)
    assert 1 <= len(results) <= 3
    assert all(r["url"].startswith("https://") for r in results)


def test_transcript(dl):
    result = dl.transcript(ZOO, lang="en")
    assert "elephant" in result["text"].lower()
    assert result["text"].startswith("[00:0")


def test_list_channel(dl):
    listing = dl.list_playlist(ZOO_CHANNEL, limit=5)
    assert any(e["id"] == "jNQXAC9IVRw" for e in listing["entries"])


def test_download_video_mp4(dl, settings):
    result = dl.download(ZOO, build_video_argv(settings))
    paths = [f["path"] for f in result["files"]]
    assert len(paths) == 1
    assert paths[0].endswith("Me at the zoo [jNQXAC9IVRw].mp4")
    assert paths[0].startswith(str(settings.video_dir))
    assert result["files"][0]["size_mb"] > 0


def test_download_audio_mp3_with_cover_art(dl, settings):
    from mutagen.id3 import ID3

    result = dl.download(ZOO, build_audio_argv(settings))
    path = result["files"][0]["path"]
    assert path.endswith("Me at the zoo [jNQXAC9IVRw].mp3")
    assert path.startswith(str(settings.audio_dir))
    tags = ID3(path)
    assert tags.getall("APIC"), "cover art not embedded"
    assert str(tags["TIT2"]) == "Me at the zoo"


def test_download_clip(dl, settings):
    result = dl.download(ZOO, build_video_argv(settings, start="0:05", end="0:10"))
    path = result["files"][0]["path"]
    assert path.endswith("(5-10).mp4")


def test_playlist_sync_skips_already_downloaded(dl, settings):
    argv = build_audio_argv(settings, playlist=PlaylistOptions(limit=1))
    first = dl.download(ZOO_CHANNEL, argv)
    assert len(first["files"]) == 1
    assert first["files"][0]["path"].startswith(str(settings.audio_dir))
    second = dl.download(ZOO_CHANNEL, argv)
    assert second["files"] == []
    assert second["skipped_already_downloaded"] == 1


def test_channel_after_date_returns_quickly_with_nothing_new(dl, settings):
    import time

    started = time.monotonic()
    argv = build_audio_argv(settings, playlist=PlaylistOptions(after_date="2010-01-01", newest_first=True))
    result = dl.download(ZOO_CHANNEL, argv)
    assert result["files"] == []
    assert time.monotonic() - started < 60
