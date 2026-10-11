"""Anonymous community models for The Floor."""

from datetime import datetime

from sqlalchemy import CheckConstraint, UniqueConstraint

from ..extensions import community_db


class MarketMood(community_db.Model):
    __tablename__ = "market_mood"
    __table_args__ = (
        UniqueConstraint("user_hash", "week_start", name="uq_market_mood_user_week"),
        CheckConstraint("mood IN ('fire', 'normal', 'cold')", name="ck_market_mood_value"),
    )

    id = community_db.Column(community_db.Integer, primary_key=True)
    user_hash = community_db.Column(community_db.String(64), nullable=False, index=True)
    city = community_db.Column(community_db.String(50), nullable=False, index=True)
    category = community_db.Column(community_db.String(50), nullable=False, index=True)
    mood = community_db.Column(community_db.String(20), nullable=False)
    created_at = community_db.Column(community_db.DateTime, nullable=False, default=datetime.utcnow)
    # A date key makes the one-check-in-per-week rule race-safe on SQLite and Postgres.
    week_start = community_db.Column(community_db.Date, nullable=False, index=True)


class StreetTip(community_db.Model):
    __tablename__ = "street_tip"
    __table_args__ = (
        CheckConstraint("length(content) <= 160", name="ck_street_tip_content_length"),
    )

    id = community_db.Column(community_db.Integer, primary_key=True)
    city = community_db.Column(community_db.String(50), nullable=False, index=True)
    category = community_db.Column(community_db.String(50), nullable=False, index=True)
    content = community_db.Column(community_db.String(160), nullable=False)
    upvotes = community_db.Column(community_db.Integer, nullable=False, default=0)
    created_at = community_db.Column(community_db.DateTime, nullable=False, default=datetime.utcnow)


class SabiPlugRequest(community_db.Model):
    __tablename__ = "sabi_plug_request"
    __table_args__ = (
        CheckConstraint("length(request_text) <= 140", name="ck_sabi_plug_request_length"),
    )

    id = community_db.Column(community_db.Integer, primary_key=True)
    city = community_db.Column(community_db.String(50), nullable=False, index=True)
    category = community_db.Column(community_db.String(50), nullable=False, index=True)
    request_text = community_db.Column(community_db.String(140), nullable=False)
    recommendations_count = community_db.Column(community_db.Integer, nullable=False, default=0)
    created_at = community_db.Column(community_db.DateTime, nullable=False, default=datetime.utcnow)
    recommendations = community_db.relationship(
        "SabiPlugRecommendation",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="SabiPlugRecommendation.upvotes.desc(), SabiPlugRecommendation.created_at.desc()",
    )


class SabiPlugRecommendation(community_db.Model):
    __tablename__ = "sabi_plug_recommendation"
    __table_args__ = (
        CheckConstraint("length(plug_detail) <= 160", name="ck_sabi_plug_recommendation_length"),
    )

    id = community_db.Column(community_db.Integer, primary_key=True)
    request_id = community_db.Column(
        community_db.Integer,
        community_db.ForeignKey("sabi_plug_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plug_detail = community_db.Column(community_db.String(160), nullable=False)
    upvotes = community_db.Column(community_db.Integer, nullable=False, default=0)
    created_at = community_db.Column(community_db.DateTime, nullable=False, default=datetime.utcnow)
    request = community_db.relationship("SabiPlugRequest", back_populates="recommendations")


class CommunityVote(community_db.Model):
    """A private vote ledger prevents the same anonymous account voting twice."""

    __tablename__ = "community_vote"
    __table_args__ = (
        UniqueConstraint("user_hash", "target_type", "target_id", name="uq_community_vote_target"),
        CheckConstraint("target_type IN ('tip', 'recommendation')", name="ck_community_vote_type"),
    )

    id = community_db.Column(community_db.Integer, primary_key=True)
    user_hash = community_db.Column(community_db.String(64), nullable=False, index=True)
    target_type = community_db.Column(community_db.String(20), nullable=False)
    target_id = community_db.Column(community_db.Integer, nullable=False)
    created_at = community_db.Column(community_db.DateTime, nullable=False, default=datetime.utcnow)
