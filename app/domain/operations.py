"""Persisted recipient safety records and individual scheduled installments."""

from datetime import datetime, timezone

from app.extensions import db


class RecipientRegistration(db.Model):
    __tablename__ = "recipient_registrations"
    __table_args__ = (db.UniqueConstraint("number", "provider", "kind", name="uq_recipient_service"),)

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(60), nullable=False, index=True)
    provider = db.Column(db.String(120), nullable=False, default="")
    kind = db.Column(db.String(40), nullable=False, default="ANY")
    name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="REGISTERED")
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ScheduledPayment(db.Model):
    __tablename__ = "scheduled_payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    recipient_number = db.Column(db.String(60), nullable=False)
    recipient_name = db.Column(db.String(120), nullable=True)
    provider = db.Column(db.String(120), nullable=False, default="")
    category = db.Column(db.String(40), nullable=False, default="")
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    frequency = db.Column(db.String(20), nullable=False, default="ONE_TIME")
    auto_pay = db.Column(db.Boolean, nullable=False, default=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="SCHEDULED", index=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True, unique=True)
    recurrence_group = db.Column(db.String(40), nullable=False)
    seed_key = db.Column(db.String(80), nullable=True, unique=True)
    last_error = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    executed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    transaction = db.relationship("Transaction", foreign_keys=[transaction_id])
