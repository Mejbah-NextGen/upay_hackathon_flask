"""Purpose-specific AI consent and content-free governance records.

New tables only: deployments need their ordinary create/migrate step. The pilot
consent is intentionally not a foreign key or an implicit source of AI consent.
"""

from datetime import datetime, timezone

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class AIConsent(db.Model):
    __tablename__ = "ai_consents"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    purpose = db.Column(db.String(30), primary_key=True)
    policy_version = db.Column(db.String(40), nullable=False)
    granted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)


class AIConversationRetention(db.Model):
    __tablename__ = "ai_conversation_retention"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class AIConversationControl(db.Model):
    """Content-free invalidation counter; prevents erased in-flight chat replay."""

    __tablename__ = "ai_conversation_controls"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    generation = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class AIGovernanceEvent(db.Model):
    __tablename__ = "ai_governance_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.String(60), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
