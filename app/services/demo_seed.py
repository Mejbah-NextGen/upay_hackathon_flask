"""Idempotent local fixtures; seeding never rewrites balances or existing records."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.domain.models import Transaction, User
from app.domain.operations import RecipientRegistration, ScheduledPayment
from app.extensions import db
from app.services.reporting_service import LOCAL_TIMEZONE, local_datetime
from app.services.schedule_service import add_months
from app.services.service_catalog import BILL_CATEGORIES


DEMO_RECIPIENT_MOBILE = "01944000001"
DEMO_AGENT_MOBILE = "01944000002"
DEMO_RECHARGE_MOBILE = "01944000003"
DEMO_BLOCKED_MOBILE = "01944000099"


def seed_demo_operations(user, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = local_datetime(now).date()
    if not User.query.filter_by(mobile=DEMO_RECIPIENT_MOBILE).first():
        db.session.add(User(full_name="Demo Recipient Ayesha", mobile=DEMO_RECIPIENT_MOBILE, balance=Decimal("1000.00"), verified=True))
    registry = (
        (DEMO_AGENT_MOBILE, "", "CASH_OUT", "Demo Authorized Agent", "REGISTERED", None),
        (DEMO_RECHARGE_MOBILE, "", "MOBILE_RECHARGE", "Demo Subscriber Rafi", "REGISTERED", None),
        (DEMO_BLOCKED_MOBILE, "", "ANY", "Demo Flagged Recipient", "BLOCKED", "Fraud flag supplied only as a demonstration fixture."),
        ("DEMO-METER-1001", "DESCO Electricity", "BILL_PAYMENT", "Demo Household Electricity", "REGISTERED", None),
        ("DEMO-GAS-1001", "Titas Gas", "BILL_PAYMENT", "Demo Household Gas", "REGISTERED", None),
        ("DEMO-BLOCKED-1001", "", "ANY", "Demo Flagged Bill Account", "BLOCKED", "Demonstration blocked account."),
    )
    for number, provider, kind, name, status, reason in registry:
        if not RecipientRegistration.query.filter_by(number=number, provider=provider, kind=kind).first():
            db.session.add(RecipientRegistration(number=number, provider=provider, kind=kind, name=name, status=status, reason=reason))

    # These are explicitly labelled imported sample records. The existing wallet
    # balance is the demo opening balance, not recomputed from generated fixtures.
    kinds = ("ADD_MONEY", "SEND_MONEY", "RECEIVE_MONEY", "CASH_OUT", "MOBILE_RECHARGE", "BILL_PAYMENT")
    labels = {"ADD_MONEY": "Add Money", "SEND_MONEY": "Send Money", "RECEIVE_MONEY": "Received Money", "CASH_OUT": "Cash Out", "MOBILE_RECHARGE": "Mobile Recharge", "BILL_PAYMENT": "Bill Payment"}
    existing_refs = {row[0] for row in db.session.query(Transaction.reference).filter(Transaction.user_id == user.id, Transaction.reference.like("DEMO120-%")).all()}
    for offset in range(119, -1, -1):
        day = today - timedelta(days=offset)
        reference = f"DEMO120-{user.id}-{day:%Y%m%d}"
        if reference in existing_refs:
            continue
        kind = kinds[day.toordinal() % len(kinds)]
        amount = Decimal((day.toordinal() % 9 + 1) * 50).quantize(Decimal("0.01"))
        fee = (amount * Decimal("0.015")).quantize(Decimal("0.01")) if kind == "CASH_OUT" else Decimal("0.00")
        counterparty = {"ADD_MONEY": "Bank Account", "SEND_MONEY": "Demo Recipient Ayesha", "RECEIVE_MONEY": "Demo Sender Karim", "CASH_OUT": DEMO_AGENT_MOBILE, "MOBILE_RECHARGE": f"Grameenphone • {DEMO_RECHARGE_MOBILE}", "BILL_PAYMENT": "DESCO Electricity • DEMO-METER-1001"}[kind]
        title = labels[kind]
        if kind == "BILL_PAYMENT":
            category = list(BILL_CATEGORIES.values())[(day.toordinal() // len(kinds)) % len(BILL_CATEGORIES)]
            title = category["label"] + " Payment"
            counterparty = category["providers"][0] + " • DEMO-ACCOUNT-1001"
        timestamp = datetime.combine(day, time(9 + day.toordinal() % 8, 15), LOCAL_TIMEZONE).astimezone(timezone.utc)
        # Keep today's fixture earlier than the seed run.
        if timestamp > now:
            timestamp = now
        db.session.add(Transaction(user_id=user.id, kind=kind, direction="IN" if kind in {"ADD_MONEY", "RECEIVE_MONEY"} else "OUT", title=title, counterparty=counterparty, reference=reference, amount=amount, fee=fee, status="SUCCESS", note="Imported demo history; the existing wallet opening balance is preserved.", created_at=timestamp))

    first_month = add_months(today.replace(day=1), 1)
    second_month = add_months(today.replace(day=1), 2)
    demo_schedules = (
        (first_month.replace(day=5), "BILL_PAYMENT", "DEMO-METER-1001", "Demo Household Electricity", "DESCO Electricity", "electricity", "620.00", "MONTHLY", True, "electricity"),
        (second_month.replace(day=5), "BILL_PAYMENT", "DEMO-METER-1001", "Demo Household Electricity", "DESCO Electricity", "electricity", "620.00", "MONTHLY", True, "electricity"),
        (first_month.replace(day=12), "MOBILE_RECHARGE", DEMO_RECHARGE_MOBILE, "Demo Subscriber Rafi", "Grameenphone", "", "200.00", "ONE_TIME", True, "recharge"),
        (second_month.replace(day=20), "SEND_MONEY", DEMO_RECIPIENT_MOBILE, "Demo Recipient Ayesha", "", "", "500.00", "ONE_TIME", False, "transfer"),
    )
    for day, kind, number, name, provider, category, amount, frequency, automatic, group in demo_schedules:
        seed_key = f"DEMO-SCHEDULE-{user.id}-{group}-{day:%Y%m%d}"
        if ScheduledPayment.query.filter_by(seed_key=seed_key).first():
            continue
        db.session.add(ScheduledPayment(user_id=user.id, kind=kind, recipient_number=number, recipient_name=name, provider=provider, category=category, amount=Decimal(amount), note="Demo future payment; cancel or edit by creating a new plan.", frequency=frequency, auto_pay=automatic, due_at=datetime.combine(day, time.min, LOCAL_TIMEZONE).astimezone(timezone.utc), recurrence_group=f"DEMO-{user.id}-{group}-{first_month:%Y%m}", seed_key=seed_key, status="SCHEDULED"))
    db.session.commit()
