"""Explainable, read-only wallet planning; never executes or blocks a payment."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.domain.payment_plans import PayLaterPurchase
from app.extensions import db
from app.services.reporting_service import local_datetime, wallet_change


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
PENDING_STATUSES = frozenset({"SCHEDULED", "FAILED", "PROCESSING"})
# These are the only kinds accepted by create_schedule. Their wallet/payment
# services debit the amount without a fee; cash-out/bank rails cannot be scheduled.
SCHEDULE_FEES = {"SEND_MONEY": ZERO, "MOBILE_RECHARGE": ZERO, "BILL_PAYMENT": ZERO}


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def outgoing_cost(tx):
    return money(tx.amount) + money(tx.fee)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def review_signals(transactions, *, now=None):
    """Review-only rules using prior same-kind debits and distinct receipt pairs."""
    now = now or datetime.now(timezone.utc)
    today = local_datetime(now).date()
    recent_start = today - timedelta(days=6)
    outgoing = sorted(
        (tx for tx in transactions if tx.status == "SUCCESS" and tx.direction == "OUT"),
        key=lambda tx: (_utc(tx.created_at), tx.id),
    )
    previous = defaultdict(list)
    signals = []
    for tx in outgoing:
        when = _utc(tx.created_at)
        recent = recent_start <= local_datetime(when).date() <= today
        history = [row for row in previous[tx.kind]
                   if when - timedelta(days=30) <= _utc(row.created_at) < when]
        if recent and len(history) >= 5:
            typical = money(median(outgoing_cost(row) for row in history))
            threshold = max(Decimal("1000.00"), typical * 3)
            if outgoing_cost(tx) > threshold:
                signals.append({"kind": "unusual", "transaction": tx, "baseline": typical,
                                "sample_count": len(history), "threshold": money(threshold)})
        # A missing recipient cannot establish that two payments had the same payee.
        recipient = str(tx.counterparty or "").strip().casefold()
        if recent and recipient:
            similar = [row for row in previous[tx.kind]
                       if timedelta(0) <= when - _utc(row.created_at) <= timedelta(minutes=10)
                       and str(row.counterparty or "").strip().casefold() == recipient
                       and money(row.amount) == money(tx.amount)
                       and money(row.fee) == money(tx.fee)]
            if similar:
                signals.append({"kind": "repeated", "transaction": tx,
                                "other_transaction": similar[-1]})
        previous[tx.kind].append(tx)
    return sorted(signals, key=lambda item: (_utc(item["transaction"].created_at),
                                             item["transaction"].id), reverse=True)


def reconcile_ledger(balance, transactions, anchor):
    """Compare with a persisted opening anchor, never with an inferred balance."""
    result = {"available": anchor is not None, "balance": money(balance)}
    if anchor is None:
        return result
    rows = [tx for tx in transactions if _utc(tx.created_at) >= _utc(anchor.recorded_at)]
    completed = [tx for tx in rows if tx.status == "SUCCESS"]
    incoming = sum((wallet_change(tx) for tx in completed if tx.direction == "IN"), ZERO)
    outgoing = -sum((wallet_change(tx) for tx in completed if tx.direction == "OUT"), ZERO)
    expected = money(anchor.opening_balance) + incoming - outgoing
    difference = money(balance) - expected
    return {**result, "opening_balance": money(anchor.opening_balance),
            "recorded_at": local_datetime(anchor.recorded_at), "source": anchor.source,
            "incoming": incoming, "outgoing": outgoing, "expected_balance": expected,
            "difference": difference, "matched": difference == ZERO,
            "successful_count": len(completed), "excluded_count": len(rows) - len(completed),
            "pre_anchor_count": len(transactions) - len(rows)}


def build_health_report(balance, transactions, schedules=(), purchases=(), *, anchor=None, now=None):
    """Reserve the next seven Bangladesh calendar days plus overdue commitments."""
    now = now or datetime.now(timezone.utc)
    today = local_datetime(now).date()
    horizon_end = today + timedelta(days=6)
    period_start = today - timedelta(days=29)
    transactions = list(transactions)
    successful_ids = {tx.id for tx in transactions if tx.status == "SUCCESS"}
    commitments = []
    unknown_fee_count = 0
    for item in schedules:
        due = local_datetime(item.due_at).date()
        if item.status not in PENDING_STATUSES or due > horizon_end or item.transaction_id in successful_ids:
            continue
        fee = SCHEDULE_FEES.get(item.kind)
        if fee is None:
            # Corrupt/unsupported legacy records are reserved at principal only,
            # and explicitly make the estimate incomplete in the UI.
            unknown_fee_count += 1
            fee = ZERO
        commitments.append({"type": "schedule", "item": item, "due": due,
                            "amount": money(item.amount), "fee": fee,
                            "total": money(item.amount) + fee, "overdue": due < today})
    for item in purchases:
        if item.status not in {"PENDING", "PROCESSING"} or item.due_on > horizon_end:
            continue
        if item.repayment_transaction_id in successful_ids:
            continue
        commitments.append({"type": "pay_later", "item": item, "due": item.due_on,
                            "amount": money(item.amount), "fee": ZERO,
                            "total": money(item.amount), "overdue": item.due_on < today})
    commitments.sort(key=lambda row: (row["due"], row["type"], row["item"].id))
    scheduled_reserve = sum((row["total"] for row in commitments if row["type"] == "schedule"), ZERO)
    pay_later_reserve = sum((row["total"] for row in commitments if row["type"] == "pay_later"), ZERO)
    reserved = scheduled_reserve + pay_later_reserve
    balance = money(balance)
    available = max(ZERO, balance - reserved)
    shortfall = max(ZERO, reserved - balance)
    observed = [tx for tx in transactions if tx.status == "SUCCESS"
                and period_start <= local_datetime(tx.created_at).date() <= today]
    incoming = sum((wallet_change(tx) for tx in observed if tx.direction == "IN"), ZERO)
    outgoing = -sum((wallet_change(tx) for tx in observed if tx.direction == "OUT"), ZERO)
    daily_outgoing = money(outgoing / 30)
    signals = review_signals(transactions, now=now)
    return {"today": today, "horizon_end": horizon_end, "period_start": period_start,
            "balance": balance, "reserved": reserved, "scheduled_reserve": scheduled_reserve,
            "pay_later_reserve": pay_later_reserve, "safe_to_spend": available, "shortfall": shortfall,
            "commitments": commitments, "overdue_count": sum(row["overdue"] for row in commitments),
            "unknown_fee_count": unknown_fee_count, "incoming": incoming, "outgoing": outgoing,
            "net_flow": incoming - outgoing, "daily_outgoing": daily_outgoing,
            "observed_count": len(observed), "signals": signals[:8], "signal_count": len(signals),
            "reconciliation": reconcile_ledger(balance, transactions, anchor)}


def health_for_user(user_id, *, now=None):
    """All financial queries are explicitly scoped to the authenticated user."""
    from app.container import get_container
    from app.domain.demo import WalletOpeningBalance

    user = get_container().wallet.get_user(user_id)
    return build_health_report(
        user.balance,
        Transaction.query.filter_by(user_id=user_id).all(),
        ScheduledPayment.query.filter_by(user_id=user_id).all(),
        PayLaterPurchase.query.filter_by(user_id=user_id).all(),
        anchor=db.session.get(WalletOpeningBalance, user_id), now=now,
    )
