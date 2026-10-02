"""Wallet history reporting using Bangladesh calendar days and UTC storage."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


LOCAL_TIMEZONE = timezone(timedelta(hours=6), "Asia/Dhaka")
PAYMENT_KINDS = frozenset({"MOBILE_RECHARGE", "BILL_PAYMENT"})
MAX_REPORT_DAYS = 120


def parse_days(raw_days, default=1):
    """Accept a whole-day range and constrain it to the supported 1-120 days."""
    if raw_days is None or str(raw_days).strip() == "":
        return default
    try:
        return min(MAX_REPORT_DAYS, max(1, int(str(raw_days).strip())))
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


def filter_transactions(transactions, *, days=None, direction="", kind="", query="", status="", start_date=None, end_date=None, now=None):
    days = parse_days(days, default=None)
    dates = period_dates(days, now) if days is not None else None
    query = query.strip().casefold()
    selected = []
    for tx in transactions:
        if dates is not None:
            tx_date = local_datetime(tx.created_at).date()
            if not dates[0] <= tx_date <= dates[1]:
                continue
        tx_date = local_datetime(tx.created_at).date()
        if start_date and tx_date < start_date:
            continue
        if end_date and tx_date > end_date:
            continue
        if direction and tx.direction != direction:
            continue
        if status and tx.status != status:
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
        "completed_count": len(completed),
        "other_count": len(transactions) - len(completed),
        "fees_total": sum((Decimal(tx.fee or 0) for tx in completed if tx.direction == "OUT"), Decimal("0.00")),
        "net_change": incoming_total - outgoing_total,
        "payment_total": payment_total,
        "outgoing_total": outgoing_total,
        "incoming_total": incoming_total,
    }


def wallet_change(transaction):
    """The actual ledger effect; incomplete records never change the wallet."""
    if transaction.status != "SUCCESS":
        return Decimal("0.00")
    amount = Decimal(transaction.amount)
    return amount if transaction.direction == "IN" else -(amount + Decimal(transaction.fee or 0))


def report_visualization(transactions):
    """Chart data for precisely the same scoped, filtered ledger as the report.

    Successful outgoing values include fees. Cumulative net change starts at zero;
    it is a change within the selected period, never an inferred wallet balance.
    Histogram bins count successful outgoing wallet deductions, with a distinct
    overflow bin so no unusually large transaction can disappear from the chart.
    """
    records = list(transactions)
    completed = [tx for tx in records if tx.status == "SUCCESS"]
    daily, categories, deductions = {}, {}, []
    zero = Decimal("0.00")
    for tx in completed:
        day = local_datetime(tx.created_at).date().isoformat()
        row = daily.setdefault(day, {"incoming": zero, "outgoing": zero})
        if tx.direction == "IN":
            row["incoming"] += Decimal(tx.amount)
        elif tx.direction == "OUT":
            deduction = Decimal(tx.amount) + Decimal(tx.fee or 0)
            row["outgoing"] += deduction
            categories[tx.kind] = categories.get(tx.kind, zero) + deduction
            deductions.append(deduction)
    cumulative_in, cumulative_out = zero, zero
    daily_rows = []
    for day, row in sorted(daily.items()):
        cumulative_in += row["incoming"]
        cumulative_out += row["outgoing"]
        daily_rows.append({
            "date": day, "incoming": float(row["incoming"]), "outgoing": float(row["outgoing"]),
            "net": float(row["incoming"] - row["outgoing"]),
            "cumulative_incoming": float(cumulative_in), "cumulative_outgoing": float(cumulative_out),
            "cumulative_net": float(cumulative_in - cumulative_out),
        })
    category_rows = [
        {"kind": kind, "label": kind.replace("_", " ").title(), "amount": float(amount)}
        for kind, amount in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    boundaries = [(0, 500), (500, 1000), (1000, 5000), (5000, 10000), (10000, 50000), (50000, None)]
    histogram, running_count = [], 0
    for lower, upper in boundaries:
        count = sum(1 for value in deductions if value >= lower and (upper is None or value < upper))
        running_count += count
        label = f"{lower:,}+" if upper is None else f"{lower:,}–<{upper:,}"
        histogram.append({
            "lower": lower, "upper": upper, "label": label, "count": count,
            "cumulative_count": running_count,
            "cumulative_percent": round(running_count * 100 / len(deductions), 2) if deductions else 0,
        })
    return {
        "daily": daily_rows, "categories": category_rows, "histogram": histogram,
        "successful_count": len(completed), "outgoing_count": len(deductions),
        "excluded_count": len(records) - len(completed),
        "incoming_total": float(cumulative_in), "outgoing_total": float(cumulative_out),
        "net_change": float(cumulative_in - cumulative_out),
        "largest_category": category_rows[0] if category_rows else None,
        "largest_category_percent": round(category_rows[0]["amount"] * 100 / float(cumulative_out), 1) if category_rows and cumulative_out else 0,
    }


def filter_schedules(schedules, *, direction="", kind="", query="", status="", start_date=None, end_date=None):
    """Due dates are distinct from the historical transaction period."""
    if direction == "IN":
        return []
    query = query.strip().casefold()
    result = []
    for item in schedules:
        due = local_datetime(item.due_at).date()
        if start_date and due < start_date or end_date and due > end_date:
            continue
        if status and item.status != status:
            continue
        if kind == "payments" and item.kind not in PAYMENT_KINDS:
            continue
        if kind and kind != "payments" and item.kind != kind:
            continue
        text = " ".join(str(getattr(item, field, "") or "") for field in (
            "recipient_number", "recipient_name", "provider", "note", "kind", "category", "id",
        )).casefold()
        if query and query not in text:
            continue
        result.append(item)
    return sorted(result, key=lambda item: (local_datetime(item.due_at), item.id))


def schedule_totals(schedules):
    schedules = list(schedules)
    active = [item for item in schedules if item.status == "SCHEDULED"]
    return {
        "schedule_count": len(schedules),
        "scheduled_count": len(active),
        "scheduled_total": sum((Decimal(item.amount) for item in active), Decimal("0.00")),
        "auto_pay_count": sum(bool(item.auto_pay) for item in active),
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
