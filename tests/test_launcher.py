"""run-podman.sh builds the right `podman run` for each transport.

Podman itself is replaced by a stub that prints its arguments, so this checks the
command the launcher would run without starting a container.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run-podman.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell launcher")


def _podman_args(tmp_path, **env) -> list[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_podman = fake_bin / "podman"
    fake_podman.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake_podman.chmod(0o755)
    run_env = {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path), **env}
    result = subprocess.run(["sh", str(SCRIPT)], env=run_env, capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def _value_after(args, flag):
    return args[args.index(flag) + 1]


def _env_passed(args) -> set[str]:
    return {args[i + 1] for i, arg in enumerate(args) if arg == "-e"}


def test_stdio_launch_gets_a_private_container_per_client(tmp_path):
    args = _podman_args(tmp_path)
    assert "-i" in args
    assert "-p" not in args
    assert _value_after(args, "--name").startswith("ytdlp-mcp-")


def test_http_launch_is_one_named_container_published_on_loopback(tmp_path):
    args = _podman_args(tmp_path, YTDLP_MCP_TRANSPORT="http")
    assert _value_after(args, "--name") == "ytdlp-mcp"
    assert "--replace" in args
    assert _value_after(args, "-p") == "127.0.0.1:8642:8642"
    assert {"YTDLP_MCP_TRANSPORT=http", "YTDLP_MCP_HOST=0.0.0.0", "YTDLP_MCP_PORT=8642"} <= _env_passed(args)


def test_http_launch_leaves_logging_to_whoever_started_it(tmp_path):
    # The service manager already records the launcher's output; Podman's own log
    # driver would store every line a second time.
    args = _podman_args(tmp_path, YTDLP_MCP_TRANSPORT="http")
    assert _value_after(args, "--log-driver") == "none"


def test_http_port_is_configurable(tmp_path):
    args = _podman_args(tmp_path, YTDLP_MCP_TRANSPORT="http", YTDLP_MCP_PORT="9000")
    assert _value_after(args, "-p") == "127.0.0.1:9000:9000"
    assert "YTDLP_MCP_PORT=9000" in _env_passed(args)
