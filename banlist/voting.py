"""Vote helpers, weighted card selection, and banlist aggregates."""

from __future__ import annotations

import secrets
from random import choices

from flask import current_app, request
from sqlalchemy import case, func

from banlist import db
from banlist.models import Card, Vote, utcnow


def get_or_create_voter_id() -> tuple[str, str | None]:
    """Read the voter cookie or allocate a new anonymous id.

    Returns:
        A pair ``(voter_id, new_cookie_value_or_None)``. The second element is
        set only when a new id was created and must be written to the response.
    """
    name = current_app.config["VOTER_COOKIE_NAME"]
    existing = request.cookies.get(name)
    if existing:
        return existing, None
    new_id = secrets.token_urlsafe(24)
    return new_id, new_id


def attach_voter_cookie(response, voter_id: str, is_new: bool):
    """Optionally set the anonymous voter cookie on a response.

    Args:
        response: Flask response object to mutate.
        voter_id: Cookie value to store.
        is_new: If False, the response is returned unchanged.

    Returns:
        The same response, possibly with ``Set-Cookie`` applied.
    """
    if not is_new:
        return response
    response.set_cookie(
        current_app.config["VOTER_COOKIE_NAME"],
        voter_id,
        max_age=current_app.config["VOTER_COOKIE_MAX_AGE"],
        httponly=True,
        samesite="Lax",
    )
    return response


def _controversy(ban_count: int, total: int) -> float | None:
    if total <= 0:
        return None
    p = ban_count / total
    return 4.0 * p * (1.0 - p)


def _vote_tallies() -> dict[int, tuple[int, int]]:
    rows = (
        db.session.query(
            Vote.card_id,
            func.sum(case((Vote.wants_ban.is_(True), 1), else_=0)),
            func.count(Vote.id),
        )
        .group_by(Vote.card_id)
        .all()
    )
    return {
        int(card_id): (int(ban_count or 0), int(total or 0)) for card_id, ban_count, total in rows
    }


def _card_weight(
    card: Card,
    ban_count: int,
    total: int,
    community_banned_ids: set[int],
    unvoted_by_user: bool,
) -> float:
    weight = 1.0
    on_diff_union = card.nsg_banned or card.id in community_banned_ids
    if on_diff_union:
        weight *= float(current_app.config["PICK_DIFF_WEIGHT"])

    controversy = _controversy(ban_count, total)
    if controversy is None:
        if on_diff_union:
            weight *= float(current_app.config["PICK_ZERO_VOTE_BONUS"])
    else:
        strength = float(current_app.config["PICK_CONTROVERSY_STRENGTH"])
        weight *= 1.0 + strength * controversy

    if not unvoted_by_user:
        weight *= float(current_app.config["PICK_ALREADY_VOTED_FACTOR"])

    return weight


def pick_card(prefer_unvoted_for: str | None = None) -> Card | None:
    """Pick a Standard-pool card with weighted randomness.

    Higher weight for cards on the NSG or community banlist, controversial
    tallies, mild exploration within that union, and reduced weight for cards
    this voter has already voted on (see ``PICK_ALREADY_VOTED_FACTOR``).

    Args:
        prefer_unvoted_for: Cookie voter id used for the already-voted factor.
            If omitted, every card is treated as unvoted by the user.

    Returns:
        A card to present, or None if the pool is empty.
    """
    cards = Card.query.filter_by(in_standard_pool=True).all()
    if not cards:
        return None

    tallies = _vote_tallies()
    community_banned_ids = {card.id for card in community_banned_cards()}

    voted_ids: set[int] = set()
    if prefer_unvoted_for:
        voted_ids = {
            row[0]
            for row in db.session.query(Vote.card_id).filter_by(voter_id=prefer_unvoted_for).all()
        }

    weights = [
        _card_weight(
            card,
            *tallies.get(card.id, (0, 0)),
            community_banned_ids,
            unvoted_by_user=(card.id not in voted_ids),
        )
        for card in cards
    ]
    return choices(cards, weights=weights, k=1)[0]


def get_existing_vote(voter_id: str, card_id: int) -> Vote | None:
    """Fetch this voter's vote for a card, if any.

    Args:
        voter_id: Anonymous cookie id.
        card_id: Local card primary key.

    Returns:
        The vote row, or None.
    """
    return Vote.query.filter_by(voter_id=voter_id, card_id=card_id).first()


def upsert_vote(voter_id: str, card: Card, wants_ban: bool) -> Vote:
    """Create or overwrite a voter's ban/keep choice for a card.

    Args:
        voter_id: Anonymous cookie id.
        card: Card being voted on.
        wants_ban: True for ban, False for keep.

    Returns:
        The persisted vote row.
    """
    vote = get_existing_vote(voter_id, card.id)
    if vote is None:
        vote = Vote(voter_id=voter_id, card_id=card.id, wants_ban=wants_ban)
        db.session.add(vote)
    else:
        vote.wants_ban = wants_ban
        vote.updated_at = utcnow()
    db.session.commit()
    return vote


def community_ban_rows(min_votes: int = 1):
    """Return cards the community would ban (>50% ban votes).

    Args:
        min_votes: Minimum total votes required to qualify.

    Returns:
        List of ``(card, ban_count, total, share)`` sorted by share descending.
    """
    rows = (
        db.session.query(
            Card,
            func.sum(case((Vote.wants_ban.is_(True), 1), else_=0)).label("ban_count"),
            func.count(Vote.id).label("total"),
        )
        .join(Vote, Vote.card_id == Card.id)
        .group_by(Card.id)
        .having(func.count(Vote.id) >= min_votes)
        .all()
    )
    result = []
    for card, ban_count, total in rows:
        ban_count = int(ban_count or 0)
        total = int(total or 0)
        share = ban_count / total if total else 0.0
        if share > 0.5:
            result.append((card, ban_count, total, share))
    result.sort(key=lambda r: (-r[3], -r[2], r[0].title))
    return result


def community_banned_cards(min_votes: int = 1) -> list[Card]:
    """Return Card objects on the community banlist.

    Args:
        min_votes: Minimum total votes required to qualify.

    Returns:
        Cards with ban share greater than 50%.
    """
    return [card for card, *_ in community_ban_rows(min_votes)]


def official_banned_cards() -> list[Card]:
    """Return Standard-pool cards flagged as NSG-banned in the last sync.

    Returns:
        Cards with ``nsg_banned`` set, ordered by title.
    """
    return Card.query.filter_by(nsg_banned=True, in_standard_pool=True).order_by(Card.title).all()


def banlist_comparison(
    min_votes: int = 1,
) -> list[tuple[Card, str, int, int, float | None]]:
    """Build the merged official/community banlist for display.

    NSG-banned cards with no votes yet are treated as still community-banned
    (default to NSG's decision) rather than as removals.

    Args:
        min_votes: Minimum votes for vote-based community banlist membership.

    Returns:
        Alphabetically sorted entries of
        ``(card, status, ban_count, total, share)`` where ``status`` is
        ``both``, ``addition``, or ``removal``, and ``share`` is None when
        the card has no votes.
    """
    community = {c.nrdb_id: c for c in community_banned_cards(min_votes)}
    official = {c.nrdb_id: c for c in official_banned_cards()}
    tallies = _vote_tallies()

    for nrdb_id, card in official.items():
        ban_count, total = tallies.get(card.id, (0, 0))
        if total == 0:
            community[nrdb_id] = card

    entries: list[tuple[Card, str, int, int, float | None]] = []
    for nrdb_id in community.keys() | official.keys():
        card = community.get(nrdb_id) or official[nrdb_id]
        in_community = nrdb_id in community
        in_official = nrdb_id in official
        if in_community and in_official:
            status = "both"
        elif in_community:
            status = "addition"
        else:
            status = "removal"
        ban_count, total = tallies.get(card.id, (0, 0))
        share = (ban_count / total) if total else None
        entries.append((card, status, ban_count, total, share))
    entries.sort(key=lambda row: row[0].title.casefold())
    return entries


def highest_ban_share_off_list(
    limit: int = 10,
    min_votes: int = 1,
) -> list[tuple[Card, int, int, float]]:
    """Return off-list cards with the highest ban share at or below 50%.

    Because community membership requires ``share > 0.5``, the closest calls
    for the banlist are simply the highest percentages that still fall short.

    Args:
        limit: Maximum number of cards to return.
        min_votes: Minimum total votes required to rank.

    Returns:
        Up to ``limit`` tuples of ``(card, ban_count, total, share)`` ordered
        by ban share descending.
    """
    on_list_ids = {card.id for card, *_ in banlist_comparison(min_votes)}
    tallies = _vote_tallies()
    ranked: list[tuple[float, Card, int, int]] = []

    for card in Card.query.filter_by(in_standard_pool=True).all():
        if card.id in on_list_ids:
            continue
        ban_count, total = tallies.get(card.id, (0, 0))
        if total < min_votes:
            continue
        share = ban_count / total
        if share > 0.5:
            continue
        ranked.append((share, card, ban_count, total))

    ranked.sort(key=lambda row: (-row[0], -row[3], row[1].title.casefold()))
    return [
        (card, ban_count, total, share)
        for share, card, ban_count, total in ranked[:limit]
    ]
