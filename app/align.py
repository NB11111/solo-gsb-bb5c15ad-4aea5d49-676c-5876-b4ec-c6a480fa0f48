"""Core quote-alignment logic.

Matching is performed on whitespace-normalized text (every run of whitespace
is treated as a single space), while the returned offsets always refer to the
original, unmodified text.

Quotes are located jointly: the chosen spans must not overlap and must keep
the order of the quote array. Among all feasible selections we

1. maximize the number of located quotes,
2. minimize the total number of original characters skipped between located
   segments (characters before the first / after the last located segment do
   not count),
3. take the lexicographically smallest offset sequence.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache

_WS_RUN = re.compile(r"\s+")

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


def _select_spans(
    candidates: list[list[tuple[int, int]]],
) -> list[tuple[int, int] | None]:
    """Jointly pick at most one span per quote.

    ``candidates[i]`` holds the feasible spans for quote ``i``, sorted by
    offset. Returns one span (or ``None``) per quote.
    """
    n = len(candidates)

    def rank(option: tuple[int, int, tuple]) -> tuple:
        count, skip, seq = option
        return (-count, skip, seq)

    @lru_cache(maxsize=None)
    def dp(i: int, prev_end: int) -> tuple[int, int, tuple]:
        # Best (located_count, skipped_chars, span_sequence) for quotes[i:],
        # given the previously located segment ends at prev_end (-1: none yet).
        if i == n:
            return (0, 0, ())

        best = None
        for start, end in candidates[i]:
            if prev_end != -1 and start < prev_end:
                continue
            count, skip, seq = dp(i + 1, end)
            gap = 0 if prev_end == -1 else start - prev_end
            option = (count + 1, skip + gap, ((start, end),) + seq)
            if best is None or rank(option) < rank(best):
                best = option

        # Leave quote i unlocated.
        count, skip, seq = dp(i + 1, prev_end)
        option = (count, skip, seq)
        if best is None or rank(option) < rank(best):
            best = option
        return best

    # Reconstruct which candidate (if any) realizes the optimum per quote.
    result: list[tuple[int, int] | None] = [None] * n
    prev_end = -1
    for i in range(n):
        best = dp(i, prev_end)
        for start, end in candidates[i]:
            if prev_end != -1 and start < prev_end:
                continue
            count, skip, seq = dp(i + 1, end)
            gap = 0 if prev_end == -1 else start - prev_end
            if (count + 1, skip + gap, ((start, end),) + seq) == best:
                result[i] = (start, end)
                prev_end = end
                break
    return result


def align_quotes(text: str, quotes: list[str]) -> list[tuple[int, int] | None]:
    """Locate every quote in ``text``.

    Returns a list parallel to ``quotes``; each entry is a ``(start, end)``
    pair of character offsets into the original text (end-exclusive), or
    ``None`` when the quote could not be located.
    """
    norm_text, norm_to_orig = _normalize_with_map(text)
    candidates = [
        _candidate_spans(norm_text, norm_to_orig, quote) for quote in quotes
    ]
    return _select_spans(candidates)
