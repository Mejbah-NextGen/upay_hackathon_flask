"""Due-only, wallet-scoped demo payments with one atomic claim per installment."""

import calendar
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from sqlalchemy import update

from app.container import get_container
from app.domain.operations import ScheduledPayment
from app.extensions import db
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.recipient_service import lookup_recipient
from app.services.reporting_service import LOCAL_TIMEZONE, local_datetime


SCHEDULE_KINDS = {"SEND_MONEY": "Send Money", "MOBILE_RECHARGE": "Mobile Recharge", "BILL_PAYMENT": "Bill Payment"}


def utc_now():
    return datetime.now(timezone.utc)


def aware_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def add_months(value, count):
    index = value.year * 12 + value.month - 1 + count
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def scheduling_window(now=None):
    today = local_datetime(now or utc_now()).date()
    last_month = add_months(today.replace(day=1), 2)
    return today + timedelta(days=1), last_month.replace(day=calendar.monthrange(last_month.year, last_month.month)[1])


def scheduled_for_user(user_id):
    return ScheduledPayment.query.filter_by(user_id=user_id).order_by(ScheduledPayment.due_at, ScheduledPayment.id).all()


def upcoming_for_user(user_id):
    return ScheduledPayment.query.filter_by(user_id=user_id, status="SCHEDULED").order_by(ScheduledPayment.due_at).all()


def create_schedule(user_id, values, *, now=None):
    container = get_container()
    sender = container.wallet.get_user(user_id)
    kind = str(values.get("kind", "")).upper()
    if kind not in SCHEDULE_KINDS:
        raise ValidationError("Choose Send Money, Mobile Recharge or Bill Payment.")
    amount = container.wallet.parse_amount(values.get("amount", ""))
    frequency = values.get("frequency", "ONE_TIME")
    if frequency not in {"ONE_TIME", "MONTHLY"}:
        raise ValidationError("Choose one-time or monthly payment.")
    auto_pay = str(values.get("auto_pay", "1")) == "1"
    note = str(values.get("note", "") or "").strip()
    if len(note) > 255:
        raise ValidationError("Note must be 255 characters or fewer.")
    try:
        due_date = date.fromisoformat(str(values.get("due_date", "")))
    except (ValueError, TypeError):
        raise ValidationError("Choose a valid payment date.")
    first_date, last_date = scheduling_window(now)
    if not first_date <= due_date <= last_date:
        raise ValidationError(f"Choose a date from {first_date:%d %b %Y} to {last_date:%d %b %Y}.")
    provider = str(values.get("provider", "") or "").strip()
    category = str(values.get("category", "") or "").strip()
    if kind == "MOBILE_RECHARGE" and not provider:
        raise ValidationError("Choose a mobile operator.")
    details = lookup_recipient(kind, values.get("recipient_number", ""), provider=provider, category=category)
    if details["status"] == "blocked":
        raise ValidationError("Blocked number. This recipient cannot be scheduled.")
    if kind == "SEND_MONEY":
        if not details["can_transact"]:
            raise ValidationError("Not registered. Create a wallet before scheduling a transfer.")
        if details["number"] == sender.mobile:
            raise ValidationError("You cannot send money to your own number.")
    group = uuid4().hex
    dates = [due_date]
    if frequency == "MONTHLY":
        # Anchor every installment to the originally chosen day: Jan 31 becomes
        # Feb 28 and then Mar 31, rather than permanently drifting to the 28th.
        for month_offset in (1, 2):
            next_date = add_months(due_date, month_offset)
            if next_date <= last_date:
                dates.append(next_date)
    installments = []
    for scheduled_date in dates:
        installment = ScheduledPayment(
            user_id=user_id, kind=kind, recipient_number=details["number"],
            recipient_name=details["name"], provider=provider if kind != "SEND_MONEY" else "",
            category=category if kind == "BILL_PAYMENT" else "", amount=amount, note=note or None,
            frequency=frequency, auto_pay=auto_pay,
            due_at=datetime.combine(scheduled_date, time.min, LOCAL_TIMEZONE).astimezone(timezone.utc),
            recurrence_group=group, status="SCHEDULED",
        )
        db.session.add(installment)
        installments.append(installment)
    from app.services.pilot_service import record_schedule_created
    record_schedule_created(installments)
    db.session.commit()
    return installments


def cancel_schedule(user_id, schedule_id):
    schedule = ScheduledPayment.query.filter_by(id=schedule_id, user_id=user_id).first()
    if schedule is None:
        raise ValidationError("Scheduled payment not found.")
    if schedule.status not in {"SCHEDULED", "FAILED"}:
        raise ValidationError("Only pending or failed payments can be cancelled.")
    changed = db.session.execute(
        update(ScheduledPayment).where(ScheduledPayment.id == schedule.id, ScheduledPayment.user_id == user_id, ScheduledPayment.status.in_(["SCHEDULED", "FAILED"])).values(status="CANCELLED"),
        execution_options={"synchronize_session": "fetch"},
    )
    if changed.rowcount != 1:
        db.session.rollback()
        raise ValidationError("This payment has already been processed.")
    db.session.commit()
    return schedule


def execute_schedule(user_id, schedule_id, *, now=None):
    now = aware_utc(now or utc_now())
    schedule = ScheduledPayment.query.filter_by(id=schedule_id, user_id=user_id).first()
    if schedule is None:
        raise ValidationError("Scheduled payment not found.")
    if schedule.status == "COMPLETED":
        schedule.processed_now = False
        return schedule
    if schedule.status != "SCHEDULED":
        raise ValidationError("Only pending scheduled payments can be paid.")
    if aware_utc(schedule.due_at) > now:
        raise ValidationError("This payment is not due yet. No wallet balance has been deducted.")
    # The claim and both wallet ledger entries commit together. A concurrent runner
    # cannot claim this installment after it has completed, and rollback releases it.
    try:
        claim = db.session.execute(
            update(ScheduledPayment).where(
                ScheduledPayment.id == schedule.id, ScheduledPayment.user_id == user_id,
                ScheduledPayment.status == "SCHEDULED", ScheduledPayment.due_at <= now,
            ).values(status="PROCESSING"),
            execution_options={"synchronize_session": "fetch"},
        )
        if claim.rowcount != 1:
            db.session.rollback()
            result = db.session.get(ScheduledPayment, schedule_id)
            if result is not None:
                result.processed_now = False
            return result
        try:
            # Keep the claim locked while rolling back a rejected payment's
            # balance and ledger writes. Releasing the outer claim first would
            # let another runner process the same failed installment in the gap.
            with db.session.begin_nested():
                container = get_container()
                if schedule.kind == "SEND_MONEY":
                    transaction = container.wallet.send_money(user_id, schedule.recipient_number, schedule.amount, schedule.note or "", commit=False)
                elif schedule.kind == "MOBILE_RECHARGE":
                    transaction = container.payments.mobile_recharge(user_id, schedule.provider, schedule.recipient_number, schedule.amount, commit=False)
                elif schedule.kind == "BILL_PAYMENT":
                    transaction = container.payments.pay_bill(user_id, schedule.provider, schedule.recipient_number, schedule.amount, category=schedule.category, commit=False)
                else:
                    raise ValidationError("Unsupported scheduled payment type.")
                transaction.note = ("Scheduled payment #" + str(schedule.id) + (": " + schedule.note if schedule.note else ""))[:255]
                schedule.transaction_id = transaction.id
                schedule.status = "COMPLETED"
                schedule.executed_at = now
                schedule.last_error = None
        except (ValidationError, InsufficientBalanceError) as exc:
            schedule.status = "FAILED"
            schedule.last_error = str(exc)[:255]
        from app.services.pilot_service import record_schedule_execution
        record_schedule_execution(schedule, now=now)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    result = db.session.get(ScheduledPayment, schedule_id)
    result.processed_now = True
    return result


def run_due_payments(*, user_id=None, now=None):
    now = aware_utc(now or utc_now())
    query = ScheduledPayment.query.filter(ScheduledPayment.status == "SCHEDULED", ScheduledPayment.auto_pay.is_(True), ScheduledPayment.due_at <= now)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    ids = [(row.user_id, row.id) for row in query.order_by(ScheduledPayment.due_at, ScheduledPayment.id).all()]
    result = []
    for owner, schedule_id in ids:
        try:
            payment = execute_schedule(owner, schedule_id, now=now)
        except ValidationError:
            # A user can cancel, or another worker can finish/fail, after this
            # runner selects its due IDs. Treat that expected race as a no-op.
            db.session.rollback()
            current = ScheduledPayment.query.filter_by(id=schedule_id, user_id=owner).populate_existing().first()
            if current is None or current.status != "SCHEDULED" or aware_utc(current.due_at) > now:
                continue
            raise
        if payment is not None and getattr(payment, "processed_now", True):
            result.append(payment)
    return result
