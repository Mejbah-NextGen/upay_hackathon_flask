"""Durable retry state and worker observability, independent of web visits."""

from app.extensions import db


class ScheduleRetry(db.Model):
    __tablename__ = "schedule_retries"
    schedule_id = db.Column(db.Integer, db.ForeignKey("scheduled_payments.id"), primary_key=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    last_error_category = db.Column(db.String(80), nullable=True)
    exhausted = db.Column(db.Boolean, nullable=False, default=False)


class WorkerHeartbeat(db.Model):
    __tablename__ = "worker_heartbeats"
    worker_id = db.Column(db.String(80), primary_key=True)
    role = db.Column(db.String(30), nullable=False)
    seen_at = db.Column(db.DateTime(timezone=True), nullable=False)
    completed = db.Column(db.Integer, nullable=False, default=0)
    failed = db.Column(db.Integer, nullable=False, default=0)

