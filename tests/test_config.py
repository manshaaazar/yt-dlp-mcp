import os
from pathlib import Path

from ytdlp_mcp.config import Settings, ensure_dirs, ensure_on_path, find_ffmpeg, load_settings


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
