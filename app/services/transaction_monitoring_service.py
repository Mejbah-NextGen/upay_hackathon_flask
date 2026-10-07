"""Explainable review-only outbound monitoring committed with the ledger."""

from datetime import timedelta
from decimal import Decimal
import json
import time

import click
from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.domain.models import Transaction
from app.domain.monitoring import TransactionReviewFlag
from app.extensions import db


def monitor_transaction(transaction):
    """Add deduplicated review signals without committing or blocking payment.

    A large transfer or a burst is a reason for operator review, not evidence of
    fraud. Only this user's successful outbound ledger records are counted.
    Flushes to obtain ledger ID/time; callers must snapshot pending transactions
    before calling this function if iterating db.session.new.
    """
    if transaction.direction != "OUT":
        return []
    db.session.flush()
    if transaction.status != "SUCCESS":
        return []
    rules = []
    large = Decimal(str(current_app.config.get("MONITOR_LARGE_AMOUNT_BDT", "50000")))
    count = int(current_app.config.get("MONITOR_BURST_COUNT", 5))
    seconds = int(current_app.config.get("MONITOR_BURST_SECONDS", 60))
    if large > 0 and Decimal(transaction.amount) >= large:
        rules.append("LARGE_OUTBOUND")
    if count > 0 and seconds > 0:
        cutoff = transaction.created_at - timedelta(seconds=seconds)
        observed = db.session.execute(select(func.count(Transaction.id)).where(
            Transaction.user_id == transaction.user_id,
            Transaction.direction == "OUT", Transaction.status == "SUCCESS",
            Transaction.created_at >= cutoff, Transaction.created_at <= transaction.created_at,
            Transaction.id <= transaction.id,
        )).scalar_one()
        if observed >= count:
            rules.append("OUTBOUND_BURST")
    if rules:
        table = TransactionReviewFlag.__table__
        dialect = db.engine.dialect.name
        insert = postgres_insert if dialect == "postgresql" else sqlite_insert
        for rule in rules:
            statement = insert(table).values(transaction_id=transaction.id, rule=rule,
                status="OPEN", created_at=int(time.time())).on_conflict_do_nothing(
                    index_elements=[table.c.transaction_id, table.c.rule])
            db.session.execute(statement)
    return rules


def register_monitoring_cli(app):
    @app.cli.command("monitor-report")
    def monitor_report():
        """Print review counts without account identifiers or transaction contents."""
        rows = db.session.execute(select(TransactionReviewFlag.rule, TransactionReviewFlag.status,
            func.count(TransactionReviewFlag.id)).group_by(
                TransactionReviewFlag.rule, TransactionReviewFlag.status).order_by(
                    TransactionReviewFlag.rule, TransactionReviewFlag.status)).all()
        click.echo(json.dumps({"review_only": True, "signals": [
            {"rule": rule, "status": status, "count": count} for rule, status, count in rows]}, sort_keys=True))
