"""Synthetic fixtures, with an explicit reset-only reconciled household ledger.

Startup fixtures remain compatible with older wallets and never alter their
balances. The reset generator records independent opening balances instead.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib

from app.domain.models import Transaction, User
from app.domain.operations import RecipientRegistration, ScheduledPayment
from app.domain.demo import DemoDataset, WalletOpeningBalance
from app.domain.assistant import AssistantConversation
from app.domain.notifications import NotificationReadReceipt, NotificationReadState
from app.domain.payment_plans import PaymentInvoice, PaymentSubmission, PayLaterAccount, PayLaterPurchase, SavingsPlan
from app.domain.preferences import DisplayPreference, UserPreference
from app.domain.profiles import UserProfile
from app.domain.wallet_submissions import WalletSubmission
from app.extensions import db
from app.services.reporting_service import LOCAL_TIMEZONE, local_datetime
from app.services.schedule_service import add_months
from app.services.service_catalog import BILL_CATEGORIES


DEMO_RECIPIENT_MOBILE = "01944000001"
DEMO_AGENT_MOBILE = "01944000002"
DEMO_RECHARGE_MOBILE = "01944000003"
DEMO_BLOCKED_MOBILE = "01944000099"
DEMO_MAIN_MOBILE = "01329097775"
DEMO_SENDER_MOBILE = "01944000004"
DEMO_LANDLORD_MOBILE = "01944000005"
DEMO_GENERATOR_VERSION = "household-ledger-v2"
DEMO_HISTORY_DAYS = 120


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

    # History is an anchored dataset, not a moving window appended on startup.
    # Explicit reset is the only way to replace it with a new 120-day period.
    if Transaction.query.filter(Transaction.user_id == user.id, Transaction.reference.like("DEMO120-%")).first():
        db.session.commit()
        return

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
        counterparty = {"ADD_MONEY": "Bank Account", "SEND_MONEY": "Demo Recipient Ayesha", "RECEIVE_MONEY": "Demo Sender Karim", "CASH_OUT": DEMO_AGENT_MOBILE, "MOBILE_RECHARGE": f"Banglalink • {DEMO_RECHARGE_MOBILE}", "BILL_PAYMENT": "DESCO Electricity • DEMO-METER-1001"}[kind]
        title = labels[kind]
        if kind == "BILL_PAYMENT":
            category = list(BILL_CATEGORIES.values())[(day.toordinal() // len(kinds)) % len(BILL_CATEGORIES)]
            title = category["label"] + " Payment"
            counterparty = category["providers"][0] + " • DEMO-ACCOUNT-1001"
        timestamp = datetime.combine(day, time(9 + day.toordinal() % 8, 15), LOCAL_TIMEZONE).astimezone(timezone.utc)
        # Keep today's fixture earlier than the seed run.
        if timestamp > now:
            timestamp = now
        db.session.add(Transaction(user_id=user.id, kind=kind, direction="IN" if kind in {"ADD_MONEY", "RECEIVE_MONEY"} else "OUT", title=title, counterparty=counterparty, reference=reference, amount=amount, fee=fee, status="SUCCESS", note="Synthetic legacy demo history; existing balance preserved; opening anchor unavailable.", created_at=timestamp))

    first_month = add_months(today.replace(day=1), 1)
    second_month = add_months(today.replace(day=1), 2)
    demo_schedules = (
        (first_month.replace(day=5), "BILL_PAYMENT", "DEMO-METER-1001", "Demo Household Electricity", "DESCO Electricity", "electricity", "620.00", "MONTHLY", True, "electricity"),
        (second_month.replace(day=5), "BILL_PAYMENT", "DEMO-METER-1001", "Demo Household Electricity", "DESCO Electricity", "electricity", "620.00", "MONTHLY", True, "electricity"),
        (first_month.replace(day=12), "MOBILE_RECHARGE", DEMO_RECHARGE_MOBILE, "Demo Subscriber Rafi", "Banglalink", "", "200.00", "ONE_TIME", True, "recharge"),
        (second_month.replace(day=20), "SEND_MONEY", DEMO_RECIPIENT_MOBILE, "Demo Recipient Ayesha", "", "", "500.00", "ONE_TIME", False, "transfer"),
    )
    for day, kind, number, name, provider, category, amount, frequency, automatic, group in demo_schedules:
        seed_key = f"DEMO-SCHEDULE-{user.id}-{group}-{day:%Y%m%d}"
        if ScheduledPayment.query.filter_by(seed_key=seed_key).first():
            continue
        db.session.add(ScheduledPayment(user_id=user.id, kind=kind, recipient_number=number, recipient_name=name, provider=provider, category=category, amount=Decimal(amount), note="Demo future payment; cancel or edit by creating a new plan.", frequency=frequency, auto_pay=automatic, due_at=datetime.combine(day, time.min, LOCAL_TIMEZONE).astimezone(timezone.utc), recurrence_group=f"DEMO-{user.id}-{group}-{first_month:%Y%m}", seed_key=seed_key, status="SCHEDULED"))
    db.session.commit()


def seed_reconciled_demo_dataset(*, as_of: date, generated_at=None):
    """Seed an empty database in one transaction; never replace an existing wallet.

    Amounts and references are deterministic for ``as_of``. Every date has a
    shared-household expense, with monthly income, rent and utilities plus
    weekly cash withdrawals/recharges. Internal transfers have both ledger sides.
    """
    if any(db.session.execute(db.select(db.func.count()).select_from(table)).scalar_one()
           for table in db.metadata.sorted_tables):
        raise ValueError("Reconciled demo seed requires an empty database. Use the backup-protected reset script.")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("as_of must be a calendar date.")
    start = as_of - timedelta(days=DEMO_HISTORY_DAYS - 1)
    generated_at = generated_at or datetime.now(timezone.utc)
    run_key = f"DEMO120-{as_of:%Y%m%d}"
    opening_at = datetime.combine(start, time.min, LOCAL_TIMEZONE).astimezone(timezone.utc)
    # A full calendar day is intentional when an explicit --as-of date is used.
    stamp = lambda day, hour=12, minute=0: datetime.combine(day, time(hour, minute), LOCAL_TIMEZONE).astimezone(timezone.utc)
    owners = {}
    opening_values = {
        DEMO_MAIN_MOBILE: ("Demo Household", "12450.00"),
        DEMO_RECIPIENT_MOBILE: ("Demo Recipient Ayesha", "1000.00"),
        DEMO_SENDER_MOBILE: ("Demo Sender Karim", "25000.00"),
        DEMO_LANDLORD_MOBILE: ("Demo Landlord Rahman", "2000.00"),
    }
    for mobile, (name, opening) in opening_values.items():
        owner = User(full_name=name, mobile=mobile, email=f"demo-{mobile[-4:]}@example.invalid",
                     balance=Decimal(opening), verified=True, created_at=opening_at)
        db.session.add(owner)
        db.session.flush()
        owners[mobile] = owner
        db.session.add(WalletOpeningBalance(user_id=owner.id, opening_balance=Decimal(opening),
                                          recorded_at=opening_at, source=f"Synthetic opening fixture / {DEMO_GENERATOR_VERSION}"))
        db.session.add(UserPreference(user_id=owner.id, notifications_enabled=True))
        db.session.add(DisplayPreference(user_id=owner.id, language="en", theme="system"))
        db.session.add(UserProfile(user_id=owner.id, nickname="Household" if mobile == DEMO_MAIN_MOBILE else name.replace("Demo ", ""),
                                  address="Synthetic household, Dhaka, Bangladesh"))
    main = owners[DEMO_MAIN_MOBILE]
    events = []
    sequence = 0

    def transaction(owner, day, kind, direction, amount, counterparty, note, *, hour=12, minute=0, fee="0.00", reference=None, status="SUCCESS"):
        nonlocal sequence
        sequence += 1
        reference = reference or f"{run_key}-{day:%Y%m%d}-{sequence:04d}"
        titles = {"ADD_MONEY": "Add Money", "SEND_MONEY": "Send Money", "RECEIVE_MONEY": "Received Money",
                  "CASH_OUT": "Cash Out", "MOBILE_RECHARGE": "Mobile Recharge", "BILL_PAYMENT": "Bill Payment",
                  "PAY_LATER_PURCHASE": "Pay Later Purchase", "PAY_LATER_REPAYMENT": "Pay Later Repayment"}
        row = Transaction(user_id=owner.id, kind=kind, direction=direction, title=titles[kind], counterparty=counterparty,
                          reference=reference, amount=Decimal(str(amount)), fee=Decimal(str(fee)), status=status,
                          note=("Synthetic demo: " + note)[:255], created_at=stamp(day, hour, minute))
        db.session.add(row)
        events.append((owner, row))
        return row

    def transfer(sender, receiver, day, amount, note, *, hour=12):
        debit = transaction(sender, day, "SEND_MONEY", "OUT", amount, receiver.full_name, note, hour=hour)
        transaction(receiver, day, "RECEIVE_MONEY", "IN", amount, sender.full_name, note, hour=hour, reference=debit.reference)
        return debit

    def bill(day, category, provider, account, amount):
        row = transaction(main, day, "BILL_PAYMENT", "OUT", amount, f"{provider} / {account}", f"{category} household bill", hour=15)
        row.title = f"{category.replace('-', ' ').title()} Payment"
        db.session.flush()
        invoice = PaymentInvoice(user_id=main.id, transaction_id=row.id, invoice_number=f"INV-{row.reference}",
                                 category=category, provider=provider, account_reference=account,
                                 invoice_reference=f"DEMO-{category.upper()}-{day:%Y%m}")
        row.note = f"Synthetic demo: {category} household bill; invoice: {invoice.invoice_number}."
        db.session.add(invoice)
        token = hashlib.sha256(f"payment:{row.reference}".encode()).hexdigest()[:32]
        db.session.add(PaymentSubmission(user_id=main.id, token=token, transaction_id=row.id))
        return row

    # Savings held before the displayed history are moved into the wallet.
    transaction(main, start, "ADD_MONEY", "IN", "20000.00", "Bank Account", "Opening-month reserve from demo bank account ending 1001", hour=8)
    for offset in range(DEMO_HISTORY_DAYS):
        day = start + timedelta(days=offset)
        serial = day.toordinal()
        if day.day == 5:
            transaction(main, day, "ADD_MONEY", "IN", "38500.00", "Bank Account", "Monthly salary funding from demo employer bank account ending 1001", hour=8)
        if offset % 13 == 8:
            transaction(main, day, "ADD_MONEY", "IN", 1000 + serial % 4 * 250, "Debit / Credit Card", "Demo card funding ending 1111", hour=9)
        if offset % 9 == 4:
            transfer(owners[DEMO_SENDER_MOBILE], main, day, 600 + serial % 5 * 150, "Freelance tutoring and shared-expense reimbursement", hour=9)
        transfer(main, owners[DEMO_RECIPIENT_MOBILE], day, 90 + serial % 8 * 25,
                 ("Shared household groceries" if day.weekday() in {4, 5} else "Shared household food and commuting"), hour=11)
        if day.day == 7:
            transfer(main, owners[DEMO_LANDLORD_MOBILE], day, "9500.00", "Monthly household rent", hour=14)
        if day.day == 10:
            bill(day, "electricity", "DESCO Electricity", "DEMO-METER-1001", 1050 + day.month % 4 * 90)
        if day.day == 12:
            bill(day, "gas", "Titas Gas", "DEMO-GAS-1001", "1080.00")
        if day.day == 15:
            bill(day, "internet", "Demo Broadband", "DEMO-NET-1001", "800.00")
        if day.day == 19:
            bill(day, "water", "Demo Water Utility", "DEMO-WATER-1001", "360.00")
        if offset % 7 == 2:
            transaction(main, day, "MOBILE_RECHARGE", "OUT", 100 + serial % 4 * 50,
                        f"Banglalink / {DEMO_RECHARGE_MOBILE}", "Weekly demo mobile recharge", hour=17)
        if day.weekday() == 4:
            amount = Decimal(1000 + serial % 3 * 250)
            transaction(main, day, "CASH_OUT", "OUT", amount, f"Demo Authorized Agent / {DEMO_AGENT_MOBILE}",
                        "Weekly cash budget; demo Agent fee 1.50%", hour=16, fee=(amount * Decimal("0.015")).quantize(Decimal("0.01")))

    # Deliberate review examples are legitimate successful demo receipts. They
    # demonstrate explainable checks, never establish a fraud allegation.
    for minute in (0, 3):
        transaction(main, as_of - timedelta(days=2), "MOBILE_RECHARGE", "OUT", "100.00",
                    f"Banglalink / {DEMO_RECHARGE_MOBILE}",
                    "Review example: two separately confirmed top-ups close together; check both receipts", hour=19, minute=minute)
    transaction(main, as_of - timedelta(days=1), "MOBILE_RECHARGE", "OUT", "1500.00",
                f"Banglalink / {DEMO_RECHARGE_MOBILE}",
                "Review example: unusually large family recharge package; confirm the intended amount", hour=19)

    # One repaid and one pending deferred purchase demonstrate true wallet
    # accounting: a DEFERRED purchase changes credit exposure, not wallet cash.
    for index, (age, merchant, amount, repaid) in enumerate(((21, "Demo Bookshop", "1250.00", True), (3, "Demo Pharmacy", "840.00", False)), 1):
        purchase_day = as_of - timedelta(days=age)
        row = transaction(main, purchase_day, "PAY_LATER_PURCHASE", "OUT", amount, merchant,
                          "Deferred demo purchase; wallet unchanged", hour=18, status="DEFERRED")
        db.session.flush()
        purchase = PayLaterPurchase(user_id=main.id, merchant=merchant, invoice_no=f"DEMO-SHOP-{index:03d}",
                                   amount=Decimal(amount), due_on=purchase_day + timedelta(days=30 if repaid else 7),
                                   status="REPAID" if repaid else "PENDING", purchase_transaction_id=row.id,
                                   created_at=row.created_at)
        if repaid:
            repayment = transaction(main, as_of - timedelta(days=7), "PAY_LATER_REPAYMENT", "OUT", amount,
                                    merchant, f"Repayment of demo purchase DEMO-SHOP-{index:03d}", hour=18)
            db.session.flush()
            purchase.repayment_transaction_id = repayment.id
            purchase.repaid_at = repayment.created_at
        db.session.add(purchase)
    db.session.add(PayLaterAccount(user_id=main.id, outstanding=Decimal("840.00")))

    # Apply the chronological successful ledger to each independently recorded
    # opening fixture and fail the whole seed if any wallet would go negative.
    for owner, row in sorted(events, key=lambda event: (event[1].created_at, event[1].reference, event[1].direction)):
        if row.status != "SUCCESS":
            continue
        change = row.amount if row.direction == "IN" else -(row.amount + row.fee)
        owner.balance += change
        if owner.balance < 0:
            raise ValueError(f"Synthetic generator produced a negative balance for {owner.mobile}.")
    db.session.flush()

    registry = (
        (DEMO_AGENT_MOBILE, "", "CASH_OUT", "Demo Authorized Agent", "REGISTERED", None),
        (DEMO_RECHARGE_MOBILE, "", "MOBILE_RECHARGE", "Demo Subscriber Rafi", "REGISTERED", None),
        (DEMO_BLOCKED_MOBILE, "", "ANY", "Demo Flagged Recipient", "BLOCKED", "Synthetic fraud flag; no real allegation."),
        ("DEMO-METER-1001", "DESCO Electricity", "BILL_PAYMENT", "Demo Household Electricity", "REGISTERED", None),
        ("DEMO-GAS-1001", "Titas Gas", "BILL_PAYMENT", "Demo Household Gas", "REGISTERED", None),
        ("DEMO-NET-1001", "Demo Broadband", "BILL_PAYMENT", "Demo Household Internet", "REGISTERED", None),
        ("DEMO-WATER-1001", "Demo Water Utility", "BILL_PAYMENT", "Demo Household Water", "REGISTERED", None),
        ("DEMO-BLOCKED-1001", "", "ANY", "Demo Flagged Bill Account", "BLOCKED", "Synthetic blocked bill account."),
    )
    for number, provider, kind, name, status, reason in registry:
        db.session.add(RecipientRegistration(number=number, provider=provider, kind=kind, name=name, status=status, reason=reason, created_at=opening_at))

    next_month = add_months(as_of.replace(day=1), 1)
    schedules = ((5, "BILL_PAYMENT", "DEMO-METER-1001", "Demo Household Electricity", "DESCO Electricity", "electricity", "1320.00", "MONTHLY", True),
                 (12, "MOBILE_RECHARGE", DEMO_RECHARGE_MOBILE, "Demo Subscriber Rafi", "Banglalink", "", "200.00", "ONE_TIME", True),
                 (20, "SEND_MONEY", DEMO_RECIPIENT_MOBILE, "Demo Recipient Ayesha", "", "", "500.00", "ONE_TIME", False))
    for day_number, kind, number, name, provider, category, amount, frequency, auto_pay in schedules:
        months = (next_month, add_months(next_month, 1)) if frequency == "MONTHLY" else (next_month,)
        for month in months:
            due = month.replace(day=day_number)
            db.session.add(ScheduledPayment(user_id=main.id, kind=kind, recipient_number=number, recipient_name=name, provider=provider,
                                            category=category, amount=Decimal(amount), note="Synthetic future plan; no advance debit.",
                                            frequency=frequency, auto_pay=auto_pay, due_at=stamp(due, 0), status="SCHEDULED",
                                            recurrence_group=f"DEMO-{kind}", seed_key=f"{run_key}-{kind}-{due:%Y%m%d}", created_at=stamp(as_of, 18)))
    db.session.add(ScheduledPayment(user_id=main.id, kind="BILL_PAYMENT", recipient_number="DEMO-METER-1001",
                                    recipient_name="Demo Household Electricity", provider="DESCO Electricity", category="electricity",
                                    amount=Decimal("620.00"), note="Synthetic near-term manual bill for cash-flow planning; no advance debit.",
                                    frequency="ONE_TIME", auto_pay=False, due_at=stamp(as_of + timedelta(days=3), 0), status="SCHEDULED",
                                    recurrence_group="DEMO-NEAR-TERM", seed_key=f"{run_key}-NEAR-TERM", created_at=stamp(as_of, 18)))
    for name, amount, months, age in (("Demo emergency fund", "1500.00", 12, 30), ("Demo education fund", "1000.00", 6, 7)):
        starts = as_of - timedelta(days=age)
        monthly = Decimal(amount)
        contribution = monthly * months
        estimated = (monthly * Decimal("0.10") / 12 * Decimal(months * (months + 1)) / 2).quantize(Decimal("0.01"))
        db.session.add(SavingsPlan(user_id=main.id, name=name, monthly_amount=monthly, months=months, annual_rate=Decimal("0.10"),
                                  contribution_total=contribution, estimated_return=estimated, starts_on=starts,
                                  matures_on=add_months(starts, months), status="SAVED", created_at=stamp(starts, 18)))

    for owner in owners.values():
        rows = sorted((row for item_owner, row in events if item_owner.id == owner.id), key=lambda row: (row.created_at, row.id))
        # Mark all except each user's three most recent transactions read.
        for row in rows[:-3]:
            db.session.add(NotificationReadReceipt(user_id=owner.id, transaction_id=row.id, read_at=stamp(as_of, 18)))
        db.session.add(NotificationReadState(user_id=owner.id, last_read_transaction_id=0, updated_at=stamp(as_of, 18)))
        db.session.add(AssistantConversation(user_id=owner.id, messages="[]"))
    # Keep sample successful form receipts, with a non-replayable synthetic
    # fingerprint, to demonstrate the persisted deduplication topology.
    for owner, row in events:
        if owner.id == main.id and row.kind in {"ADD_MONEY", "CASH_OUT", "SEND_MONEY"}:
            db.session.add(WalletSubmission(user_id=main.id, token=hashlib.sha256(f"wallet:{row.reference}".encode()).hexdigest()[:32],
                                           fingerprint=hashlib.sha256(f"synthetic:{row.reference}".encode()).hexdigest(), transaction_id=row.id))
    db.session.add(DemoDataset(run_key=run_key, starts_on=start, ends_on=as_of, generated_at=generated_at,
                              generator_version=DEMO_GENERATOR_VERSION, synthetic=True,
                              description="Generated Bangladeshi household demonstration; no real customer records. Independent opening balances, mirrored wallet transfers and fee-inclusive ledger. Full as-of calendar day."))
    db.session.commit()
    return {
        "synthetic": True, "generator_version": DEMO_GENERATOR_VERSION, "run_key": run_key,
        "start_date": start.isoformat(), "end_date": as_of.isoformat(), "days": DEMO_HISTORY_DAYS,
        "primary_mobile": DEMO_MAIN_MOBILE, "primary_name": main.full_name,
        "primary_opening_balance": "12450.00", "primary_balance": str(main.balance),
        "primary_transactions": sum(owner.id == main.id for owner, row in events),
        "transactions": len(events), "users": len(owners),
        "table_counts": {table.name: db.session.execute(db.select(db.func.count()).select_from(table)).scalar_one() for table in db.metadata.sorted_tables},
        "wallet_balances": {mobile: str(owner.balance) for mobile, owner in owners.items()},
    }
