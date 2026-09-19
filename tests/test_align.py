"""Tests for the alignment core and the HTTP API."""

from fastapi.testclient import TestClient

from app.align import align_quotes
from app.main import app

client = TestClient(app)


# --- core: whitespace handling -------------------------------------------


def test_exact_match_offsets():
    assert align_quotes("hello world", ["hello"]) == [(0, 5)]


def test_whitespace_collapsed_but_original_offsets_returned():
    text = "a  b\t\nc"
    # Quote with single spaces matches across the whitespace runs; the
    # returned span covers the original raw characters.
    assert align_quotes(text, ["a b c"]) == [(0, 7)]
    assert text[0:7] == "a  b\t\nc"


def test_leading_and_trailing_whitespace_in_text():
    assert align_quotes("  hello  ", ["hello"]) == [(2, 7)]


def test_empty_or_blank_quote_is_not_located():
    assert align_quotes("some text", ["", "   "]) == [None, None]


def test_unlocatable_quote_returns_none():
    assert align_quotes("the quick brown fox", ["lazy dog"]) == [None]


# --- core: joint selection ------------------------------------------------


def test_repeated_quotes_get_ordered_non_overlapping_spans():
    text = "foo bar foo"
    assert align_quotes(text, ["foo", "foo"]) == [(0, 3), (8, 11)]


def test_overlapping_occurrences_do_not_overlap_in_result():
    # "aa" occurs at 0 and 1 in "aaa"; only one of the two quotes can fit.
    assert align_quotes("aaa", ["aa", "aa"]) == [(0, 2), None]


def test_touching_spans_are_allowed():
    assert align_quotes("ab", ["a", "b"]) == [(0, 1), (1, 2)]


def test_maximize_located_count_first():
    # Locating both quotes beats any single-quote selection.
    text = "aXXa b"
    assert align_quotes(text, ["a", "b"]) == [(3, 4), (5, 6)]


def test_minimize_skipped_characters_between_segments():
    # Both selections locate 2 quotes; the one skipping 0 chars wins.
    text = "aXXab"
    assert align_quotes(text, ["a", "b"]) == [(3, 4), (4, 5)]


def test_skipped_chars_only_count_between_located_segments():
    # Leading/trailing text is not part of the skip cost.
    text = "xxABxxCDxx"
    assert align_quotes(text, ["AB", "CD"]) == [(2, 4), (6, 8)]


def test_lexicographically_smallest_offsets_on_tie():
    # Two symmetric zero-skip solutions; the earlier offsets win.
    text = "abXXab"
    assert align_quotes(text, ["a", "b"]) == [(0, 1), (1, 2)]


def test_unlocatable_quote_does_not_break_order():
    text = "alpha omega"
    assert align_quotes(text, ["alpha", "missing", "omega"]) == [
        (0, 5),
        None,
        (6, 11),
    ]


def test_order_is_preserved_not_first_come_first_served():
    # Greedy per-quote matching would misplace the second quote; the joint
    # optimum keeps array order with non-overlapping spans.
    text = "b a b"
    assert align_quotes(text, ["a", "b"]) == [(2, 3), (4, 5)]


def test_empty_quote_array():
    assert align_quotes("anything", []) == []


# --- API -------------------------------------------------------------------


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_align_endpoint():
    resp = client.post(
        "/quotes/align",
        json={
            "text": "Archive  text\nwith repeats. Archive text.",
            "quotes": ["Archive text", "repeats", "Archive text", "absent"],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "results": [
            {"start": 0, "end": 13},
            {"start": 19, "end": 26},
            {"start": 28, "end": 40},
            None,
        ]
    }


def test_align_endpoint_rejects_bad_payload():
    resp = client.post("/quotes/align", json={"text": "x"})
    assert resp.status_code == 422
