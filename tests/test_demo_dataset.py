"""Verify independent ledger anchors, complete resets and backup boundaries."""

from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from app import create_app
from app.domain.demo import DemoDataset, WalletOpeningBalance
from app.domain.models import Transaction, User
from app.domain.payment_plans import PayLaterAccount, PayLaterPurchase, PaymentInvoice
from app.domain.operations import ScheduledPayment
from app.extensions import db
from app.services.demo_seed import DEMO_MAIN_MOBILE, seed_demo_operations, seed_reconciled_demo_dataset
from app.services.reporting_service import local_datetime, wallet_change
from config import DevelopmentConfig
from scripts.reset_demo_data import ROOT, main, reset_demo_database, validated_database_path


@contextmanager
def reset_fixture_directory():
    """Normal workspace directory avoids Windows tempfile ACL inheritance issues."""
    instance = (ROOT / "instance").resolve()
    target = instance / f"reset-test-{uuid4().hex}"
    target.mkdir(parents=True)
    try:
        yield target
    finally:
        resolved = target.resolve()
        if resolved != instance and resolved.is_relative_to(instance):
            shutil.rmtree(resolved)


class EmptySeedConfig(DevelopmentConfig):
    TESTING = True
    DEBUG = False
    SEED_DEMO_DATA = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    ASSISTANT_API_ENABLED = False
    SCHEDULE_AUTO_RUN_ON_REQUEST = False


class DemoDatasetTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(EmptySeedConfig)
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def seed(self):
        return seed_reconciled_demo_dataset(as_of=date(2026, 10, 2), generated_at=datetime(2026, 10, 2, 12, tzinfo=timezone.utc))

    def test_seed_is_labelled_and_covers_exactly_120_bangladesh_calendar_days(self):
        result = self.seed()
        dataset = DemoDataset.query.one()
        self.assertTrue(dataset.synthetic)
        self.assertEqual((dataset.starts_on, dataset.ends_on), (date(2026, 6, 5), date(2026, 10, 2)))
        self.assertEqual(result["transactions"], Transaction.query.count())
        # Research participation is never fabricated by demo seeding. Every
        # original demo table remains populated; consented pilot tables start empty.
        pilot_tables = {"pilot_participants", "pilot_events", "pilot_feedback"}
        self.assertTrue(all(result["table_counts"][table] == 0 for table in pilot_tables))
        self.assertTrue(all(value > 0 for table, value in result["table_counts"].items()
                            if table not in pilot_tables))
        main_user = User.query.filter_by(mobile=DEMO_MAIN_MOBILE).one()
        rows = main_user.transactions.all()
        days = {local_datetime(row.created_at).date() for row in rows}
        self.assertEqual(days, {dataset.starts_on + timedelta(days=index) for index in range(120)})
        self.assertTrue({"ADD_MONEY", "SEND_MONEY", "RECEIVE_MONEY", "CASH_OUT", "MOBILE_RECHARGE", "BILL_PAYMENT"}.issubset({row.kind for row in rows}))
        self.assertTrue(all("Synthetic demo" in row.note for row in rows))
        self.assertTrue(all(row.reference.startswith("DEMO120-20261002-") for row in rows))

    def test_wallets_reconcile_independent_opening_anchors_without_negative_intermediate_balances(self):
        self.seed()
        for user in User.query.all():
            anchor = db.session.get(WalletOpeningBalance, user.id)
            balance = Decimal(anchor.opening_balance)
            rows = user.transactions.order_by(Transaction.created_at, Transaction.id).all()
            self.assertTrue(all(row.created_at >= anchor.recorded_at for row in rows))
            for row in rows:
                balance += wallet_change(row)
                self.assertGreaterEqual(balance, 0)
            self.assertEqual(balance, user.balance)
        primary = User.query.filter_by(mobile=DEMO_MAIN_MOBILE).one()
        primary.balance += Decimal("1.00")
        db.session.commit()
        anchor = db.session.get(WalletOpeningBalance, primary.id)
        expected = anchor.opening_balance + sum((wallet_change(row) for row in primary.transactions.all()), Decimal("0.00"))
        self.assertNotEqual(expected, primary.balance, "Anchor must be independent of the current balance.")

    def test_transfers_have_two_equal_opposite_entries_and_cashouts_use_fee(self):
        self.seed()
        grouped = defaultdict(list)
        for row in Transaction.query.filter(Transaction.kind.in_(("SEND_MONEY", "RECEIVE_MONEY"))).all():
            grouped[row.reference].append(row)
        for rows in grouped.values():
            self.assertEqual(2, len(rows))
            self.assertEqual({"IN", "OUT"}, {row.direction for row in rows})
            self.assertEqual(rows[0].amount, rows[1].amount)
            self.assertNotEqual(rows[0].user_id, rows[1].user_id)
            self.assertEqual(Decimal("0.00"), sum((wallet_change(row) for row in rows), Decimal("0.00")))
        for row in Transaction.query.filter_by(kind="CASH_OUT").all():
            self.assertEqual((row.amount * Decimal("0.015")).quantize(Decimal("0.01")), row.fee)

    def test_invoices_credit_plans_and_future_schedules_have_consistent_relationships(self):
        self.seed()
        for invoice in PaymentInvoice.query.all():
            transaction = db.session.get(Transaction, invoice.transaction_id)
            self.assertEqual(transaction.user_id, invoice.user_id)
            self.assertEqual("BILL_PAYMENT", transaction.kind)
            self.assertIn(invoice.invoice_number, transaction.note)
        pending = PayLaterPurchase.query.filter_by(status="PENDING").all()
        self.assertEqual(sum((purchase.amount for purchase in pending), Decimal("0.00")), PayLaterAccount.query.one().outstanding)
        for purchase in PayLaterPurchase.query.all():
            self.assertEqual(Decimal("0.00"), wallet_change(db.session.get(Transaction, purchase.purchase_transaction_id)))
            if purchase.status == "REPAID":
                self.assertEqual(-purchase.amount, wallet_change(db.session.get(Transaction, purchase.repayment_transaction_id)))
        self.assertTrue(all(local_datetime(row.due_at).date() > date(2026, 10, 2) and row.transaction_id is None for row in ScheduledPayment.query.all()))

    def test_seed_refuses_nonempty_database_and_startup_never_rolls_a_new_window(self):
        self.seed()
        user = User.query.filter_by(mobile=DEMO_MAIN_MOBILE).one()
        old_count, old_balance = Transaction.query.count(), user.balance
        with self.assertRaisesRegex(ValueError, "empty database"):
            seed_reconciled_demo_dataset(as_of=date(2026, 10, 3))
        seed_demo_operations(user, now=datetime(2026, 11, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(old_count, Transaction.query.count())
        self.assertEqual(old_balance, user.balance)
        self.assertEqual(5, ScheduledPayment.query.count())

    def test_first_login_health_has_explainable_reviews_and_near_term_commitments(self):
        from app.services.financial_health_service import health_for_user

        self.seed()
        user = User.query.filter_by(mobile=DEMO_MAIN_MOBILE).one()
        report = health_for_user(user.id, now=datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
        self.assertEqual({"repeated", "unusual"}, {item["kind"] for item in report["signals"]})
        self.assertEqual(Decimal("1460.00"), report["reserved"])
        self.assertEqual(Decimal("620.00"), report["scheduled_reserve"])
        self.assertEqual(Decimal("840.00"), report["pay_later_reserve"])
        self.assertTrue(report["reconciliation"]["matched"])


class DemoResetTests(unittest.TestCase):
    def test_reset_requires_explicit_confirmation_and_rejects_outside_or_backup_targets(self):
        with self.assertRaises(SystemExit) as error:
            main([])
        self.assertEqual(2, error.exception.code)
        for target in (ROOT / "danger.db", ROOT / "instance" / "backups" / "restore.db", ROOT / "instance" / "nested" / "BACKUPS" / "restore.db", ROOT / "instance" / "data.txt"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validated_database_path(target)

    def test_reset_preserves_online_backup_and_replaces_even_unknown_old_table_records(self):
        with reset_fixture_directory() as temporary:
            target = Path(temporary) / "fixture.db"
            with closing(sqlite3.connect(target)) as connection, connection:
                connection.execute("CREATE TABLE old_hackathon_data (id INTEGER PRIMARY KEY, note TEXT)")
                connection.execute("INSERT INTO old_hackathon_data VALUES (1, 'previous private fixture')")
            result = reset_demo_database(target, as_of=date(2026, 10, 2))
            backup = Path(result["backup"])
            self.assertTrue(backup.is_relative_to(ROOT / "instance" / "backups"))
            try:
                with closing(sqlite3.connect(backup)) as connection:
                    self.assertEqual("previous private fixture", connection.execute("SELECT note FROM old_hackathon_data").fetchone()[0])
                with closing(sqlite3.connect(target)) as connection:
                    self.assertEqual(0, connection.execute("SELECT count(*) FROM old_hackathon_data").fetchone()[0])
                    self.assertEqual(4, connection.execute("SELECT count(*) FROM users").fetchone()[0])
                    self.assertEqual(result["transactions"], connection.execute("SELECT count(*) FROM transactions").fetchone()[0])
                    self.assertEqual("ok", connection.execute("PRAGMA integrity_check").fetchone()[0])
            finally:
                backup.unlink()

    def test_failed_generation_rolls_back_all_prior_record_deletions(self):
        with reset_fixture_directory() as temporary:
            target = Path(temporary) / "fixture.db"
            with closing(sqlite3.connect(target)) as connection, connection:
                connection.execute("CREATE TABLE old_fixture (note TEXT)")
                connection.execute("INSERT INTO old_fixture VALUES ('preserve me on failure')")
            backups_before = set((ROOT / "instance" / "backups").glob("fixture-before-demo-reset-*.db"))
            try:
                with patch("scripts.reset_demo_data.seed_reconciled_demo_dataset", side_effect=ValueError("forced seed failure")):
                    with self.assertRaisesRegex(ValueError, "forced seed failure"):
                        reset_demo_database(target, as_of=date(2026, 10, 2))
                with closing(sqlite3.connect(target)) as connection:
                    self.assertEqual("preserve me on failure", connection.execute("SELECT note FROM old_fixture").fetchone()[0])
            finally:
                for backup in set((ROOT / "instance" / "backups").glob("fixture-before-demo-reset-*.db")) - backups_before:
                    backup.unlink()


if __name__ == "__main__":
    unittest.main()
