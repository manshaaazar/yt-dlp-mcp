import pytest

from ytdlp_mcp.urls import is_channel_url, normalize_channel_url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/@veritasium", "https://www.youtube.com/@veritasium/videos"),
        ("https://youtube.com/@veritasium/", "https://youtube.com/@veritasium/videos"),
        ("https://www.youtube.com/channel/UC123abc", "https://www.youtube.com/channel/UC123abc/videos"),
        ("https://www.youtube.com/c/SomeName", "https://www.youtube.com/c/SomeName/videos"),
        ("https://www.youtube.com/user/old", "https://www.youtube.com/user/old/videos"),
        ("https://www.youtube.com/@veritasium/shorts", "https://www.youtube.com/@veritasium/shorts"),
        ("https://www.youtube.com/@veritasium/videos", "https://www.youtube.com/@veritasium/videos"),
        ("https://www.youtube.com/playlist?list=PL1", "https://www.youtube.com/playlist?list=PL1"),
        ("https://www.youtube.com/watch?v=abc", "https://www.youtube.com/watch?v=abc"),
        ("https://vimeo.com/@someone", "https://vimeo.com/@someone"),
    ],
)
def test_normalize_channel_url(url, expected):
    assert normalize_channel_url(url) == expected


def test_is_channel_url():
    assert is_channel_url("https://www.youtube.com/@x/videos")
    assert not is_channel_url("https://www.youtube.com/playlist?list=PL1")
