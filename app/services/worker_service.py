"""Bounded durable polling; payment claims and rollback belong to the ledger."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import click
from flask import current_app
from sqlalchemy import or_

from app.domain.operations import ScheduledPayment
from app.domain.runtime import ScheduleRetry, WorkerHeartbeat
from app.extensions import db
from app.services.schedule_service import execute_schedule


def process_schedules_once(*, limit=None, now=None, worker_id=None):
    now = now or datetime.now(timezone.utc)
    limit = max(1, min(int(limit or current_app.config.get("WORKER_BATCH_SIZE", 50)), 200))
    ids = db.session.query(ScheduledPayment.user_id, ScheduledPayment.id).outerjoin(
        ScheduleRetry, ScheduleRetry.schedule_id == ScheduledPayment.id
    ).filter(ScheduledPayment.status == "SCHEDULED", ScheduledPayment.auto_pay.is_(True),
             ScheduledPayment.due_at <= now,
             or_(ScheduleRetry.schedule_id.is_(None), ScheduleRetry.exhausted.is_(False)),
             or_(ScheduleRetry.next_attempt_at.is_(None), ScheduleRetry.next_attempt_at <= now)
    ).order_by(ScheduledPayment.due_at, ScheduledPayment.id).limit(limit).all()
    db.session.rollback()  # Release selection snapshots before claiming any payment.
    result = {"selected": len(ids), "completed": 0, "failed": 0, "retried": 0, "exhausted": 0}
    for owner, schedule_id in ids:
        try:
            payment = execute_schedule(owner, schedule_id, now=now)
            if payment and getattr(payment, "processed_now", False):
                result["completed" if payment.status == "COMPLETED" else "failed"] += 1
        except Exception as exc:
            # An ambiguous local interruption leaves no committed ledger write.
            # Retain only an error class, never provider bodies or account text.
            db.session.rollback()
            # Serialize retry creation on both supported backends. A no-op write
            # locks the row before reading retry state, without changing funds.
            locked = ScheduledPayment.query.filter_by(id=schedule_id, status="SCHEDULED").update(
                {ScheduledPayment.status: "SCHEDULED"}, synchronize_session=False)
            if not locked:
                db.session.rollback()
                continue
            payment = db.session.get(ScheduledPayment, schedule_id)
            retry = db.session.get(ScheduleRetry, schedule_id)
            if retry is None:
                retry = ScheduleRetry(schedule_id=schedule_id, failures=0)
                db.session.add(retry)
            retry.failures += 1
            retry.last_error_category = type(exc).__name__[:80]
            retry.next_attempt_at = now + timedelta(seconds=min(3600, current_app.config.get("WORKER_RETRY_SECONDS", 30) * 2 ** min(retry.failures - 1, 10)))
            retry.exhausted = retry.failures >= current_app.config.get("WORKER_MAX_ATTEMPTS", 5)
            if retry.exhausted:
                payment.status = "FAILED"
                payment.last_error = "Processing was interrupted repeatedly. Review this plan before creating a replacement."
                result["exhausted"] += 1
            else:
                result["retried"] += 1
            from app.services.security_service import audit_event
            audit_event("scheduler.interrupted", "review_required" if retry.exhausted else "retry_planned", owner,
                        {"job_id": schedule_id, "reason": retry.last_error_category})
            db.session.commit()
        finally:
            db.session.remove()
    worker_id = worker_id or "single-pass"
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    table = WorkerHeartbeat.__table__
    values = {"worker_id": worker_id, "role": "schedules", "seen_at": now,
              "completed": result["completed"], "failed": result["failed"] + result["exhausted"]}
    statement = (pg_insert if db.engine.dialect.name == "postgresql" else sqlite_insert)(table).values(**values)
    db.session.execute(statement.on_conflict_do_update(index_elements=[table.c.worker_id],
                       set_={key: value for key, value in values.items() if key != "worker_id"}))
    db.session.commit()
    return result


def register_worker_cli(app):
    @app.cli.command("durable-worker")
    @click.option("--watch", is_flag=True)
    @click.option("--interval", default=10, type=click.IntRange(1, 60))
    @click.option("--batch-size", default=50, type=click.IntRange(1, 200))
    def worker(watch, interval, batch_size):
        """Run payments and hourly expiry cleanup without a browser visit."""
        import json
        import time
        worker_id = "scheduler-" + uuid4().hex
        last_cleanup = 0
        while True:
            click.echo(json.dumps(process_schedules_once(limit=batch_size, worker_id=worker_id)))
            if time.monotonic() - last_cleanup >= 3600:
                from app.services.ai_governance_service import prune_expired
                from app.services.security_service import prune_expired_security
                prune_expired()
                prune_expired_security()
                WorkerHeartbeat.query.filter(WorkerHeartbeat.seen_at < datetime.now(timezone.utc) - timedelta(days=7)).delete()
                db.session.commit()
                last_cleanup = time.monotonic()
            db.session.remove()
            if not watch:
                break
            time.sleep(interval)
