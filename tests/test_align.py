"""Tests for the alignment core and the HTTP API."""

from fastapi.testclient import TestClient

from app.align import align_quotes, align_quotes_fuzzy
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


# --- core: fuzzy matching --------------------------------------------------


def _f(quote, budget):
    """Shorthand for a (quote text, max edits) pair."""
    return (quote, budget)


def test_fuzzy_exact_match_has_zero_distance():
    assert align_quotes_fuzzy("hello world", [_f("hello", 1)]) == [(0, 5, 0)]


def test_fuzzy_budget_zero_behaves_like_exact():
    text = "Archive  text\nwith repeats."
    fuzzy = align_quotes_fuzzy(
        text, [_f("Archive text", 0), _f("repeats", 0), _f("nope", 0)]
    )
    exact = align_quotes(text, ["Archive text", "repeats", "nope"])
    assert [None if s is None else (s[0], s[1]) for s in fuzzy] == exact
    assert fuzzy == [(0, 13, 0), (19, 26, 0), None]


def test_fuzzy_one_substitution():
    # "hallo" vs "hello" differs in one character.
    assert align_quotes_fuzzy("hello", [_f("hallo", 1)]) == [(0, 5, 1)]


def test_fuzzy_fragment_longer_than_quote():
    # "heello" vs "hello": one extra character inside the fragment.
    assert align_quotes_fuzzy("heello", [_f("hello", 1)]) == [(0, 6, 1)]


def test_fuzzy_fragment_shorter_than_quote():
    # "hello" vs "hellox": the quote carries one extra trailing character.
    assert align_quotes_fuzzy("hello", [_f("hellox", 1)]) == [(0, 5, 1)]


def test_fuzzy_distance_exceeding_budget_is_null():
    # "hxxlo" vs "hello" needs two substitutions, budget is one.
    assert align_quotes_fuzzy("hello", [_f("hxxlo", 1)]) == [None]


def test_fuzzy_distance_within_budget_two():
    assert align_quotes_fuzzy("hello", [_f("hxxlo", 2)]) == [(0, 5, 2)]


def test_fuzzy_returns_original_offsets_after_whitespace_collapse():
    text = "a  b\t\nc d"
    # "ab c" ~ normalized "a b c" via one deletion; the span covers the
    # raw whitespace runs between the matched characters.
    assert align_quotes_fuzzy(text, [_f("ab c", 1)]) == [(0, 7, 1)]
    assert text[0:7] == "a  b\t\nc"


def test_fuzzy_unicode_code_points_count_one_each():
    # One CJK substitution must cost exactly 1, not 3 (UTF-8 bytes); the
    # strings are chosen so no shorter/longer fragment can also fit the
    # budget, making the full-length substitution the unique optimum.
    assert align_quotes_fuzzy("你好世界！", [_f("你好星界", 1)]) == [(0, 4, 1)]
    # Emoji code points are units too.
    assert align_quotes_fuzzy("x😀ab", [_f("x😀cb", 1)]) == [(0, 4, 1)]


def test_fuzzy_blank_quote_is_null():
    assert align_quotes_fuzzy("some text", [_f("", 2), _f("   ", 1)]) == [
        None,
        None,
    ]


def test_fuzzy_joint_ordered_non_overlapping():
    text = "foo bar foo"
    # "fx" matches at distance 1 wherever "f"/"fo" occurs; the two located
    # fragments stay ordered and disjoint.
    assert align_quotes_fuzzy(text, [_f("fx", 1), _f("fx", 1)]) == [
        (0, 2, 1),
        (8, 9, 1),
    ]


def test_fuzzy_count_beats_edit_distance():
    # Locating both quotes (distance 1 total) beats one exact match.
    text = "aX"
    assert align_quotes_fuzzy(text, [_f("a", 0), _f("Y", 2)]) == [
        (0, 1, 0),
        (1, 2, 1),
    ]


def test_fuzzy_edit_distance_outranks_gap():
    # "ax" has no exact placement in "xxbcd": (0,2) "xx" costs 1 but leaves
    # a gap of 1 before "cd", whereas a touching fragment near "cd" costs 2.
    # Total edit distance is minimized before the gap, so the distance-1
    # placement with the larger gap wins.
    text = "xxbcd"
    assert align_quotes_fuzzy(text, [_f("ax", 2), _f("cd", 0)]) == [
        (0, 2, 1),
        (3, 5, 0),
    ]


def test_fuzzy_smaller_gap_wins_on_equal_distance():
    # In "xaaa cd" every within-budget placement of "ax" costs exactly 1;
    # the fragment touching "cd" leaves the smallest gap and wins even
    # though later occurrences also qualify.
    text = "xaaa cd"
    assert align_quotes_fuzzy(text, [_f("ax", 1), _f("cd", 0)]) == [
        (3, 5, 1),
        (5, 7, 0),
    ]


def test_fuzzy_earliest_offsets_on_full_tie():
    # Two symmetric distance-2 zero-gap solutions, mirroring the exact
    # tie-break test: earliest offset sequence wins.
    text = "abXXab"
    assert align_quotes_fuzzy(text, [_f("ax", 1), _f("bx", 1)]) == [
        (0, 1, 1),
        (1, 2, 1),
    ]


def test_fuzzy_empty_quote_array():
    assert align_quotes_fuzzy("anything", []) == []


def test_fuzzy_overlapping_candidates_jointly_disjoint():
    # "aaa", quote "aa" with budget 1: feasible fragments include the
    # exact length-2 windows (distance 0) and length-1 windows (distance
    # 1). Total distance ties between a (len1,len2) and a (len2,len1)
    # placement; the earliest offset sequence wins, and the spans never
    # overlap (touching at offset 1 is allowed).
    assert align_quotes_fuzzy("aaa", [_f("aa", 1), _f("aa", 1)]) == [
        (0, 1, 1),
        (1, 3, 0),
    ]


def test_fuzzy_unlocatable_middle_quote_keeps_order():
    text = "alpha omega"
    assert align_quotes_fuzzy(
        text, [_f("alpha", 0), _f("zzzzzzzzzz", 2), _f("omega", 0)]
    ) == [(0, 5, 0), None, (6, 11, 0)]


# --- API: fuzzy endpoint ---------------------------------------------------


def test_align_fuzzy_endpoint():
    resp = client.post(
        "/quotes/align-fuzzy",
        json={
            "text": "Archive  text\nwith repeats. Archive text.",
            "quotes": [
                {"text": "Archiv text", "max_edits": 1},
                {"text": "repeets", "max_edits": 1},
                {"text": "Archive text", "max_edits": 0},
                {"text": "zzzzzzzzzzz", "max_edits": 2},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0] == {"start": 0, "end": 13, "edit_distance": 1}
    assert body["results"][1] == {"start": 19, "end": 26, "edit_distance": 1}
    assert body["results"][2] == {"start": 28, "end": 40, "edit_distance": 0}
    assert body["results"][3] is None


def test_align_fuzzy_endpoint_default_text_required():
    resp = client.post("/quotes/align-fuzzy", json={"quotes": []})
    assert resp.status_code == 422


def test_align_fuzzy_endpoint_rejects_missing_max_edits():
    resp = client.post(
        "/quotes/align-fuzzy",
        json={"text": "hello", "quotes": [{"text": "hello"}]},
    )
    assert resp.status_code == 422


def test_align_fuzzy_endpoint_rejects_out_of_range_budget():
    for bad in (-1, 3):
        resp = client.post(
            "/quotes/align-fuzzy",
            json={"text": "hello", "quotes": [{"text": "hello", "max_edits": bad}]},
        )
        assert resp.status_code == 422

