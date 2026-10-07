"""Persisted security controls shared by web processes and durable workers."""

from sqlalchemy import event

from app.extensions import db


class RateLimitBucket(db.Model):
    __tablename__ = "security_rate_buckets"

    key_hash = db.Column(db.String(64), primary_key=True)
    category = db.Column(db.String(32), primary_key=True)
    window_start = db.Column(db.BigInteger, primary_key=True)
    hits = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)


class OtpChallenge(db.Model):
    __tablename__ = "security_otp_challenges"

    id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.BigInteger, nullable=True)
    delivered = db.Column(db.Boolean, nullable=False, default=False)


class TrustedSession(db.Model):
    __tablename__ = "security_trusted_sessions"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    device_hash = db.Column(db.String(64), nullable=False)
    agent_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)
    revoked_at = db.Column(db.BigInteger, nullable=True)


class SecurityAuditEvent(db.Model):
    __tablename__ = "security_audit_events"

    id = db.Column(db.String(32), primary_key=True)
    created_at = db.Column(db.BigInteger, nullable=False, index=True)
    request_id = db.Column(db.String(32), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    result = db.Column(db.String(40), nullable=False)
    details = db.Column(db.Text, nullable=False, default="{}")
    signature = db.Column(db.String(64), nullable=False)


@event.listens_for(SecurityAuditEvent, "before_update")
@event.listens_for(SecurityAuditEvent, "before_delete")
def protect_audit_history(mapper, connection, target):
    raise ValueError("Security audit events are append-only.")
