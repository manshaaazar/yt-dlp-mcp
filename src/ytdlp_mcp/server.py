"""MCP server exposing yt-dlp: downloads, transcripts, info, search and playlists."""
import asyncio
import logging
import os
import sys
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from .argv import PlaylistOptions, build_audio_argv, build_video_argv
from .config import Settings, load_settings
from .core import Downloader
from .jobs import JobManager
from .urls import is_channel_url, normalize_channel_url

WAIT_SECONDS = float(os.environ.get("YTDLP_MCP_WAIT_SECONDS", "50"))

mcp = MCPServer(
    "yt-dlp",
    instructions=(
        "Download video and audio from YouTube and 1,800+ other sites with yt-dlp. "
        "Videos are saved as MP4 to the user's Videos folder, audio as MP3 to their Music folder. "
        "Downloads run in the background: if a tool returns status 'running', call "
        "check_downloads with the job_id later. Use get_transcript to read what a video says "
        "without downloading it."
    ),
)
jobs = JobManager(max_workers=2)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
DOWNLOAD = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
JOB_STATUS = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

Url = Annotated[str, Field(description="Video URL from YouTube or any site yt-dlp supports")]
Timestamp = Annotated[
    str | None, Field(description="Clip boundary as seconds, MM:SS or HH:MM:SS. Omit for the whole video.")
]
Sponsors = Annotated[
    bool, Field(description="Cut sponsor, self-promo, intro and outro segments (SponsorBlock)")
]


def _settings(need_ffmpeg: bool = False) -> Settings:
    settings = load_settings()
    if need_ffmpeg and settings.ffmpeg is None:
        if sys.platform == "win32":
            hint = "Install it with `winget install Gyan.FFmpeg`, or set YTDLP_FFMPEG to the full path of ffmpeg.exe."
        elif sys.platform == "darwin":
            hint = "Install it with `brew install ffmpeg`, or set YTDLP_FFMPEG to the full path of ffmpeg."
        else:
            hint = "Install it with your package manager (e.g. `sudo apt install ffmpeg`), or set YTDLP_FFMPEG to the full path of ffmpeg."
        raise ToolError(f"ffmpeg not found. {hint}")
    return settings


def _arg_error(exc: ValueError) -> ToolError:
    return ToolError(str(exc))


async def _run_job(kind: str, url: str, argv: list[str], settings: Settings) -> dict[str, Any]:
    downloader = Downloader(settings)
    job = jobs.submit(kind, url, lambda job: downloader.download(url, argv, job))
    job = await jobs.wait(job.id, WAIT_SECONDS)
    if job.status == "failed":
        raise ToolError(f"Download failed: {job.error}")
    data = job.to_dict()
    if not job.finished:
        data["message"] = (
            f"Still downloading in the background. Call check_downloads(job_id='{job.id}') to see progress."
        )
    return data


@mcp.tool(annotations=DOWNLOAD)
async def download_video(
    url: Url,
    max_height: Annotated[
        int | None, Field(description="Highest resolution to allow, e.g. 1080 or 720. Omit for best available.")
    ] = None,
    start: Timestamp = None,
    end: Timestamp = None,
    remove_sponsors: Sponsors = False,
) -> dict[str, Any]:
    """Download one video as MP4 into the Videos folder, best quality by default.

    Give start and/or end to save only a clip. A link inside a playlist downloads just that video.
    Returns the saved file path, or a job_id if it is still downloading after ~50 seconds.
    """
    settings = _settings(need_ffmpeg=True)
    try:
        argv = build_video_argv(
            settings, max_height=max_height, start=start, end=end, remove_sponsors=remove_sponsors
        )
    except ValueError as exc:
        raise _arg_error(exc) from exc
    return await _run_job("video", url, argv, settings)


@mcp.tool(annotations=DOWNLOAD)
async def download_audio(
    url: Url,
    audio_format: Annotated[
        Literal["mp3", "m4a", "opus", "flac", "wav", "aac", "vorbis", "alac"],
        Field(description="Audio file format"),
    ] = "mp3",
    start: Timestamp = None,
    end: Timestamp = None,
    split_chapters: Annotated[
        bool, Field(description="Also save each chapter as its own track, e.g. to split a full-album upload")
    ] = False,
    remove_sponsors: Sponsors = False,
) -> dict[str, Any]:
    """Download one video's audio (MP3 by default) into the Music folder.

    The file gets embedded cover art, title, artist and chapter markers.
    Returns the saved file paths, or a job_id if it is still downloading after ~50 seconds.
    """
    settings = _settings(need_ffmpeg=True)
    try:
        argv = build_audio_argv(
            settings,
            audio_format=audio_format,
            start=start,
            end=end,
            split_chapters=split_chapters,
            remove_sponsors=remove_sponsors,
        )
    except ValueError as exc:
        raise _arg_error(exc) from exc
    return await _run_job("audio", url, argv, settings)


@mcp.tool(annotations=DOWNLOAD)
async def download_playlist(
    url: Annotated[str, Field(description="Playlist or channel URL")],
    mode: Annotated[Literal["video", "audio"], Field(description="Save as MP4 videos or MP3 audio")] = "video",
    limit: Annotated[
        int | None, Field(description="Download at most this many items (a channel's newest first)", ge=1)
    ] = None,
    after_date: Annotated[
        str | None, Field(description="Only items uploaded on or after this date, YYYY-MM-DD")
    ] = None,
) -> dict[str, Any]:
    """Download a playlist or channel into a subfolder named after it.

    Remembers what was already downloaded, so running it again on the same channel
    fetches only new uploads ("sync"). Usually returns a job_id; check it with check_downloads.
    """
    settings = _settings(need_ffmpeg=True)
    newest_first = is_channel_url(normalize_channel_url(url))
    options = PlaylistOptions(limit=limit, after_date=after_date, newest_first=newest_first)
    try:
        builder = build_video_argv if mode == "video" else build_audio_argv
        argv = builder(settings, playlist=options)
    except ValueError as exc:
        raise _arg_error(exc) from exc
    return await _run_job(f"playlist-{mode}", url, argv, settings)


@mcp.tool(annotations=READ_ONLY)
async def get_transcript(
    url: Url,
    lang: Annotated[str, Field(description="Language code, e.g. en, es, de")] = "en",
    offset: Annotated[int, Field(description="Character offset to continue from (use next_offset)", ge=0)] = 0,
    max_chars: Annotated[int, Field(description="Maximum characters to return", ge=1000, le=100_000)] = 40_000,
) -> dict[str, Any]:
    """Get a video's transcript as timestamped text, without downloading the video.

    Uses real subtitles when present, otherwise auto-generated captions. Long transcripts
    are paged: when next_offset is not null, call again with offset=next_offset.
    """
    downloader = Downloader(_settings())
    try:
        return await asyncio.to_thread(downloader.transcript, url, lang, offset, max_chars)
    except ValueError as exc:
        raise _arg_error(exc) from exc


@mcp.tool(annotations=READ_ONLY)
async def get_video_info(url: Url) -> dict[str, Any]:
    """Get a video's title, channel, length, upload date, chapters, available qualities and
    subtitle languages without downloading anything."""
    return await asyncio.to_thread(Downloader(_settings()).info, url)


@mcp.tool(annotations=READ_ONLY)
async def search_youtube(
    query: Annotated[str, Field(description="Search terms")],
    limit: Annotated[int, Field(description="Number of results", ge=1, le=25)] = 10,
) -> dict[str, Any]:
    """Search YouTube and return matching videos with their URLs."""
    results = await asyncio.to_thread(Downloader(_settings()).search, query, limit)
    return {"query": query, "results": results}


@mcp.tool(annotations=READ_ONLY)
async def list_playlist(
    url: Annotated[str, Field(description="Playlist or channel URL")],
    limit: Annotated[int, Field(description="Maximum entries to list", ge=1, le=500)] = 50,
) -> dict[str, Any]:
    """List the videos in a playlist or channel (newest first for channels) without downloading."""
    return await asyncio.to_thread(Downloader(_settings()).list_playlist, url, limit)


@mcp.tool(annotations=JOB_STATUS)
async def check_downloads(
    job_id: Annotated[str | None, Field(description="Job to check. Omit to list recent jobs.")] = None,
) -> dict[str, Any]:
    """Show progress or results of background downloads."""
    if job_id is None:
        return {"jobs": [job.to_dict() for job in jobs.list()[:20]]}
    job = jobs.get(job_id)
    if job is None:
        raise ToolError(f"No download job with id {job_id!r}")
    return job.to_dict()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def cancel_download(job_id: Annotated[str, Field(description="Job to cancel")]) -> dict[str, Any]:
    """Cancel a background download. Takes effect at the next progress update; a file already
    being converted by ffmpeg finishes that step first."""
    job = jobs.get(job_id)
    if job is None:
        raise ToolError(f"No download job with id {job_id!r}")
    if not jobs.cancel(job_id):
        return {"job_id": job_id, "cancelled": False, "status": job.status, "message": "Job already finished."}
    return {"job_id": job_id, "cancelled": True, "status": job.status}


def main() -> None:
    # Titles contain any Unicode; a cp1252 Windows console would choke on logging them.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("YTDLP_MCP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run()
