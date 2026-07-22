"""NetrunnerDB v3 client: Standard pool sync and latest-announced restriction."""

from __future__ import annotations

import requests
from flask import current_app

from banlist import db
from banlist.models import Card

PAGE_SIZE = 100


def _get(path: str, params: dict | None = None) -> dict:
    base = current_app.config["NRDB_API_BASE"].rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    response = requests.get(url, params=params or {}, timeout=60)
    response.raise_for_status()
    return response.json()


def latest_announced_restriction_id() -> str:
    """Return the Standard restriction id with the latest ``date_start``.

    Ignores NRDB's ``active`` flag so announced-but-not-yet-legal lists win.

    Returns:
        Restriction id string (e.g. ``standard_balance_update_26_08``).

    Raises:
        RuntimeError: If no Standard restrictions are available.
    """
    fmt = _get("formats/standard")["data"]["attributes"]
    restriction_ids = fmt.get("restriction_ids") or []
    if not restriction_ids:
        raise RuntimeError("No Standard restrictions found on NRDB")

    best_id = None
    best_date = ""
    for rid in restriction_ids:
        attrs = _get(f"restrictions/{rid}")["data"]["attributes"]
        date_start = attrs.get("date_start") or ""
        if date_start >= best_date:
            best_date = date_start
            best_id = rid
    if not best_id:
        raise RuntimeError("Could not resolve latest announced restriction")
    return best_id


def fetch_banned_card_ids(restriction_id: str) -> set[str]:
    """Load banned card ids for a restriction.

    Args:
        restriction_id: NRDB restriction resource id.

    Returns:
        Set of NRDB card ids marked banned on that list.
    """
    attrs = _get(f"restrictions/{restriction_id}")["data"]["attributes"]
    verdicts = attrs.get("verdicts") or {}
    return set(verdicts.get("banned") or [])


def fetch_standard_card_pool_id() -> str:
    """Return the active Standard card pool id from NRDB.

    Returns:
        Card pool id string.

    Raises:
        RuntimeError: If the format payload has no active pool.
    """
    fmt = _get("formats/standard")["data"]["attributes"]
    pool_id = fmt.get("active_card_pool_id")
    if not pool_id:
        raise RuntimeError("No active Standard card pool on NRDB")
    return pool_id


def iter_pool_cards(card_pool_id: str):
    """Yield card JSON:API resources for every card in a pool.

    Args:
        card_pool_id: NRDB card pool id.

    Yields:
        Individual card resource dicts from the v3 API.
    """
    page = 1
    while True:
        payload = _get(
            "cards",
            {
                "filter[card_pool_id]": card_pool_id,
                "page[number]": page,
                "page[size]": PAGE_SIZE,
                # Without a stable sort, NRDB v3 page windows overlap and skip
                # cards (e.g. Synapse Global never appears in the pool walk).
                "sort": "id",
            },
        )
        data = payload.get("data") or []
        if not data:
            break
        yield from data
        links = payload.get("links") or {}
        if not links.get("next"):
            break
        page += 1


def _image_url(attributes: dict) -> str | None:
    images = attributes.get("latest_printing_images") or {}
    classic = images.get("nrdb_classic") or {}
    return classic.get("large") or classic.get("medium") or classic.get("small")


def sync_standard_cards() -> int:
    """Refresh local ``Card`` rows from the Standard pool and ban flags.

    Cards that leave the pool remain in the DB (votes preserved) but are
    marked ``in_standard_pool=False``.

    Returns:
        Number of cards upserted from the current Standard pool.
    """
    pool_id = fetch_standard_card_pool_id()
    restriction_id = latest_announced_restriction_id()
    banned_ids = fetch_banned_card_ids(restriction_id)

    seen: set[str] = set()
    count = 0

    for item in iter_pool_cards(pool_id):
        nrdb_id = item["id"]
        attrs = item["attributes"]
        seen.add(nrdb_id)

        card = Card.query.filter_by(nrdb_id=nrdb_id).first()
        if card is None:
            card = Card(nrdb_id=nrdb_id)
            db.session.add(card)

        card.title = attrs.get("title") or nrdb_id
        card.side = attrs.get("side_id") or "unknown"
        card.faction = attrs.get("faction_id") or "unknown"
        card.card_type = attrs.get("card_type_id") or "unknown"
        card.image_url = _image_url(attrs)
        card.nsg_banned = nrdb_id in banned_ids
        card.in_standard_pool = True
        count += 1

    for card in Card.query.filter(Card.in_standard_pool.is_(True)).all():
        if card.nrdb_id not in seen:
            card.in_standard_pool = False
            card.nsg_banned = False

    db.session.commit()
    return count
