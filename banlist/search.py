"""Card title search with accent folding and light fuzzy matching."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from banlist.models import Card


def normalize_text(value: str) -> str:
    """Lowercase text, strip accents, and replace punctuation with spaces.

    Args:
        value: Raw card title or search query.

    Returns:
        Normalized whitespace-separated ASCII-ish string.
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = without_marks.lower()
    spaced = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(spaced.split())


def _token_match(query_norm: str, title_norm: str) -> bool:
    if not query_norm:
        return False
    if query_norm in title_norm:
        return True
    tokens = query_norm.split()
    return bool(tokens) and all(token in title_norm for token in tokens)


def _partial_ratio(query_norm: str, title_norm: str) -> float:
    if not query_norm or not title_norm:
        return 0.0
    if query_norm in title_norm:
        return 1.0
    if len(query_norm) >= len(title_norm):
        return SequenceMatcher(None, query_norm, title_norm).ratio()

    best = SequenceMatcher(None, query_norm, title_norm).ratio()
    window = len(query_norm)
    step = max(1, window // 4)
    for i in range(0, len(title_norm) - window + 1, step):
        chunk = title_norm[i : i + window]
        best = max(best, SequenceMatcher(None, query_norm, chunk).ratio())
        if best >= 0.95:
            break
    return best


def search_cards(query: str, limit: int = 25) -> list[Card]:
    """Find Standard-pool cards by title using normalized and fuzzy matching.

    Args:
        query: User search string (accents optional).
        limit: Maximum number of cards to return.

    Returns:
        Matching cards, best matches first. Empty if nothing qualifies.
    """
    query_norm = normalize_text(query)
    if not query_norm:
        return []

    cards = Card.query.filter_by(in_standard_pool=True).all()

    exactish: list[tuple[int, str, Card]] = []
    for card in cards:
        title_norm = normalize_text(card.title)
        if _token_match(query_norm, title_norm):
            pos = title_norm.find(query_norm.split()[0])
            exactish.append((pos if pos >= 0 else 999, title_norm, card))

    if exactish:
        exactish.sort(key=lambda row: (row[0], len(row[1]), row[2].title))
        return [card for _, _, card in exactish[:limit]]

    fuzzy: list[tuple[float, Card]] = []
    for card in cards:
        title_norm = normalize_text(card.title)
        score = _partial_ratio(query_norm, title_norm)
        if score >= 0.72:
            fuzzy.append((score, card))

    fuzzy.sort(key=lambda row: (-row[0], row[1].title))
    return [card for _, card in fuzzy[:limit]]
