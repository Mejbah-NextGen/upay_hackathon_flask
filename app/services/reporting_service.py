"""Wallet history reporting using Bangladesh calendar days and UTC storage."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json

from app.services.service_catalog import BILL_CATEGORIES


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


def bill_category(transaction, invoice_categories=None):
    """Prefer invoice metadata, with a fallback for historical demo records."""
    if transaction.kind != "BILL_PAYMENT":
        return ""
    category = (invoice_categories or {}).get(getattr(transaction, "id", None), "")
    if category in BILL_CATEGORIES:
        return category
    title = str(transaction.title or "").casefold()
    for slug, details in BILL_CATEGORIES.items():
        if title.startswith(details["label"].casefold() + " "):
            return slug
    provider = str(transaction.counterparty or "").split("•", 1)[0].strip()
    # The dedicated education services share some providers with Education.
    for slug in sorted(BILL_CATEGORIES, key=lambda value: not value.startswith("education-")):
        if provider in BILL_CATEGORIES[slug]["providers"]:
            return slug
    return ""


def parse_chart_selection(raw):
    """Validate compact chart filters used by the segment export form."""
    if not raw:
        return None
    try:
        if len(raw) > 500:
            raise ValueError
        selection = json.loads(raw)
        if not isinstance(selection, dict):
            raise ValueError
        mode = selection.get("mode")
        if mode not in {"daily", "category", "amount", "cumulative"}:
            raise ValueError
        allowed = {
            "daily": {"mode", "start", "end", "direction"},
            "category": {"mode", "kind", "category"},
            "amount": {"mode", "lower", "upper"},
            "cumulative": {"mode", "end", "direction"},
        }[mode]
        if set(selection) - allowed:
            raise ValueError
        if mode in {"daily", "cumulative"}:
            end = date.fromisoformat(selection["end"])
            selection["end"] = end.isoformat()
            direction = selection.get("direction", "")
            if direction not in ({"IN", "OUT"} if mode == "daily" else {"IN", "OUT", ""}):
                raise ValueError
            if mode == "daily":
                start = date.fromisoformat(selection["start"])
                if start > end:
                    raise ValueError
                selection["start"] = start.isoformat()
        elif mode == "category":
            kind = selection["kind"]
            if not isinstance(kind, str) or not kind or len(kind) > 40:
                raise ValueError
            category = selection.get("category", "")
            if not isinstance(category, str) or category and (kind != "BILL_PAYMENT" or category not in BILL_CATEGORIES):
                raise ValueError
        elif mode == "amount":
            lower = Decimal(str(selection["lower"]))
            upper = None if selection.get("upper") is None else Decimal(str(selection["upper"]))
            if not lower.is_finite() or lower < 0 or upper is not None and (not upper.is_finite() or upper <= lower):
                raise ValueError
        return selection
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise ValueError("Choose a valid chart segment before exporting.") from None


def filter_chart_transactions(transactions, selection, invoice_categories=None):
    """Chart selections refine the existing user/filter scope; never expand it."""
    if not selection:
        return list(transactions)
    mode = selection["mode"]
    result = []
    for tx in transactions:
        if tx.status != "SUCCESS":
            continue
        day = local_datetime(tx.created_at).date().isoformat()
        if mode in {"daily", "cumulative"}:
            if day > selection["end"] or mode == "daily" and day < selection["start"]:
                continue
            if selection.get("direction") and tx.direction != selection["direction"]:
                continue
        elif mode == "category":
            if tx.direction != "OUT" or tx.kind != selection["kind"]:
                continue
            if selection.get("category") and bill_category(tx, invoice_categories) != selection["category"]:
                continue
            if not selection.get("category") and bill_category(tx, invoice_categories):
                continue
        elif mode == "amount":
            deduction = Decimal(tx.amount) + Decimal(tx.fee or 0)
            upper = selection.get("upper")
            if tx.direction != "OUT" or deduction < Decimal(str(selection["lower"])) or upper is not None and deduction >= Decimal(str(upper)):
                continue
        result.append(tx)
    return result


def chart_selection_description(selection):
    if not selection:
        return "Entire filtered report"
    mode = selection["mode"]
    direction = {"IN": "Money in", "OUT": "Money out", "": "Net activity"}.get(selection.get("direction", ""), "Activity")
    if mode == "daily":
        return f"{direction}, {selection['start']} to {selection['end']} (Bangladesh dates)"
    if mode == "cumulative":
        return f"{direction} through {selection['end']} (Bangladesh date)"
    if mode == "category":
        category = selection.get("category", "")
        return BILL_CATEGORIES[category]["label"] if category else selection["kind"].replace("_", " ").title()
    lower, upper = Decimal(str(selection["lower"])), selection.get("upper")
    return f"Money out from BDT {lower:,.2f}" + (f" to below BDT {Decimal(str(upper)):,.2f}" if upper is not None else " and above")


def report_visualization(transactions, invoice_categories=None):
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
            category = bill_category(tx, invoice_categories)
            key = (tx.kind, category)
            categories[key] = categories.get(key, zero) + deduction
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
        {"kind": kind, "category": category, "label": BILL_CATEGORIES[category]["label"] if category else kind.replace("_", " ").title(), "amount": float(amount)}
        for (kind, category), amount in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))
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
        "transactions": [{
            "id": getattr(tx, "id", None), "date": local_datetime(tx.created_at).date().isoformat(),
            "datetime": local_datetime(tx.created_at).strftime("%d %b %Y, %I:%M %p"),
            "kind": tx.kind, "category": bill_category(tx, invoice_categories), "direction": tx.direction,
            "title": tx.title, "counterparty": tx.counterparty or "Wallet", "reference": tx.reference or "",
            "amount": float(tx.amount), "fee": float(tx.fee or 0), "change": float(wallet_change(tx)),
        } for tx in completed],
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
