"""Core quote-alignment logic.

Matching is performed on whitespace-normalized text (every run of whitespace
is treated as a single space), while the returned offsets always refer to the
original, unmodified text.

Two matching modes share the same joint selection:

* exact (``align_quotes``): a quote must appear verbatim after normalization;
* fuzzy (``align_quotes_fuzzy``): each quote carries a per-quote edit budget
  (0-2); a source fragment is feasible when its Unicode code point
  Levenshtein distance (insert / delete / substitute each cost 1) from the
  normalized quote stays within that budget.

Quotes are located jointly: the chosen spans must not overlap and must keep
the order of the quote array. Among all feasible selections we

1. maximize the number of located quotes,
2. (fuzzy only) minimize the total Levenshtein edit distance,
3. minimize the total number of original characters skipped between located
   segments (characters before the first / after the last located segment do
   not count),
4. take the lexicographically smallest offset sequence.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache

_WS_RUN = re.compile(r"\s+")

# Fuzzy quotes may relax the match by at most this many edits.
MAX_EDIT_BUDGET = 2

# The dynamic program recurses once per quote; lift the default recursion
# limit so long quote arrays stay solvable.
sys.setrecursionlimit(max(sys.getrecursionlimit(), 100_000))


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse every whitespace run to a single space.

    Returns the normalized string plus a list mapping each normalized
    character index to its index in the original text.
    """
    norm_chars: list[str] = []
    norm_to_orig: list[int] = []
    pos = 0
    for match in _WS_RUN.finditer(text):
        norm_chars.extend(text[pos : match.start()])
        norm_to_orig.extend(range(pos, match.start()))
        # The whole run becomes one space, mapped to the run's first char.
        norm_chars.append(" ")
        norm_to_orig.append(match.start())
        pos = match.end()
    norm_chars.extend(text[pos:])
    norm_to_orig.extend(range(pos, len(text)))
    return "".join(norm_chars), norm_to_orig


def _find_all(haystack: str, needle: str) -> list[int]:
    """All start offsets of ``needle`` in ``haystack``, including overlaps."""
    starts = []
    i = haystack.find(needle)
    while i != -1:
        starts.append(i)
        i = haystack.find(needle, i + 1)
    return starts


def _candidate_spans(
    norm_text: str, norm_to_orig: list[int], quote: str
) -> list[tuple[int, int]]:
    """Sorted original-text [start, end) spans where ``quote`` may be located."""
    norm_quote, _ = _normalize_with_map(quote)
    if not norm_quote.strip():
        # Empty or whitespace-only quotes carry no content to locate.
        return []
    spans = set()
    for start in _find_all(norm_text, norm_quote):
        end = start + len(norm_quote)
        spans.add((norm_to_orig[start], norm_to_orig[end - 1] + 1))
    return sorted(spans)


def _fuzzy_candidate_spans(
    norm_text: str,
    norm_to_orig: list[int],
    quote: str,
    max_edits: int,
) -> list[tuple[int, int, int]]:
    """Sorted ``(start, end, edit_distance)`` fuzzy candidates for ``quote``.

    Enumerates non-empty substrings of the normalized source whose length
    differs from the normalized quote by at most ``max_edits`` and whose
    Levenshtein distance (Unicode code point granularity) is within budget.
    Offsets are mapped back to the original text, exactly as for exact
    matching.
    """
    norm_quote, _ = _normalize_with_map(quote)
    if not norm_quote.strip():
        return []

    m = len(norm_quote)
    n = len(norm_text)
    min_len = max(1, m - max_edits)
    max_len = m + max_edits
    if n < min_len:
        return []

    spans: set[tuple[int, int, int]] = set()
    for s in range(n - min_len + 1):
        window = norm_text[s : s + max_len]
        # Standard Levenshtein DP with the quote along the row; after
        # consuming j window characters row[-1] is the distance between the
        # quote and the prefix window[:j], i.e. normalized span [s, s+j).
        row = list(range(m + 1))
        for j in range(1, len(window) + 1):
            prev = row
            row = [j] + [0] * m
            for i in range(1, m + 1):
                cost = norm_quote[i - 1] != window[j - 1]
                row[i] = min(
                    prev[i] + 1,          # delete from quote
                    row[i - 1] + 1,       # insert into quote
                    prev[i - 1] + cost,   # match / substitute
                )
            distance = row[m]
            if j >= min_len and distance <= max_edits:
                spans.add(
                    (
                        norm_to_orig[s],
                        norm_to_orig[s + j - 1] + 1,
                        distance,
                    )
                )
            # If every live prefix already exceeds the budget, later columns
            # cannot recover: all subsequent rows stay above the budget.
            if min(row[1:]) > max_edits:
                break
    return sorted(spans)


def _select_spans(
    candidates: list[list[tuple]],
    extra_costs: int = 0,
) -> list[tuple | None]:
    """Jointly pick at most one candidate span per quote.

    ``candidates[i]`` holds the feasible candidates for quote ``i`` as
    ``(start, end, *own_costs)`` tuples sorted by offset. The optimization
    ranks by (located count desc, own cost totals asc, skipped-character
    total asc, offset sequence asc); ``extra_costs`` says how many candidate
    cost components precede the structural gap cost (0 for exact matching,
    1 for fuzzy edit distance).

    Returns one candidate tuple (or ``None``) per quote.
    """
    n = len(candidates)
    costs_len = extra_costs + 1  # last cost coordinate is the inter-segment gap
    zero_costs = (0,) * costs_len

    def rank(option: tuple[int, tuple, tuple]) -> tuple:
        count, costs, seq = option
        return (-count,) + costs + (seq,)

    @lru_cache(maxsize=None)
    def dp(
        i: int, prev_end: int
    ) -> tuple[int, tuple[int, ...], tuple]:
        # Best (located_count, cost_totals, span_sequence) for quotes[i:],
        # given the previously located segment ends at prev_end (-1: none yet).
        if i == n:
            return (0, zero_costs, ())

        best = None
        for cand in candidates[i]:
            start, end = cand[0], cand[1]
            if prev_end != -1 and start < prev_end:
                continue
            count, costs, seq = dp(i + 1, end)
            gap = 0 if prev_end == -1 else start - prev_end
            own = cand[2:]
            totals = tuple(
                own[j] + costs[j] for j in range(extra_costs)
            ) + (costs[-1] + gap,)
            option = (count + 1, totals, ((start, end),) + seq)
            if best is None or rank(option) < rank(best):
                best = option

        # Leave quote i unlocated.
        option = dp(i + 1, prev_end)
        if best is None or rank(option) < rank(best):
            best = option
        return best

    # Reconstruct which candidate (if any) realizes the optimum per quote.
    result: list[tuple | None] = [None] * n
    prev_end = -1
    for i in range(n):
        best = dp(i, prev_end)
        for cand in candidates[i]:
            start, end = cand[0], cand[1]
            if prev_end != -1 and start < prev_end:
                continue
            count, costs, seq = dp(i + 1, end)
            gap = 0 if prev_end == -1 else start - prev_end
            own = cand[2:]
            totals = tuple(
                own[j] + costs[j] for j in range(extra_costs)
            ) + (costs[-1] + gap,)
            if (count + 1, totals, ((start, end),) + seq) == best:
                result[i] = cand
                prev_end = end
                break
    return result


def align_quotes(text: str, quotes: list[str]) -> list[tuple[int, int] | None]:
    """Locate every quote in ``text`` with exact (post-normalization) match.

    Returns a list parallel to ``quotes``; each entry is a ``(start, end)``
    pair of character offsets into the original text (end-exclusive), or
    ``None`` when the quote could not be located.
    """
    norm_text, norm_to_orig = _normalize_with_map(text)
    candidates = [
        _candidate_spans(norm_text, norm_to_orig, quote) for quote in quotes
    ]
    return [
        None if cand is None else (cand[0], cand[1])
        for cand in _select_spans(candidates)
    ]


def align_quotes_fuzzy(
    text: str, quotes: list[tuple[str, int]]
) -> list[tuple[int, int, int] | None]:
    """Locate every quote in ``text`` allowing a per-quote edit budget.

    ``quotes`` pairs each quote text with its maximum Levenshtein distance
    (0-2). Returns a list parallel to ``quotes``; each entry is a
    ``(start, end, edit_distance)`` triple of original-text character offsets
    (end-exclusive) and the distance paid, or ``None`` when the quote could
    not be located.
    """
    norm_text, norm_to_orig = _normalize_with_map(text)
    candidates = [
        _fuzzy_candidate_spans(norm_text, norm_to_orig, quote, max_edits)
        for quote, max_edits in quotes
    ]
    return [
        None if cand is None else (cand[0], cand[1], cand[2])
        for cand in _select_spans(candidates, extra_costs=1)
    ]
