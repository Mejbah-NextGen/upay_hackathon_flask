"""Trusted, transaction-local measurement hooks and honest cohort summaries.

Hooks deliberately never commit: payment outcomes and their observations succeed
or roll back together. There is no client endpoint for payment success events.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.domain.pilot import PilotEvent, PilotFeedback, PilotParticipant
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.reporting_service import local_datetime


CONSENT_VERSION = "planning-pilot-v1"
TASK_KEYS = {"financial_health", "recurring_payment"}
PROBLEMS = {"planning", "recurring_payments", "both"}
PAYMENT_MODE = "simulated prototype payments"


def _utc(value=None):
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def participant_for_user(user_id):
    return db.session.get(PilotParticipant, user_id)


def pilot_context(user_id):
    participant = participant_for_user(user_id)
    active = bool(participant and participant.withdrawn_at is None)
    return {
        "enrolled": active,
        "variant": participant.variant if participant else None,
        "source": participant.data_source if participant else "DEMO",
        "verified_real": bool(active and participant.verified_real),
        "forecast_enabled": not participant or participant.variant == "treatment",
    }


def enrol_participant(user_id, *, consent=False, data_source="DEMO", real_attestation=False, now=None):
    if not consent:
        raise ValidationError("Please read and accept the pilot consent before enrolling.")
    data_source = str(data_source).upper()
    if data_source not in {"DEMO", "REAL"}:
        raise ValidationError("Choose a demo session or a real participant research session.")
    if data_source == "REAL" and not real_attestation:
        raise ValidationError("Real participant sessions require your confirmation that you are a real research participant.")
    previous = participant_for_user(user_id)
    if previous:
        if previous.withdrawn_at is not None:
            raise ValidationError("This account has withdrawn from the pilot. Contact the study operator to join a new study.")
        if previous.data_source != data_source:
            raise ValidationError("The session source is fixed after enrolment to keep demo and research observations separate.")
        return previous
    # Stable salted allocation: reloading or retrying cannot select a preferred arm.
    secret = current_app.config.get("PILOT_ASSIGNMENT_SALT") or current_app.config["SECRET_KEY"]
    digest = hashlib.sha256(f"{secret}:{CONSENT_VERSION}:{user_id}".encode()).digest()
    participant = _insert_once(PilotParticipant, {
        "user_id": user_id, "data_source": data_source,
        "variant": "treatment" if digest[0] % 2 else "control",
        "consent_version": CONSENT_VERSION, "enrolled_at": _utc(now), "verified_real": False,
    }, ["user_id"])
    if participant.data_source != data_source or participant.withdrawn_at is not None:
        raise ValidationError("An existing study enrolment keeps its original source and withdrawal status.")
    return participant


def withdraw_participant(user_id, *, now=None):
    participant = participant_for_user(user_id)
    if participant and participant.withdrawn_at is None:
        participant.withdrawn_at = _utc(now)
        db.session.flush()
    return participant


def _active(user_id):
    participant = participant_for_user(user_id)
    return participant if participant and participant.withdrawn_at is None else None


def _insert_once(model, values, unique_keys):
    """Insert once without committing or invalidating an outer transaction."""
    dialect = db.session.get_bind().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        statement = insert(model).values(**values).on_conflict_do_nothing(index_elements=unique_keys)
        db.session.execute(statement)
        return model.query.filter_by(**{key: values[key] for key in unique_keys}).one()
    # Engines with explicit outer transactions can isolate a uniqueness race.
    event = model(**values)
    try:
        with db.session.begin_nested():
            db.session.add(event)
            db.session.flush()
    except IntegrityError:
        existing = model.query.filter_by(**{key: values[key] for key in unique_keys}).first()
        if existing is None:
            raise
        return existing
    return event


def _event(user_id, kind, dedup_key, *, task_key=None, resource_id=None, task_token=None, now=None):
    participant = _active(user_id)
    observed_at = _utc(now)
    if participant is None or observed_at < _utc(participant.enrolled_at):
        return None
    existing = PilotEvent.query.filter_by(user_id=user_id, dedup_key=dedup_key).first()
    if existing:
        return existing
    return _insert_once(PilotEvent, {"user_id": user_id, "kind": kind, "dedup_key": dedup_key,
                                    "task_key": task_key, "resource_id": resource_id,
                                    "task_token": task_token, "created_at": observed_at}, ["user_id", "dedup_key"])


def record_activity(user_id, *, now=None):
    now = _utc(now)
    return _event(user_id, "ACTIVITY", f"activity:{local_datetime(now).date().isoformat()}", now=now)


def record_exposure(user_id, task_key="financial_health", *, now=None):
    if task_key not in TASK_KEYS:
        raise ValidationError("Unknown research task.")
    now = _utc(now)
    return _event(user_id, "EXPOSURE", f"exposure:{task_key}:{local_datetime(now).date().isoformat()}", task_key=task_key, now=now)


def record_forecast_exposure(user_id, *, now=None):
    """Record a successfully rendered numerical forecast in the treatment arm.

    The server calls this only when its forecast is available. An unavailable
    placeholder is a planning-page exposure, rather than a delivered forecast.
    """
    participant = _active(user_id)
    if participant is None or participant.variant != "treatment":
        return None
    now = _utc(now)
    return _event(user_id, "FORECAST_SHOWN", f"forecast-shown:{local_datetime(now).date().isoformat()}",
                  task_key="financial_health", now=now)


def record_task_start(user_id, task_key, *, now=None):
    if task_key not in TASK_KEYS:
        raise ValidationError("Unknown research task.")
    if not _active(user_id):
        return None
    # One primary task per participant prevents the acknowledgement redirect or
    # a page refresh from silently creating another denominator entry.
    start = PilotEvent.query.filter_by(user_id=user_id, kind="TASK_STARTED", task_key=task_key).order_by(PilotEvent.id).first()
    if start:
        return start
    token = uuid4().hex
    return _event(user_id, "TASK_STARTED", f"task-start:{task_key}", task_key=task_key, task_token=token, now=now)


def record_task_completion(user_id, task_key, resource_id=None, *, now=None):
    if task_key not in TASK_KEYS:
        raise ValidationError("Unknown research task.")
    if not _active(user_id):
        return None
    starts = PilotEvent.query.filter_by(user_id=user_id, kind="TASK_STARTED", task_key=task_key).order_by(PilotEvent.id.desc()).all()
    completed = {row.task_token for row in PilotEvent.query.filter_by(user_id=user_id, kind="TASK_COMPLETED", task_key=task_key).all()}
    start = next((row for row in starts if row.task_token not in completed), None)
    if start is None:
        return None
    return _event(user_id, "TASK_COMPLETED", f"task-complete:{start.task_token}", task_key=task_key,
                  task_token=start.task_token, resource_id=resource_id, now=now)


def record_transaction(transaction, *, now=None):
    """Record initiated successful ledger entries; passive receipts are excluded."""
    if transaction.status != "SUCCESS" or transaction.kind == "RECEIVE_MONEY":
        return None
    db.session.flush()
    observed_at = _utc(now or transaction.created_at)
    return _event(transaction.user_id, "TRANSACTION", f"transaction:{transaction.id}", resource_id=transaction.id, now=observed_at)


def record_schedule_created(installments, *, now=None):
    installments = list(installments)
    db.session.flush()
    for schedule in installments:
        _event(schedule.user_id, "SCHEDULE_CREATED", f"schedule:{schedule.id}", resource_id=schedule.id, now=now or schedule.created_at)
    if installments:
        record_task_completion(installments[0].user_id, "recurring_payment", installments[0].id, now=now or installments[0].created_at)


def record_schedule_execution(schedule, *, now=None):
    if not schedule.auto_pay or schedule.status not in {"COMPLETED", "FAILED"}:
        return None
    if schedule.status == "COMPLETED":
        transaction = db.session.get(Transaction, schedule.transaction_id)
        if transaction is None or transaction.user_id != schedule.user_id or transaction.status != "SUCCESS":
            return None
    return _event(schedule.user_id, f"AUTO_PAY_{schedule.status}", f"auto-pay:{schedule.id}:{schedule.status}", resource_id=schedule.id, now=now or schedule.executed_at)


def submit_feedback(user_id, values, *, support=False, now=None):
    if not _active(user_id):
        raise ValidationError("Join the pilot before submitting a research response.")
    problem = values.get("problem", "")
    if problem not in PROBLEMS:
        raise ValidationError("Choose planning, recurring payments or both.")
    comment = str(values.get("comment", "")).strip()
    if len(comment) > 1000:
        raise ValidationError("Your comment must be 1,000 characters or fewer.")
    if support and not comment:
        raise ValidationError("Describe the problem you needed help with.")
    ratings = {}
    if not support:
        for key in ("usefulness", "ease"):
            try:
                value = int(values.get(key, ""))
            except (TypeError, ValueError):
                raise ValidationError("Rate usefulness and ease from 1 to 5.")
            if value not in range(1, 6):
                raise ValidationError("Rate usefulness and ease from 1 to 5.")
            ratings[key] = value
        try:
            missed = int(values.get("missed_payments_last_30_days", ""))
        except (TypeError, ValueError):
            raise ValidationError("Enter the number of missed payments in the last 30 days (0–30).")
        if not 0 <= missed <= 30:
            raise ValidationError("Enter the number of missed payments in the last 30 days (0–30).")
        ratings["missed_payments_last_30_days"] = missed
    response = PilotFeedback(user_id=user_id, kind="SUPPORT" if support else "RESEARCH",
                             problem=problem, comment=comment, created_at=_utc(now), **ratings)
    db.session.add(response)
    db.session.flush()
    if support:
        _event(user_id, "SUPPORT_CONTACT", f"support:{response.id}", resource_id=response.id, now=now)
    return response


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def pilot_metrics(*, data_source="REAL", user_id=None, now=None):
    """Aggregate for the operator CLI; a web view must always supply user_id."""
    data_source = str(data_source).upper()
    if data_source not in {"REAL", "DEMO"}:
        raise ValidationError("Choose REAL or DEMO observations.")
    now = _utc(now)
    query = PilotParticipant.query.filter_by(data_source=data_source)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    all_participants = query.all()
    pending_real = sum(not p.verified_real for p in all_participants) if data_source == "REAL" else 0
    participants = [p for p in all_participants if _utc(p.enrolled_at) <= now and (data_source == "DEMO" or p.verified_real)]
    # Withdrawn participants remain in intention-to-treat denominators; no new
    # observations are collected after their withdrawal.
    ids = {p.user_id for p in participants}
    events = PilotEvent.query.filter(PilotEvent.user_id.in_(ids), PilotEvent.created_at <= now).all() if ids else []
    events_by_user = {uid: [] for uid in ids}
    for event in events:
        events_by_user[event.user_id].append(event)
    feedback = PilotFeedback.query.filter(PilotFeedback.user_id.in_(ids), PilotFeedback.created_at <= now).all() if ids else []
    arms = {}
    for variant in ("control", "treatment"):
        cohort = [p for p in participants if p.variant == variant]
        cohort_ids = {p.user_id for p in cohort}
        rows = [e for e in events if e.user_id in cohort_ids]
        starts = [e for e in rows if e.kind == "TASK_STARTED" and e.task_key == "financial_health"]
        tokens = {e.task_token for e in starts}
        completed = [e for e in rows if e.kind == "TASK_COMPLETED" and e.task_key == "financial_health" and e.task_token in tokens]
        recurring_starts = [e for e in rows if e.kind == "TASK_STARTED" and e.task_key == "recurring_payment"]
        recurring_tokens = {e.task_token for e in recurring_starts}
        recurring_completed = [e for e in rows if e.kind == "TASK_COMPLETED" and e.task_key == "recurring_payment" and e.task_token in recurring_tokens]
        schedule_ids = {e.resource_id for e in rows if e.kind == "SCHEDULE_CREATED"}
        schedules = ScheduledPayment.query.filter(ScheduledPayment.id.in_(schedule_ids), ScheduledPayment.user_id.in_(cohort_ids), ScheduledPayment.auto_pay.is_(True), ScheduledPayment.due_at <= now).all() if schedule_ids else []
        cancelled = sum(s.status == "CANCELLED" for s in schedules)
        due = [s for s in schedules if s.status != "CANCELLED"]
        successes = sum(s.status == "COMPLETED" and s.transaction_id is not None and s.transaction is not None
                        and s.transaction.status == "SUCCESS" and s.executed_at is not None
                        and _utc(s.executed_at) <= now and _utc(s.transaction.created_at) <= now for s in due)
        retention = {}
        for day in (30, 60, 90):
            # Calendar-day retention and daily activity deduplication must use
            # the same Dhaka boundaries, including the enrolment calendar day.
            today = local_datetime(now).date()
            mature = [p for p in cohort if local_datetime(p.enrolled_at).date() + timedelta(days=day + 7) <= today]
            retained = 0
            for participant in mature:
                start = local_datetime(participant.enrolled_at).date() + timedelta(days=day)
                end = start + timedelta(days=7)
                retained += any(e.kind == "ACTIVITY" and start <= local_datetime(e.created_at).date() < end for e in events_by_user[participant.user_id])
            retention[str(day)] = {"retained": retained, "eligible": len(mature), "rate": _ratio(retained, len(mature)), "immature": len(cohort) - len(mature)}
        mature_30 = [p for p in cohort if _utc(p.enrolled_at) + timedelta(days=30) <= now]
        transactions_30 = 0
        support_30 = 0
        for participant in mature_30:
            start, end = _utc(participant.enrolled_at), _utc(participant.enrolled_at) + timedelta(days=30)
            transactions_30 += sum(e.kind == "TRANSACTION" and start <= _utc(e.created_at) < end for e in events_by_user[participant.user_id])
            support_30 += sum(e.kind == "SUPPORT_CONTACT" and start <= _utc(e.created_at) < end for e in events_by_user[participant.user_id])
        research_rows = [row for row in feedback if row.kind == "RESEARCH" and row.user_id in cohort_ids]
        latest_research = {}
        for response in sorted(research_rows, key=lambda row: (_utc(row.created_at), row.id)):
            latest_research[response.user_id] = response
        research_participants = list(latest_research.values())
        arms[variant] = {
            "participants": len(cohort), "withdrawn": sum(p.withdrawn_at is not None for p in cohort),
            "exposed_participants": len({e.user_id for e in rows if e.kind == "EXPOSURE"}),
            "forecast_shown_participants": len({e.user_id for e in rows if e.kind == "FORECAST_SHOWN"}),
            "planning_tasks_started": len(starts), "planning_tasks_completed": len(completed),
            "planning_completion_rate": _ratio(len(completed), len(starts)),
            "planning_intention_to_treat_rate": _ratio(len(completed), len(cohort)),
            "recurring_tasks_started": len(recurring_starts), "recurring_tasks_completed": len(recurring_completed),
            "recurring_completion_rate": _ratio(len(recurring_completed), len(recurring_starts)),
            "auto_pay_due": len(due), "auto_pay_completed": successes,
            "auto_pay_completion_rate": _ratio(successes, len(due)), "auto_pay_cancelled": cancelled,
            "retention": retention, "mature_30_participants": len(mature_30),
            "transactions_first_30_days": transactions_30,
            "transactions_per_participant_30_days": _ratio(transactions_30, len(mature_30)),
            "support_reports_first_30_days": support_30,
            "support_reports_per_participant_30_days": _ratio(support_30, len(mature_30)),
            "research_responses": len(research_rows),
            "research": {
                "participants_responded": len(research_participants),
                "priority_problems": {problem: sum(row.problem == problem for row in research_participants) for problem in sorted(PROBLEMS)},
                "mean_usefulness": _ratio(sum(row.usefulness for row in research_participants), len(research_participants)),
                "mean_ease": _ratio(sum(row.ease for row in research_participants), len(research_participants)),
                "self_reported_missed_payments": sum(row.missed_payments_last_30_days for row in research_participants),
            },
        }
    def difference(key, multiplier=1):
        treatment, control = arms["treatment"][key], arms["control"][key]
        return (treatment - control) * multiplier if treatment is not None and control is not None else None
    return {
        "data_source": data_source, "payment_mode": PAYMENT_MODE,
        "as_of": now.isoformat(), "participants": len(participants), "unverified_real_participants": pending_real,
        "arms": arms, "planning_completion_uplift_pp": difference("planning_intention_to_treat_rate", 100),
        "planning_completion_among_started_uplift_pp": difference("planning_completion_rate", 100),
        "incremental_transactions_per_participant_30_days": difference("transactions_per_participant_30_days"),
        "support_report_reduction_per_participant_30_days": -difference("support_reports_per_participant_30_days") if difference("support_reports_per_participant_30_days") is not None else None,
        "small_cohort": any(arms[variant]["participants"] < 30 for variant in arms),
        "business_impact_validated": False,
        "limitations": ["Prototype payment counts are simulated; no real transaction, revenue or business uplift is established.",
                        "Unavailable rates have no eligible denominator; retention requires the full seven-day follow-up window.",
                        "Support reports are help issues recorded in this prototype, not external support-center contacts.",
                        "Small samples and self-reported research answers cannot establish customer impact."],
    }
