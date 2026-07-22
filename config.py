"""Application configuration loaded from the environment."""

import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _require_env(name: str) -> str:
    """Return a required environment variable.

    Args:
        name: Environment variable name.

    Returns:
        The non-empty value of the variable.

    Raises:
        RuntimeError: If the variable is missing or empty.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and set {name}, "
            "or export it in your environment / host secrets UI."
        )
    return value


class Config:
    """Flask and picker settings loaded from the environment."""

    SECRET_KEY = _require_env("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(basedir, "data", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    VOTER_COOKIE_NAME = "voter_id"
    VOTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
    NRDB_API_BASE = "https://api.netrunnerdb.com/api/v3/public"

    # Weighted card picker (see banlist.voting.pick_card)
    # The banlist is a small slice of ~600 cards. We weight cards accordining to
    # a few factors so the user isn't constantly presented with obvious
    # uncontrovertial "do not ban" choices, which is what would happen if we
    # just picked cards randomly.

    # Union of NSG and current community banlist. We want to show cards on
    # either list the most frequently.
    PICK_DIFF_WEIGHT = 25.0

    # Scales 4p(1-p) term. We want to show cards that are somewhat conrovertial
    # more frequently, so weight cards higher the closer they are to a 50/50
    # vote split.
    PICK_CONTROVERSY_STRENGTH = 5.0

    PICK_ZERO_VOTE_BONUS = 1.5  # only applied to diff-union cards

    # Dial down the weight of cards you've already voted on, so you're not
    # constantly presented with the same cards.
    PICK_ALREADY_VOTED_FACTOR = 0.005
