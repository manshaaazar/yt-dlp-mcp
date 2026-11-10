from dataclasses import replace
from pathlib import Path

import pytest

from ytdlp_mcp.argv import (
    PlaylistOptions,
    build_audio_argv,
    build_query_argv,
    build_video_argv,
    parse_timestamp,
    to_ydl_opts,
)
from ytdlp_mcp.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        video_dir=tmp_path / "Videos",
        audio_dir=tmp_path / "Music",
        data_dir=tmp_path / "data",
        ffmpeg=tmp_path / "ffmpeg" / "ffmpeg.exe",
        node="C:/node/node.exe",
    )


def pp_keys(opts):
    return [pp["key"] for pp in opts.get("postprocessors", [])]


def value_after(argv, flag):
    return argv[argv.index(flag) + 1]


# --- timestamps -------------------------------------------------------------

@pytest.mark.parametrize(
    "text, seconds",
    [("83", 83.0), ("1:23", 83.0), ("01:02:03", 3723.0), ("12.5", 12.5), ("0:07.25", 7.25)],
)
def test_parse_timestamp_accepts_common_forms(text, seconds):
    assert parse_timestamp(text) == seconds


@pytest.mark.parametrize("bad", ["", "abc", "1:2:3:4", "-5", "1:75", "--exec"])
def test_parse_timestamp_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_timestamp(bad)


# --- video ------------------------------------------------------------------

def test_video_saves_to_video_dir_as_mp4(settings):
    opts = to_ydl_opts(build_video_argv(settings))
    assert opts["paths"]["home"] == str(settings.video_dir)
    assert opts["merge_output_format"] == "mp4"
    assert opts["outtmpl"]["default"] == "%(title)s [%(id)s].%(ext)s"


def test_video_single_download_ignores_playlist(settings):
    opts = to_ydl_opts(build_video_argv(settings))
    assert opts["noplaylist"] is True
    assert "download_archive" not in opts or opts["download_archive"] is None


def test_video_prefers_highest_resolution_then_h264(settings):
    argv = build_video_argv(settings)
    assert value_after(argv, "-S") == "res,fps,vcodec:h264,acodec:aac"


def test_video_max_height_caps_resolution(settings):
    argv = build_video_argv(settings, max_height=1080)
    assert value_after(argv, "-S").startswith("res:1080,")


def test_video_passes_ffmpeg_and_node(settings):
    opts = to_ydl_opts(build_video_argv(settings))
    assert opts["ffmpeg_location"] == str(settings.ffmpeg)
    assert "node" in opts["js_runtimes"]
    assert opts["js_runtimes"]["node"]["path"] == "C:/node/node.exe"


def test_video_clip_downloads_only_requested_range(settings):
    argv = build_video_argv(settings, start="1:00", end="1:30")
    assert value_after(argv, "--download-sections") == "*60-90"
    assert "--force-keyframes-at-cuts" in argv
    opts = to_ydl_opts(argv)
    assert "download_ranges" in opts
    assert opts["outtmpl"]["default"] == "%(title)s [%(id)s] (60-90).%(ext)s"


def test_video_clip_with_only_start_runs_to_end(settings):
    argv = build_video_argv(settings, start="10")
    assert value_after(argv, "--download-sections") == "*10-inf"
    assert to_ydl_opts(argv)["outtmpl"]["default"].endswith("(10-end).%(ext)s")


def test_proxy_only_when_configured(settings):
    assert "--proxy" not in build_video_argv(settings)
    proxied = replace(settings, proxy="socks5h://host.containers.internal:40000")
    assert value_after(build_video_argv(proxied), "--proxy") == "socks5h://host.containers.internal:40000"
    assert value_after(build_audio_argv(proxied), "--proxy") == "socks5h://host.containers.internal:40000"
    assert value_after(build_query_argv(proxied), "--proxy") == "socks5h://host.containers.internal:40000"


def test_ignores_user_yt_dlp_config_files(settings):
    assert build_video_argv(settings)[0] == "--ignore-config"


def test_clip_end_before_start_rejected(settings):
    with pytest.raises(ValueError):
        build_video_argv(settings, start="2:00", end="1:00")


def test_video_sponsorblock_removal_only_when_asked(settings):
    assert "SponsorBlock" not in pp_keys(to_ydl_opts(build_video_argv(settings)))
    opts = to_ydl_opts(build_video_argv(settings, remove_sponsors=True))
    assert "SponsorBlock" in pp_keys(opts)
    assert "ModifyChapters" in pp_keys(opts)


def test_video_no_mtime_so_new_files_sort_first(settings):
    opts = to_ydl_opts(build_video_argv(settings))
    assert opts["updatetime"] is False


# --- audio ------------------------------------------------------------------

def test_audio_extracts_mp3_into_audio_dir(settings):
    opts = to_ydl_opts(build_audio_argv(settings))
    assert opts["paths"]["home"] == str(settings.audio_dir)
    extract = next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio")
    assert extract["preferredcodec"] == "mp3"


def test_audio_embeds_cover_art_and_metadata(settings):
    keys = pp_keys(to_ydl_opts(build_audio_argv(settings)))
    assert "EmbedThumbnail" in keys
    assert "FFmpegMetadata" in keys


def test_audio_split_chapters_writes_tracks_into_subfolder(settings):
    opts = to_ydl_opts(build_audio_argv(settings, split_chapters=True))
    assert "FFmpegSplitChapters" in pp_keys(opts)
    assert opts["outtmpl"]["chapter"].startswith("%(title)s [%(id)s]/")


def test_audio_format_must_be_supported(settings):
    with pytest.raises(ValueError):
        build_audio_argv(settings, audio_format="exe")


# --- playlists --------------------------------------------------------------

def test_playlist_uses_archive_and_subfolder(settings):
    opts = to_ydl_opts(build_video_argv(settings, playlist=PlaylistOptions()))
    assert opts["noplaylist"] is False
    assert opts["download_archive"] == str(settings.archive_file)
    assert opts["outtmpl"]["default"].startswith("%(playlist_title,playlist_id)s/")


def test_playlist_limit_and_date(settings):
    argv = build_audio_argv(settings, playlist=PlaylistOptions(limit=5, after_date="2026-01-31"))
    opts = to_ydl_opts(argv)
    assert opts["playlistend"] == 5
    assert value_after(argv, "--dateafter") == "20260131"


def test_playlist_bad_date_rejected(settings):
    with pytest.raises(ValueError):
        build_audio_argv(settings, playlist=PlaylistOptions(after_date="last tuesday"))


def test_channel_date_filter_stops_at_first_older_video(settings):
    # Channels list newest first, so stop instead of extracting every older video.
    options = PlaylistOptions(after_date="2026-01-31", newest_first=True)
    argv = build_video_argv(settings, playlist=options)
    assert value_after(argv, "--break-match-filters") == "upload_date>=20260131"
    assert value_after(argv, "--dateafter") == "20260131"


def test_playlist_date_filter_does_not_stop_early(settings):
    # Playlists can be in any order, so every item must be checked.
    argv = build_video_argv(settings, playlist=PlaylistOptions(after_date="2026-01-31"))
    assert "--break-match-filters" not in argv
