"""Integration records; provider results never represent local wallet movements."""

from datetime import datetime, timezone

from app.extensions import db


def now_utc():
    return datetime.now(timezone.utc)


class ApiToken(db.Model):
    __tablename__ = "api_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    secret_hash = db.Column(db.String(64), nullable=False, unique=True)
    prefix = db.Column(db.String(12), nullable=False)
    scopes = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))


class ApiIdempotency(db.Model):
    __tablename__ = "api_idempotency"
    __table_args__ = (db.UniqueConstraint("token_id", "key", name="uq_api_token_idempotency"),)
    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey("api_tokens.id"), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    response_json = db.Column(db.Text, nullable=False, default="")
    status_code = db.Column(db.Integer, nullable=False, default=201)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)


class ProviderIntent(db.Model):
    __tablename__ = "provider_intents"
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    provider = db.Column(db.String(40), nullable=False, default="reference_sandbox")
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="BDT")
    biller_reference = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="QUEUED")
    provider_reference = db.Column(db.String(80))
    provider_sequence = db.Column(db.Integer, nullable=False, default=0)
    authorized_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)


class ProviderOutbox(db.Model):
    __tablename__ = "provider_outbox"
    id = db.Column(db.Integer, primary_key=True)
    intent_id = db.Column(db.String(32), db.ForeignKey("provider_intents.id"), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc, index=True)
    lease_until = db.Column(db.DateTime(timezone=True))
    lease_token = db.Column(db.String(32))
    last_error = db.Column(db.String(80))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)


class ProviderWebhook(db.Model):
    __tablename__ = "provider_webhooks"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(80), nullable=False, unique=True)
    payload_hash = db.Column(db.String(64), nullable=False)
    intent_id = db.Column(db.String(32), db.ForeignKey("provider_intents.id"), nullable=False)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now_utc)
