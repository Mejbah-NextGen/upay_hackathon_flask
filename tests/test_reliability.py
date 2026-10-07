"""Real concurrent sessions against a file-backed SQLite database.

Barriers stop workers immediately before their competing SQL writes, after both
have read the same initial state. These are database races, not mocked outcomes.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event, get_ident
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event

from app import create_app
from app.container import get_container
from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.domain.payment_plans import PaymentInvoice, PaymentSubmission
from app.domain.pilot import PilotEvent
from app.domain.wallet_submissions import WalletSubmission
from app.extensions import db
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.schedule_service import cancel_schedule, execute_schedule, run_due_payments
from app.services.pilot_service import enrol_participant
from app.services.wallet_service import WalletService
from tests.helpers import TestConfig


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / "instance"
        self.database = temporary_root / f"upay-reliability-{uuid4().hex}.sqlite"
        database = self.database

        class FileConfig(TestConfig):
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + database.as_posix()
            SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 10, "check_same_thread": False}}
            SEED_DEMO_DATA = False
            SCHEDULE_AUTO_RUN_ON_REQUEST = False

        self.app = create_app(FileConfig)
        self.now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
        with self.app.app_context():
            sender = User(full_name="Reliability Sender", mobile="01711223344", balance=Decimal("1000.00"))
            recipient = User(full_name="Reliability Recipient", mobile="01811223344", balance=Decimal("0.00"))
            db.session.add_all([sender, recipient])
            db.session.commit()
            self.user_id, self.recipient_id = sender.id, recipient.id
            self.recipient_mobile = recipient.mobile
            for user_id in (self.user_id, self.recipient_id):
                enrol_participant(user_id, consent=True, data_source="DEMO", now=datetime(2000, 1, 1, tzinfo=timezone.utc))
            db.session.commit()
            self.engine = db.engine

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.database.unlink(missing_ok=True)

    def schedule(self, *, kind="SEND_MONEY", amount="125.00"):
        with self.app.app_context():
            row = ScheduledPayment(
                user_id=self.user_id, kind=kind, recipient_number=self.recipient_mobile,
                recipient_name="Reliability Recipient", amount=Decimal(amount),
                provider="Robi" if kind == "MOBILE_RECHARGE" else "Titas Gas" if kind == "BILL_PAYMENT" else "",
                category="gas" if kind == "BILL_PAYMENT" else "", frequency="ONE_TIME", auto_pay=True,
                due_at=self.now - timedelta(seconds=1), status="SCHEDULED", recurrence_group="reliability",
            )
            db.session.add(row)
            db.session.commit()
            return row.id

    def state(self, schedule_id=None):
        with self.app.app_context():
            row = db.session.get(ScheduledPayment, schedule_id) if schedule_id else None
            return {
                "balance": db.session.get(User, self.user_id).balance,
                "recipient_balance": db.session.get(User, self.recipient_id).balance,
                "transactions": Transaction.query.count(),
                "outgoing": Transaction.query.filter_by(user_id=self.user_id, direction="OUT").count(),
                "invoices": PaymentInvoice.query.count(), "submissions": PaymentSubmission.query.count(),
                "wallet_submissions": WalletSubmission.query.count(),
                "transaction_events": PilotEvent.query.filter_by(kind="TRANSACTION").count(),
                "completed_events": PilotEvent.query.filter_by(kind="AUTO_PAY_COMPLETED").count(),
                "failed_events": PilotEvent.query.filter_by(kind="AUTO_PAY_FAILED").count(),
                "schedule_failed_events": PilotEvent.query.filter_by(kind="AUTO_PAY_FAILED", resource_id=schedule_id).count() if schedule_id else 0,
                "status": row.status if row else None,
                "transaction_id": row.transaction_id if row else None,
                "executed_at": row.executed_at if row else None,
            }

    def worker(self, action):
        with self.app.app_context():
            session_id = id(db.session())
            connection_id = id(db.session.connection().connection.driver_connection)
            try:
                return action(), session_id, connection_id
            finally:
                db.session.remove()

    @contextmanager
    def simultaneous_writes(self, prefix):
        barrier = Barrier(2, timeout=10)
        seen = set()

        def before_write(connection, cursor, statement, parameters, context, executemany):
            identity = get_ident()
            if statement.upper().startswith(prefix.upper()) and identity not in seen:
                seen.add(identity)
                barrier.wait()

        event.listen(self.engine, "before_cursor_execute", before_write)
        try:
            yield
        finally:
            event.remove(self.engine, "before_cursor_execute", before_write)

    def parallel(self, actions):
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(self.worker, action) for action in actions]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertEqual(2, len({outcome[1] for outcome in outcomes}), "Workers must use separate ORM sessions")
        self.assertEqual(2, len({outcome[2] for outcome in outcomes}), "Workers must use separate database connections")
        return [outcome[0] for outcome in outcomes]

    def test_two_due_runners_execute_each_payment_kind_once(self):
        for kind in ("SEND_MONEY", "MOBILE_RECHARGE", "BILL_PAYMENT"):
            with self.subTest(kind=kind):
                schedule_id = self.schedule(kind=kind)

                def run():
                    return len(run_due_payments(user_id=self.user_id, now=self.now))

                with self.simultaneous_writes("UPDATE scheduled_payments SET status"):
                    outcomes = self.parallel([run, run])
                self.assertEqual([0, 1], sorted(outcomes))
                state = self.state(schedule_id)
                self.assertEqual("COMPLETED", state["status"])
                self.assertIsNotNone(state["transaction_id"])
                self.assertIsNotNone(state["executed_at"])
                with self.app.app_context():
                    self.assertFalse(execute_schedule(self.user_id, schedule_id, now=self.now).processed_now)
        state = self.state()
        self.assertEqual(Decimal("625.00"), state["balance"])
        self.assertEqual(Decimal("125.00"), state["recipient_balance"])
        self.assertEqual(3, state["outgoing"])
        self.assertEqual(4, state["transactions"])
        self.assertEqual(1, state["invoices"])
        self.assertEqual(3, state["transaction_events"])
        self.assertEqual(3, state["completed_events"])

    def test_competing_wallet_debits_cannot_overdraw_or_create_partial_ledger(self):
        def transfer():
            try:
                get_container().wallet.send_money(self.user_id, self.recipient_mobile, "750")
                return "paid"
            except InsufficientBalanceError:
                return "insufficient"

        with self.simultaneous_writes("UPDATE users SET balance"):
            self.assertEqual(["insufficient", "paid"], sorted(self.parallel([transfer, transfer])))
        state = self.state()
        self.assertEqual(Decimal("250.00"), state["balance"])
        self.assertEqual(Decimal("750.00"), state["recipient_balance"])
        self.assertEqual(2, state["transactions"])
        self.assertEqual(1, state["transaction_events"])
        with self.app.app_context():
            entries = Transaction.query.all()
            self.assertEqual(1, len({entry.reference for entry in entries}))
            self.assertEqual({"IN", "OUT"}, {entry.direction for entry in entries})

    def test_concurrent_wallet_http_submissions_return_one_receipt_and_transfer_once(self):
        def post():
            client = self.app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
            response = client.post("/wallet/send-money", data={
                "recipient_mobile": self.recipient_mobile, "amount": "125", "note": "Concurrent HTTP demo",
                "operation_token": "c" * 32,
            })
            return response.status_code, response.location

        with self.simultaneous_writes("INSERT INTO wallet_submissions"):
            first, second = self.parallel([post, post])
        self.assertEqual(302, first[0])
        self.assertEqual(first, second)
        state = self.state()
        self.assertEqual(Decimal("875.00"), state["balance"])
        self.assertEqual(Decimal("125.00"), state["recipient_balance"])
        self.assertEqual(2, state["transactions"])
        self.assertEqual(1, state["wallet_submissions"])
        self.assertEqual(1, state["transaction_events"])

    def test_cancellation_committed_before_runner_claim_prevents_debit(self):
        schedule_id = self.schedule()
        claim_reached, release_claim = Event(), Event()

        def hold_claim(connection, cursor, statement, parameters, context, executemany):
            if statement.upper().startswith("UPDATE SCHEDULED_PAYMENTS SET STATUS") and "PROCESSING" in parameters:
                claim_reached.set()
                if not release_claim.wait(10):
                    raise TimeoutError("Runner claim was not released")

        event.listen(self.engine, "before_cursor_execute", hold_claim)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                runner = workers.submit(self.worker, lambda: len(run_due_payments(user_id=self.user_id, now=self.now)))
                self.assertTrue(claim_reached.wait(5))
                cancel = workers.submit(self.worker, lambda: cancel_schedule(self.user_id, schedule_id).status)
                self.assertEqual("CANCELLED", cancel.result(timeout=5)[0])
                release_claim.set()
                self.assertEqual(0, runner.result(timeout=5)[0])
        finally:
            release_claim.set()
            event.remove(self.engine, "before_cursor_execute", hold_claim)
        state = self.state(schedule_id)
        self.assertEqual("CANCELLED", state["status"])
        self.assertEqual(Decimal("1000.00"), state["balance"])
        self.assertEqual(0, state["transactions"])
        self.assertEqual((0, 0, 0), (state["transaction_events"], state["completed_events"], state["failed_events"]))

    def test_runner_claim_before_cancellation_completes_once_and_cancel_is_rejected(self):
        schedule_id = self.schedule()
        debit_reached, release_debit, cancel_reached = Event(), Event(), Event()
        original_debit = WalletService._debit

        def hold_debit(*args, **kwargs):
            debit_reached.set()
            if not release_debit.wait(10):
                raise TimeoutError("Wallet debit was not released")
            return original_debit(*args, **kwargs)

        def see_cancel(connection, cursor, statement, parameters, context, executemany):
            if statement.upper().startswith("UPDATE SCHEDULED_PAYMENTS SET STATUS") and "CANCELLED" in parameters:
                cancel_reached.set()

        def cancel():
            try:
                cancel_schedule(self.user_id, schedule_id)
                return "cancelled"
            except ValidationError:
                return "already processed"

        event.listen(self.engine, "before_cursor_execute", see_cancel)
        try:
            with patch.object(WalletService, "_debit", side_effect=hold_debit):
                with ThreadPoolExecutor(max_workers=2) as workers:
                    runner = workers.submit(self.worker, lambda: len(run_due_payments(user_id=self.user_id, now=self.now)))
                    self.assertTrue(debit_reached.wait(5))
                    cancellation = workers.submit(self.worker, cancel)
                    self.assertTrue(cancel_reached.wait(5))
                    release_debit.set()
                    self.assertEqual(1, runner.result(timeout=5)[0])
                    self.assertEqual("already processed", cancellation.result(timeout=5)[0])
        finally:
            release_debit.set()
            event.remove(self.engine, "before_cursor_execute", see_cancel)
        state = self.state(schedule_id)
        self.assertEqual("COMPLETED", state["status"])
        self.assertEqual(Decimal("875.00"), state["balance"])
        self.assertEqual(2, state["transactions"])
        self.assertEqual(1, state["completed_events"])
        self.assertEqual(1, state["transaction_events"])

    def test_schedule_failure_after_debit_rolls_back_claim_balances_and_ledger_then_retries(self):
        schedule_id = self.schedule()
        original_finish = WalletService._finish

        def fail_after_flush(commit):
            original_finish(False)
            raise RuntimeError("injected ledger persistence failure")

        with self.app.app_context():
            with patch.object(WalletService, "_finish", side_effect=fail_after_flush):
                with self.assertRaisesRegex(RuntimeError, "injected ledger"):
                    execute_schedule(self.user_id, schedule_id, now=self.now)
        state = self.state(schedule_id)
        self.assertEqual("SCHEDULED", state["status"])
        self.assertIsNone(state["transaction_id"])
        self.assertIsNone(state["executed_at"])
        self.assertEqual(Decimal("1000.00"), state["balance"])
        self.assertEqual(Decimal("0.00"), state["recipient_balance"])
        self.assertEqual(0, state["transactions"])
        self.assertEqual((0, 0, 0), (state["transaction_events"], state["completed_events"], state["failed_events"]))
        with self.app.app_context():
            result = execute_schedule(self.user_id, schedule_id, now=self.now)
            self.assertEqual("COMPLETED", result.status)
            self.assertFalse(execute_schedule(self.user_id, schedule_id, now=self.now).processed_now)
        self.assertEqual(2, self.state(schedule_id)["transactions"])
        self.assertEqual(1, self.state(schedule_id)["completed_events"])
        self.assertEqual(1, self.state(schedule_id)["transaction_events"])

    def test_standalone_wallet_failure_rolls_back_before_caller_can_commit(self):
        original_finish = WalletService._finish

        def fail_after_flush(commit):
            original_finish(False)
            raise RuntimeError("injected commit failure")

        with self.app.app_context():
            wallet = get_container().wallet
            with patch.object(wallet, "_finish", side_effect=fail_after_flush):
                with self.assertRaisesRegex(RuntimeError, "injected commit"):
                    wallet.send_money(self.user_id, self.recipient_mobile, "125")
            # A service must not leave a debit behind if a caller catches an error
            # and subsequently commits other work in the same request/session.
            db.session.commit()
        state = self.state()
        self.assertEqual(Decimal("1000.00"), state["balance"])
        self.assertEqual(Decimal("0.00"), state["recipient_balance"])
        self.assertEqual(0, state["transactions"])
        self.assertEqual(0, state["transaction_events"])
        with self.app.app_context():
            get_container().wallet.send_money(self.user_id, self.recipient_mobile, "125")
        self.assertEqual(2, self.state()["transactions"])
        self.assertEqual(1, self.state()["transaction_events"])

    def test_each_schedule_kind_rolls_back_a_rejection_after_ledger_flush_and_commits_failed_once(self):
        for kind in ("SEND_MONEY", "MOBILE_RECHARGE", "BILL_PAYMENT"):
            with self.subTest(kind=kind):
                schedule_id = self.schedule(kind=kind)
                with self.app.app_context():
                    container = get_container()
                    service = container.wallet if kind == "SEND_MONEY" else container.payments
                    method = {"SEND_MONEY": "send_money", "MOBILE_RECHARGE": "mobile_recharge", "BILL_PAYMENT": "pay_bill"}[kind]
                    original = getattr(service, method)

                    def reject_after_payment(*args, **kwargs):
                        original(*args, **kwargs)
                        raise ValidationError("injected rejection after ledger flush")

                    with patch.object(service, method, side_effect=reject_after_payment):
                        result = execute_schedule(self.user_id, schedule_id, now=self.now)
                    self.assertEqual("FAILED", result.status)
                    self.assertIn("injected rejection", result.last_error)
                    self.assertEqual([], run_due_payments(user_id=self.user_id, now=self.now))
                state = self.state(schedule_id)
                self.assertEqual(Decimal("1000.00"), state["balance"])
                self.assertEqual(Decimal("0.00"), state["recipient_balance"])
                self.assertIsNone(state["transaction_id"])
                self.assertEqual((0, 0, 0), (state["transactions"], state["invoices"], state["submissions"]))
                self.assertEqual(0, state["transaction_events"])
                self.assertEqual(0, state["completed_events"])
                self.assertEqual(1, state["schedule_failed_events"])

    def bill(self, *, token="", invoice="", amount="125"):
        return get_container().payments.pay_bill(
            self.user_id, "Titas Gas", "CUSTOMER-4500", amount, "gas",
            submission_token=token, invoice_reference=invoice,
        ).id

    def test_concurrent_duplicate_bill_tokens_return_same_receipt_even_when_balance_funds_only_one(self):
        with self.app.app_context():
            db.session.get(User, self.user_id).balance = Decimal("125.00")
            db.session.commit()
        with self.simultaneous_writes("UPDATE users SET balance"):
            ids = self.parallel([lambda: self.bill(token="a" * 32), lambda: self.bill(token="a" * 32)])
        self.assertEqual(ids[0], ids[1])
        state = self.state()
        self.assertEqual(Decimal("0.00"), state["balance"])
        self.assertEqual(1, state["transactions"])
        self.assertEqual(1, state["invoices"])
        self.assertEqual(1, state["submissions"])
        self.assertEqual(1, state["transaction_events"])

    def test_concurrent_duplicate_invoice_reference_creates_one_payment(self):
        def pay():
            try:
                return ("paid", self.bill(invoice="BILL-1001"))
            except ValidationError as exc:
                return ("rejected", str(exc))

        with self.simultaneous_writes("UPDATE users SET balance"):
            outcomes = self.parallel([pay, pay])
        self.assertEqual(["paid", "rejected"], sorted(outcome[0] for outcome in outcomes))
        self.assertIn("already paid", next(outcome[1] for outcome in outcomes if outcome[0] == "rejected"))
        state = self.state()
        self.assertEqual(Decimal("875.00"), state["balance"])
        self.assertEqual(1, state["transactions"])
        self.assertEqual(1, state["invoices"])
        self.assertEqual(1, state["transaction_events"])

    def test_concurrent_insufficient_schedule_is_marked_failed_by_one_runner(self):
        schedule_id = self.schedule(amount="1001")
        first_marker, second_marker = Event(), Event()
        first_thread = []

        def hold_first_failure(connection, cursor, statement, parameters, context, executemany):
            if statement.upper().startswith("UPDATE SCHEDULED_PAYMENTS SET STATUS") and "FAILED" in parameters:
                if not first_thread:
                    first_thread.append(get_ident())
                    first_marker.set()
                    # The old full rollback released the claim before persisting
                    # FAILED. A second worker could then fail the same installment.
                    # Holding this marker makes that gap observable if it returns.
                    second_marker.wait(2)
                elif get_ident() != first_thread[0]:
                    second_marker.set()

        event.listen(self.engine, "before_cursor_execute", hold_first_failure)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                run = lambda: len(run_due_payments(user_id=self.user_id, now=self.now))
                first = workers.submit(self.worker, run)
                self.assertTrue(first_marker.wait(5))
                second = workers.submit(self.worker, run)
                counts = [first.result(timeout=8)[0], second.result(timeout=8)[0]]
        finally:
            event.remove(self.engine, "before_cursor_execute", hold_first_failure)
        self.assertEqual([0, 1], sorted(counts))
        state = self.state(schedule_id)
        self.assertEqual("FAILED", state["status"])
        self.assertEqual(Decimal("1000.00"), state["balance"])
        self.assertEqual(0, state["transactions"])
        self.assertEqual(1, state["failed_events"])
        self.assertEqual(0, state["transaction_events"])

    def test_bill_failure_after_debit_rolls_back_invoice_token_and_allows_same_token_retry(self):
        with self.app.app_context():
            original_finish = get_container().wallet._finish

            def fail_commit(commit):
                if commit:
                    original_finish(False)
                    raise RuntimeError("injected bill commit failure")
                return original_finish(commit)

            with patch.object(get_container().wallet, "_finish", side_effect=fail_commit):
                with self.assertRaisesRegex(RuntimeError, "injected bill"):
                    self.bill(token="b" * 32, invoice="BILL-RETRY")
            db.session.commit()
        state = self.state()
        self.assertEqual(Decimal("1000.00"), state["balance"])
        self.assertEqual((0, 0, 0), (state["transactions"], state["invoices"], state["submissions"]))
        self.assertEqual(0, state["transaction_events"])
        with self.app.app_context():
            first = self.bill(token="b" * 32, invoice="BILL-RETRY")
            self.assertEqual(first, self.bill(token="b" * 32, invoice="BILL-RETRY"))
        self.assertEqual(1, self.state()["transactions"])
        self.assertEqual(1, self.state()["transaction_events"])


if __name__ == "__main__":
    unittest.main()
