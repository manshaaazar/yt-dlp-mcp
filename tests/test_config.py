import os
from pathlib import Path

import pytest

from ytdlp_mcp.config import (
    HttpSettings,
    Settings,
    ensure_dirs,
    ensure_on_path,
    find_ffmpeg,
    load_http_settings,
    load_settings,
)


def test_default_folders_are_videos_and_music_under_home(tmp_path):
    settings = load_settings(env={}, home=tmp_path)
    assert settings.video_dir == tmp_path / "Videos"
    assert settings.audio_dir == tmp_path / "Music"


def test_env_vars_override_folders(tmp_path):
    env = {
        "YTDLP_VIDEO_DIR": str(tmp_path / "v"),
        "YTDLP_AUDIO_DIR": str(tmp_path / "a"),
        "YTDLP_MCP_DATA_DIR": str(tmp_path / "d"),
    }
    settings = load_settings(env=env, home=tmp_path)
    assert settings.video_dir == tmp_path / "v"
    assert settings.audio_dir == tmp_path / "a"
    assert settings.data_dir == tmp_path / "d"


def test_archive_file_lives_in_data_dir(tmp_path):
    settings = load_settings(env={"YTDLP_MCP_DATA_DIR": str(tmp_path)}, home=tmp_path)
    assert settings.archive_file == tmp_path / "archive.txt"


def test_data_dir_defaults_to_localappdata(tmp_path):
    settings = load_settings(env={"LOCALAPPDATA": str(tmp_path / "lad")}, home=tmp_path)
    assert settings.data_dir == tmp_path / "lad" / "yt-dlp-mcp"


def test_data_dir_defaults_to_xdg_data_home(tmp_path):
    settings = load_settings(env={"XDG_DATA_HOME": str(tmp_path / "xdg")}, home=tmp_path)
    assert settings.data_dir == tmp_path / "xdg" / "yt-dlp-mcp"


def test_data_dir_defaults_to_local_share_without_xdg(tmp_path):
    settings = load_settings(env={}, home=tmp_path)
    assert settings.data_dir == tmp_path / ".local" / "share" / "yt-dlp-mcp"


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_ffmpeg_env_override_wins(tmp_path):
    exe = _touch(tmp_path / "custom" / "ffmpeg.exe")
    found = find_ffmpeg(env={"YTDLP_FFMPEG": str(exe)}, which=lambda _: "C:/other/ffmpeg.exe")
    assert found == exe


def test_ffmpeg_found_on_path(tmp_path):
    exe = _touch(tmp_path / "bin" / "ffmpeg.exe")
    found = find_ffmpeg(env={}, which=lambda name: str(exe) if name == "ffmpeg" else None)
    assert found == exe


def test_ffmpeg_found_in_winget_links_when_not_on_path(tmp_path):
    exe = _touch(tmp_path / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
    found = find_ffmpeg(env={"LOCALAPPDATA": str(tmp_path)}, which=lambda _: None)
    assert found == exe


def test_ffmpeg_found_in_winget_package_folder(tmp_path):
    exe = _touch(
        tmp_path / "Microsoft" / "WinGet" / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.0-full_build" / "bin" / "ffmpeg.exe"
    )
    found = find_ffmpeg(env={"LOCALAPPDATA": str(tmp_path)}, which=lambda _: None)
    assert found == exe


def test_ffmpeg_missing_returns_none(tmp_path):
    assert find_ffmpeg(env={"LOCALAPPDATA": str(tmp_path)}, which=lambda _: None) is None


def test_ensure_on_path_prepends_ffmpeg_folder(tmp_path):
    # yt-dlp's clip downloader looks for ffmpeg on PATH only, ignoring ffmpeg_location.
    env = {"PATH": "C:/Windows"}
    ensure_on_path(tmp_path / "bin" / "ffmpeg.exe", env)
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin")
    assert "C:/Windows" in env["PATH"]


def test_ensure_on_path_does_not_duplicate(tmp_path):
    env = {"PATH": str(tmp_path / "bin")}
    ensure_on_path(tmp_path / "bin" / "ffmpeg.exe", env)
    assert env["PATH"] == str(tmp_path / "bin")


def test_ensure_on_path_ignores_missing_ffmpeg():
    env = {"PATH": "x"}
    ensure_on_path(None, env)
    assert env["PATH"] == "x"


def test_ensure_dirs_creates_data_dir_for_archive(tmp_path):
    # yt-dlp cannot write archive.txt into a folder that does not exist.
    settings = Settings(tmp_path / "V", tmp_path / "M", tmp_path / "deep" / "data", None, None)
    ensure_dirs(settings)
    assert settings.data_dir.is_dir()
    assert settings.video_dir.is_dir()
    assert settings.audio_dir.is_dir()


def test_proxy_unset_by_default(tmp_path):
    assert load_settings(env={}, home=tmp_path).proxy is None


def test_empty_proxy_env_means_no_proxy(tmp_path):
    assert load_settings(env={"YTDLP_PROXY": ""}, home=tmp_path).proxy is None


def test_proxy_read_from_env(tmp_path):
    env = {"YTDLP_PROXY": "socks5h://127.0.0.1:40000"}
    assert load_settings(env=env, home=tmp_path).proxy == "socks5h://127.0.0.1:40000"


def test_transport_is_stdio_unless_http_is_asked_for():
    assert load_http_settings(env={}) is None
    assert load_http_settings(env={"YTDLP_MCP_TRANSPORT": "stdio"}) is None


def test_http_transport_listens_on_loopback_by_default():
    settings = load_http_settings(env={"YTDLP_MCP_TRANSPORT": "http"})
    assert settings == HttpSettings(host="127.0.0.1", port=8642)


def test_http_host_and_port_read_from_env():
    env = {"YTDLP_MCP_TRANSPORT": "http", "YTDLP_MCP_HOST": "0.0.0.0", "YTDLP_MCP_PORT": "9000"}
    assert load_http_settings(env=env) == HttpSettings(host="0.0.0.0", port=9000)


def test_unknown_transport_is_rejected():
    with pytest.raises(ValueError, match="YTDLP_MCP_TRANSPORT"):
        load_http_settings(env={"YTDLP_MCP_TRANSPORT": "sse"})


@pytest.mark.parametrize("port", ["abc", "0", "70000"])
def test_bad_http_port_is_rejected(port):
    with pytest.raises(ValueError, match="YTDLP_MCP_PORT"):
        load_http_settings(env={"YTDLP_MCP_TRANSPORT": "http", "YTDLP_MCP_PORT": port})
