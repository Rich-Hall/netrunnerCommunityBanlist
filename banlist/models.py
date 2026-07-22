"""SQLAlchemy models for cards and votes."""

from datetime import UTC, datetime

from banlist import db


def utcnow():
    """Return the current UTC time.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(UTC)


class Card(db.Model):
    """A Netrunner card from the Standard pool (synced from NRDB)."""

    __tablename__ = "card"

    id = db.Column(db.Integer, primary_key=True)
    nrdb_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False)
    side = db.Column(db.String(32), nullable=False)
    faction = db.Column(db.String(64), nullable=False)
    card_type = db.Column(db.String(64), nullable=False)
    image_url = db.Column(db.String(512))
    nsg_banned = db.Column(db.Boolean, default=False, nullable=False)
    in_standard_pool = db.Column(db.Boolean, default=True, nullable=False)

    votes = db.relationship("Vote", back_populates="card", lazy="dynamic")

    def __repr__(self):
        """Return a debug representation of the card."""
        return f"<Card {self.nrdb_id}>"


class Vote(db.Model):
    """A single browser's ban/keep vote for one card."""

    __tablename__ = "vote"
    __table_args__ = (db.UniqueConstraint("voter_id", "card_id", name="uq_vote_voter_card"),)

    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.String(64), nullable=False, index=True)
    card_id = db.Column(db.Integer, db.ForeignKey("card.id"), nullable=False)
    wants_ban = db.Column(db.Boolean, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    card = db.relationship("Card", back_populates="votes")

    def __repr__(self):
        """Return a debug representation of the vote."""
        return f"<Vote voter={self.voter_id} card={self.card_id} ban={self.wants_ban}>"
