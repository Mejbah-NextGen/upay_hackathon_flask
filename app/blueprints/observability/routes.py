import hmac
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text

from app.domain.operations import ScheduledPayment
from app.domain.runtime import ScheduleRetry, WorkerHeartbeat
from app.extensions import db


bp = Blueprint("observability", __name__)


@bp.get("/health/live")
def live():
    return jsonify(status="alive")


@bp.get("/health/ready")
def ready():
    try:
        db.session.execute(text("SELECT 1"))
        if current_app.config.get("SECURITY_PRODUCTION"):
            version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if version != "20261007_03":
                raise ValueError("Schema requires an upgrade")
        # A healthy connection alone must not mask a missing worker schema.
        db.session.query(ScheduledPayment.id).limit(1).all()
        db.session.query(WorkerHeartbeat.worker_id).limit(1).all()
    except Exception:
        db.session.rollback()
        return jsonify(status="not_ready"), 503
    return jsonify(status="ready")


@bp.get("/internal/metrics")
def metrics():
    secret = current_app.config.get("OBSERVABILITY_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(supplied, "Bearer " + secret):
        return jsonify(error="unauthorized"), 401
    now = datetime.now(timezone.utc)
    lines = ["# TYPE upayx_due_schedules gauge",
             f"upayx_due_schedules {ScheduledPayment.query.filter(ScheduledPayment.auto_pay.is_(True), ScheduledPayment.status == 'SCHEDULED', ScheduledPayment.due_at <= now).count()}",
             "# TYPE upayx_schedule_retries_exhausted gauge",
             f"upayx_schedule_retries_exhausted {ScheduleRetry.query.filter_by(exhausted=True).count()}"]
    for worker in WorkerHeartbeat.query.order_by(WorkerHeartbeat.seen_at.desc(), WorkerHeartbeat.worker_id).limit(100).all():
        seen = worker.seen_at.replace(tzinfo=timezone.utc) if worker.seen_at.tzinfo is None else worker.seen_at
        lines.append(f'upayx_worker_heartbeat_age_seconds{{worker="{worker.worker_id}"}} {max(0, (now - seen).total_seconds()):.2f}')
    response = current_app.response_class("\n".join(lines) + "\n", mimetype="text/plain")
    response.headers["Cache-Control"] = "private, no-store"
    return response
