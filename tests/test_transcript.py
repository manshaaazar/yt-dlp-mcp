from ytdlp_mcp.transcript import (
    format_transcript,
    group_paragraphs,
    page,
    parse_json3,
    parse_vtt,
    pick_track,
)

JSON3_AUTO = {
    "events": [
        {"tStartMs": 0, "dDurationMs": 5000, "id": 1, "wpWinPosId": 1},
        {"tStartMs": 120, "dDurationMs": 4000, "segs": [{"utf8": "hello"}, {"utf8": " there", "tOffsetMs": 400}]},
        {"tStartMs": 2000, "dDurationMs": 2000, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 4100, "dDurationMs": 3000, "segs": [{"utf8": "general"}, {"utf8": " kenobi"}]},
        {"tStartMs": 9000, "dDurationMs": 1000, "segs": [{"utf8": "  "}]},
    ]
}


def test_parse_json3_joins_segments_and_skips_blank_events():
    assert parse_json3(JSON3_AUTO) == [(0.12, "hello there"), (4.1, "general kenobi")]


VTT_ROLLING = """WEBVTT
Kind: captions
Language: en

00:00:00.120 --> 00:00:02.000 align:start position:0%
hello<00:00:00.500><c> there</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
hello there

00:00:02.010 --> 00:00:04.100 align:start position:0%
hello there
general<00:00:04.000><c> kenobi</c>

00:00:04.100 --> 00:00:05.000
general kenobi
"""


def test_parse_vtt_strips_tags_and_drops_rolling_repeats():
    assert parse_vtt(VTT_ROLLING) == [(0.12, "hello there"), (2.01, "general kenobi")]


def test_parse_vtt_handles_short_timestamps():
    vtt = "WEBVTT\n\n01:05.000 --> 01:07.000\n<b>Bold</b> &amp; plain\n"
    assert parse_vtt(vtt) == [(65.0, "Bold & plain")]


def _fmt(ext):
    return {"ext": ext, "url": f"https://example/{ext}"}


def test_pick_track_prefers_manual_subtitles():
    subs = {"en": [_fmt("vtt"), _fmt("json3")]}
    auto = {"en": [_fmt("json3")]}
    source, lang, fmt = pick_track(subs, auto, "en")
    assert (source, lang, fmt["ext"]) == ("subtitles", "en", "json3")


def test_pick_track_matches_regional_variant():
    source, lang, _ = pick_track({"en-US": [_fmt("vtt")]}, {}, "en")
    assert (source, lang) == ("subtitles", "en-US")


def test_pick_track_prefers_original_auto_captions_over_translated():
    auto = {"en": [_fmt("json3")], "en-orig": [_fmt("json3")], "fr": [_fmt("json3")]}
    source, lang, _ = pick_track({}, auto, "en")
    assert (source, lang) == ("automatic_captions", "en-orig")


def test_pick_track_ignores_live_chat_and_unknown_formats():
    subs = {"live_chat": [_fmt("json")], "en": [_fmt("ttml")]}
    assert pick_track(subs, {}, "en") is None


def test_pick_track_returns_none_when_language_missing():
    assert pick_track({"de": [_fmt("vtt")]}, {}, "en") is None


def test_group_paragraphs_merges_lines_within_window():
    segments = [(0.0, "a"), (10.0, "b"), (29.0, "c"), (31.0, "d"), (65.0, "e")]
    assert group_paragraphs(segments, window=30) == [(0.0, "a b c"), (31.0, "d"), (65.0, "e")]


def test_format_transcript_uses_mmss_and_hours_when_needed():
    text = format_transcript([(5.0, "intro"), (3725.0, "late")])
    assert text == "[0:00:05] intro\n[1:02:05] late"
    assert format_transcript([(65.0, "x")]) == "[01:05] x"


def test_page_cuts_on_line_boundary_and_reports_next_offset():
    text = "line one\nline two\nline three"
    first = page(text, offset=0, max_chars=12)
    assert first["text"] == "line one\n"
    assert first["next_offset"] == 9
    assert first["total_chars"] == len(text)
    rest = page(text, offset=first["next_offset"], max_chars=100)
    assert rest["text"] == "line two\nline three"
    assert rest["next_offset"] is None


def test_page_hard_cuts_single_long_line():
    result = page("x" * 50, offset=0, max_chars=20)
    assert result["text"] == "x" * 20
    assert result["next_offset"] == 20
