"""Serve the real server over streamable HTTP, the way one shared container does.

A single long-lived server answers every MCP client, so downloads started by one
client must be visible to the others, and the endpoint must only answer requests
addressed to localhost even though the container binds 0.0.0.0.
"""
import asyncio
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from test_stdio import EXPECTED_TOOLS

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def port(tmp_path):
    """Run `python -m ytdlp_mcp` in HTTP mode and yield the port it listens on."""
    port = _free_port()
    env = dict(os.environ)
    env.update(
        YTDLP_MCP_TRANSPORT="http",
        YTDLP_MCP_HOST="0.0.0.0",  # what the container binds; its port is published on loopback only
        YTDLP_MCP_PORT=str(port),
        YTDLP_VIDEO_DIR=str(tmp_path / "Videos"),
        YTDLP_AUDIO_DIR=str(tmp_path / "Music"),
        YTDLP_MCP_DATA_DIR=str(tmp_path / "data"),
    )
    log = (tmp_path / "server.log").open("w+")
    proc = subprocess.Popen(
        [sys.executable, "-m", "ytdlp_mcp"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            if proc.poll() is not None:
                log.seek(0)
                pytest.fail(f"server exited with code {proc.returncode} instead of serving HTTP:\n{log.read()[-2000:]}")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail("server did not start listening within 30s")
                time.sleep(0.1)
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


async def _with_session(port, fn):
    async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _post_initialize(port, host_header) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("POST", "/mcp", skip_host=True)
        conn.putheader("Host", host_header)
        body = json.dumps(INITIALIZE).encode()
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Accept", "application/json, text/event-stream")
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        return conn.getresponse().status
    finally:
        conn.close()


def test_lists_all_tools_over_http(port):
    async def run(session):
        return {t.name for t in (await session.list_tools()).tools}

    assert asyncio.run(_with_session(port, run)) == EXPECTED_TOOLS


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="download tools need ffmpeg")
def test_download_started_by_one_client_is_visible_to_another(port):
    async def start(session):
        # Not a URL, so yt-dlp rejects it without touching the network.
        return await session.call_tool("download_video", {"url": "not a url"})

    async def list_jobs(session):
        return (await session.call_tool("check_downloads", {})).structured_content

    started = asyncio.run(_with_session(port, start))
    assert started.is_error  # the job itself fails; what matters is that it was recorded

    seen_by_other_client = asyncio.run(_with_session(port, list_jobs))
    assert [(job["url"], job["status"]) for job in seen_by_other_client["jobs"]] == [("not a url", "failed")]


def test_only_answers_requests_addressed_to_localhost(port):
    # Bound to 0.0.0.0 inside the container, so the Host check is what stops a
    # web page from reaching the server through DNS rebinding.
    assert _post_initialize(port, f"127.0.0.1:{port}") == 200
    assert _post_initialize(port, f"evil.example:{port}") == 421
