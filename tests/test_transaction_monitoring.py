import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.models import Transaction, User
from app.domain.monitoring import TransactionReviewFlag
from app.extensions import db
from app.services.transaction_monitoring_service import monitor_transaction, register_monitoring_cli
from tests.helpers import AppTestCase


class TransactionMonitoringTests(AppTestCase):
    def make_transaction(self, amount="10", direction="OUT", status="SUCCESS", user_id=None, age=0):
        tx = Transaction(user_id=user_id or self.user_id, direction=direction,
            status=status, kind="SEND_MONEY", title="Synthetic transfer",
            counterparty="PRIVATE-COUNTERPARTY", amount=Decimal(amount),
            reference="PRIVATE-REFERENCE", created_at=datetime.now(timezone.utc) - timedelta(seconds=age))
        db.session.add(tx)
        db.session.flush()
        return tx

    def test_large_outbound_review_is_deduplicated_and_does_not_block(self):
        original_balance = self.user.balance
        tx = self.make_transaction("50000")
        self.assertIn("LARGE_OUTBOUND", monitor_transaction(tx))
        monitor_transaction(tx)
        db.session.commit()
        flags = TransactionReviewFlag.query.all()
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].transaction_id, tx.id)
        self.assertEqual(flags[0].status, "OPEN")
        self.assertEqual(self.user.balance, original_balance)
        self.assertFalse(hasattr(flags[0], "counterparty"))
        self.assertFalse(hasattr(flags[0], "amount"))

    def test_inbound_failed_and_below_threshold_not_flagged(self):
        for tx in (self.make_transaction("50000", direction="IN"),
                   self.make_transaction("50000", status="FAILED"),
                   self.make_transaction("49999")):
            self.assertEqual(monitor_transaction(tx), [])
        db.session.commit()
        self.assertEqual(TransactionReviewFlag.query.count(), 0)

    def test_burst_counts_only_same_user_successful_outbound_in_window(self):
        peer = User(full_name="Other", mobile="01755555999", balance=0)
        db.session.add(peer)
        db.session.flush()
        for _ in range(6):
            self.make_transaction(user_id=peer.id)
            self.make_transaction(direction="IN")
            self.make_transaction(status="FAILED")
            self.make_transaction(age=120)
        for _ in range(4):
            tx = self.make_transaction()
            self.assertNotIn("OUTBOUND_BURST", monitor_transaction(tx))
        current = self.make_transaction()
        self.assertIn("OUTBOUND_BURST", monitor_transaction(current))
        db.session.commit()
        flags = TransactionReviewFlag.query.all()
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].transaction_id, current.id)

    def test_review_signals_rollback_with_ledger(self):
        tx = self.make_transaction("50000")
        monitor_transaction(tx)
        self.assertEqual(TransactionReviewFlag.query.count(), 1)
        db.session.rollback()
        self.assertEqual(TransactionReviewFlag.query.count(), 0)

    def test_custom_threshold_and_private_aggregate_report(self):
        self.app.config.update(MONITOR_LARGE_AMOUNT_BDT="100", MONITOR_BURST_COUNT=2,
            MONITOR_BURST_SECONDS=120)
        first = self.make_transaction("100")
        self.assertEqual(monitor_transaction(first), ["LARGE_OUTBOUND"])
        second = self.make_transaction("100")
        self.assertEqual(set(monitor_transaction(second)), {"LARGE_OUTBOUND", "OUTBOUND_BURST"})
        db.session.commit()
        if "monitor-report" not in self.app.cli.commands:
            register_monitoring_cli(self.app)
        result = self.app.test_cli_runner().invoke(args=["monitor-report"])
        self.assertEqual(result.exit_code, 0)
        report = json.loads(result.output)
        self.assertTrue(report["review_only"])
        self.assertEqual(sum(signal["count"] for signal in report["signals"]), 3)
        self.assertNotIn(self.user.mobile, result.output)
        self.assertNotIn("PRIVATE", result.output)
