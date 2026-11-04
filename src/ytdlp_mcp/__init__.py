"""MCP server for yt-dlp."""


def main() -> None:
    from .server import main as run

    run()
