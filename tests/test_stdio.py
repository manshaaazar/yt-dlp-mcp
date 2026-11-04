"""Launch the real server over stdio, the way Claude Code does.

Catches anything that writes to stdout and corrupts the JSON-RPC stream.
"""
import asyncio
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "download_video",
    "download_audio",
    "get_transcript",
    "get_video_info",
    "search_youtube",
    "list_playlist",
    "download_playlist",
    "check_downloads",
    "cancel_download",
}


def _params(tmp_path, **extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    env["YTDLP_VIDEO_DIR"] = str(tmp_path / "Videos")
    env["YTDLP_AUDIO_DIR"] = str(tmp_path / "Music")
    env["YTDLP_MCP_DATA_DIR"] = str(tmp_path / "data")
    return StdioServerParameters(command=sys.executable, args=["-m", "ytdlp_mcp"], env=env)


async def _with_session(tmp_path, fn, **extra_env):
    async with stdio_client(_params(tmp_path, **extra_env)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def test_lists_all_tools(tmp_path):
    async def run(session):
        return {t.name for t in (await session.list_tools()).tools}

    assert asyncio.run(_with_session(tmp_path, run)) == EXPECTED_TOOLS


@pytest.mark.live
def test_video_info_over_stdio(tmp_path):
    async def run(session):
        return await session.call_tool(
            "get_video_info", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
        )

    result = asyncio.run(_with_session(tmp_path, run))
    assert not result.is_error, result.content
    assert result.structured_content["title"] == "Me at the zoo"


@pytest.mark.live
def test_audio_download_over_stdio(tmp_path):
    async def run(session):
        return await session.call_tool(
            "download_audio", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
        )

    result = asyncio.run(_with_session(tmp_path, run))
    assert not result.is_error, result.content
    data = result.structured_content
    assert data["status"] == "done"
    assert data["files"][0]["path"].endswith(".mp3")


GIT_100S = "https://www.youtube.com/watch?v=hwP7WQkmECE"  # 2 minutes


async def _poll_until_finished(session, job_id, timeout=300):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        status = (await session.call_tool("check_downloads", {"job_id": job_id})).structured_content
        if status["status"] in ("done", "failed", "cancelled"):
            return status
        await asyncio.sleep(1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


@pytest.mark.live
def test_long_download_returns_job_then_finishes(tmp_path):
    async def run(session):
        started = await session.call_tool("download_video", {"url": GIT_100S, "max_height": 360})
        assert not started.is_error, started.content
        first = started.structured_content
        final = await _poll_until_finished(session, first["job_id"])
        return first, final

    first, final = asyncio.run(_with_session(tmp_path, run, YTDLP_MCP_WAIT_SECONDS="1"))
    assert first["status"] in ("queued", "running")
    assert "check_downloads" in first["message"]
    assert final["status"] == "done", final
    mp4 = final["files"][0]["path"]
    assert mp4.endswith(".mp4") and os.path.isfile(mp4)


@pytest.mark.live
def test_cancel_stops_background_download(tmp_path):
    async def run(session):
        started = (await session.call_tool("download_video", {"url": GIT_100S})).structured_content
        cancel = (await session.call_tool("cancel_download", {"job_id": started["job_id"]})).structured_content
        final = await _poll_until_finished(session, started["job_id"])
        return cancel, final

    cancel, final = asyncio.run(_with_session(tmp_path, run, YTDLP_MCP_WAIT_SECONDS="1"))
    assert cancel["cancelled"] is True
    assert final["status"] == "cancelled", final
    assert not list((tmp_path / "Videos").glob("*.mp4"))
