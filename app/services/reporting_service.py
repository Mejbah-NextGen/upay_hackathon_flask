"""Wallet history reporting using Bangladesh calendar days and UTC storage."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


LOCAL_TIMEZONE = timezone(timedelta(hours=6), "Asia/Dhaka")
PAYMENT_KINDS = frozenset({"MOBILE_RECHARGE", "BILL_PAYMENT"})


def parse_days(raw_days, default=1):
    """Accept a whole-day range and constrain it to the supported 1–90 days."""
    if raw_days is None or str(raw_days).strip() == "":
        return default
    try:
        return min(90, max(1, int(str(raw_days).strip())))
    except (TypeError, ValueError):
        return default


def local_datetime(value):
    """SQLite returns naive datetimes for the application's UTC timestamps."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TIMEZONE)


def period_dates(days, now=None):
    today = local_datetime(now or datetime.now(timezone.utc)).date()
    return today - timedelta(days=days - 1), today


def filter_transactions(transactions, *, days=None, direction="", kind="", query="", now=None):
    days = parse_days(days, default=None)
    dates = period_dates(days, now) if days is not None else None
    query = query.strip().casefold()
    selected = []
    for tx in transactions:
        if dates is not None:
            tx_date = local_datetime(tx.created_at).date()
            if not dates[0] <= tx_date <= dates[1]:
                continue
        if direction and tx.direction != direction:
            continue
        if kind == "payments":
            if tx.kind not in PAYMENT_KINDS:
                continue
        elif kind and tx.kind != kind:
            continue
        if query:
            text = " ".join(
                str(value or "")
                for value in (tx.title, tx.counterparty, tx.reference, tx.note, tx.kind)
            ).casefold()
            if query not in text:
                continue
        selected.append(tx)
    return sorted(selected, key=lambda tx: local_datetime(tx.created_at), reverse=True)


def transaction_totals(transactions):
    transactions = list(transactions)
    completed = [tx for tx in transactions if tx.status == "SUCCESS"]
    payment_total = sum(
        (Decimal(tx.amount) for tx in completed if tx.direction == "OUT" and tx.kind in PAYMENT_KINDS),
        Decimal("0.00"),
    )
    outgoing_total = sum(
        (Decimal(tx.amount) + Decimal(tx.fee or 0) for tx in completed if tx.direction == "OUT"),
        Decimal("0.00"),
    )
    incoming_total = sum(
        (Decimal(tx.amount) for tx in completed if tx.direction == "IN"), Decimal("0.00")
    )
    return {
        "transaction_count": len(transactions),
        "payment_total": payment_total,
        "outgoing_total": outgoing_total,
        "incoming_total": incoming_total,
    }


def dashboard_report(balance, transactions, *, days=1, now=None):
    days = parse_days(days)
    selected = filter_transactions(transactions, days=days, now=now)
    start_date, end_date = period_dates(days, now)
    return {
        **transaction_totals(selected),
        "balance": Decimal(balance),
        "days": days,
        "period_label": "Today" if days == 1 else f"Last {days} days",
        "card_prefix": "Today's" if days == 1 else f"Last {days} days",
        "start_date": start_date,
        "end_date": end_date,
        "transactions": selected,
        "recent": selected[:6],
    }
