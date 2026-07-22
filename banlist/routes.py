"""HTTP routes for voting and banlist views."""

from itertools import zip_longest

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from banlist.models import Card
from banlist.search import search_cards
from banlist.voting import (
    attach_voter_cookie,
    banlist_comparison,
    get_existing_vote,
    get_or_create_voter_id,
    highest_ban_share_off_list,
    pick_card,
    upsert_vote,
)

bp = Blueprint("main", __name__)


def _voter_from_request():
    voter_id, new_cookie = get_or_create_voter_id()
    return voter_id, new_cookie is not None, new_cookie


@bp.route("/")
def index():
    """Show a card to vote on, or search results for a card query.

    Returns:
        HTML response for the vote page (and sets the voter cookie when new).
    """
    voter_id, is_new, new_cookie = _voter_from_request()
    query = (request.args.get("q") or "").strip()
    card_id = request.args.get("card", type=int)
    search_matches = None

    if query and not card_id:
        search_matches = search_cards(query, limit=25)
        if len(search_matches) == 1:
            response = redirect(url_for("main.index", card=search_matches[0].id))
            if is_new and new_cookie:
                attach_voter_cookie(response, new_cookie, True)
            return response
        if not search_matches:
            flash(f"No Standard cards matching “{query}”.")
            search_matches = None

    if card_id:
        card = Card.query.filter_by(id=card_id, in_standard_pool=True).first()
    elif search_matches:
        card = None
    else:
        card = pick_card(prefer_unvoted_for=voter_id)

    existing = get_existing_vote(voter_id, card.id) if card else None
    html = render_template(
        "index.html",
        card=card,
        existing_vote=existing,
        query=query,
        search_matches=search_matches,
    )
    response = current_app.make_response(html)
    if is_new and new_cookie:
        attach_voter_cookie(response, new_cookie, True)
    return response


@bp.route("/vote/<int:card_id>", methods=["POST"])
def vote(card_id):
    """Record a ban/keep vote and redirect to the next card.

    Args:
        card_id: Primary key of the card being voted on.

    Returns:
        Redirect to the next vote page.
    """
    voter_id, is_new, new_cookie = _voter_from_request()
    card = Card.query.filter_by(id=card_id, in_standard_pool=True).first_or_404()
    choice = request.form.get("choice")
    if choice not in {"ban", "keep"}:
        flash("Invalid vote.")
        return redirect(url_for("main.index", card=card.id))

    upsert_vote(voter_id, card, wants_ban=(choice == "ban"))
    next_card = pick_card(prefer_unvoted_for=voter_id)
    target = url_for("main.index", card=next_card.id) if next_card else url_for("main.index")
    response = redirect(target)
    if is_new and new_cookie:
        attach_voter_cookie(response, new_cookie, True)
    return response


@bp.route("/banlist")
def banlist():
    """Show the merged official and community banlist comparison.

    Returns:
        HTML for the Runner/Corp banlist view.
    """
    entries = banlist_comparison()
    runner_entries = [e for e in entries if e[0].side == "runner"]
    corp_entries = [e for e in entries if e[0].side == "corp"]
    return render_template(
        "banlist.html",
        banlist_rows=list(zip_longest(runner_entries, corp_entries)),
        controversial=highest_ban_share_off_list(limit=10),
    )


@bp.route("/faq")
def faq():
    """Show the FAQ page.

    Returns:
        HTML for the FAQ.
    """
    return render_template("faq.html")
