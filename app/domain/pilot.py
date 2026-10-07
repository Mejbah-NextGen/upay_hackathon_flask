"""Consent and observations for the narrowly scoped planning experiment."""

from datetime import datetime, timezone

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class PilotParticipant(db.Model):
    __tablename__ = "pilot_participants"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    data_source = db.Column(db.String(10), nullable=False, default="DEMO")
    variant = db.Column(db.String(10), nullable=False)
    verified_real = db.Column(db.Boolean, nullable=False, default=False)
    consent_version = db.Column(db.String(30), nullable=False)
    enrolled_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    withdrawn_at = db.Column(db.DateTime(timezone=True), nullable=True)


class PilotEvent(db.Model):
    __tablename__ = "pilot_events"
    __table_args__ = (db.UniqueConstraint("user_id", "dedup_key", name="uq_pilot_event_dedup"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("pilot_participants.user_id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False, index=True)
    task_key = db.Column(db.String(30), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    task_token = db.Column(db.String(32), nullable=True, index=True)
    dedup_key = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class PilotFeedback(db.Model):
    __tablename__ = "pilot_feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("pilot_participants.user_id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default="RESEARCH")
    problem = db.Column(db.String(30), nullable=False)
    usefulness = db.Column(db.Integer, nullable=True)
    ease = db.Column(db.Integer, nullable=True)
    missed_payments_last_30_days = db.Column(db.Integer, nullable=True)
    comment = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
