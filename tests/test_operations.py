from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.domain.models import Transaction, User
from app.domain.operations import RecipientRegistration, ScheduledPayment
from app.extensions import db
from app.services.demo_seed import DEMO_BLOCKED_MOBILE, DEMO_RECIPIENT_MOBILE, seed_demo_operations
from app.services.exceptions import ValidationError
from app.services.reporting_service import local_datetime
from app.services.schedule_service import (
    cancel_schedule, create_schedule, execute_schedule, run_due_payments, scheduling_window,
)
from tests.helpers import AppTestCase


class OperationsTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = False
        ScheduledPayment.query.delete()
        db.session.commit()
        self.login()

    def schedule(self, **changes):
        first_date, _ = scheduling_window()
        values = {"kind": "SEND_MONEY", "recipient_number": DEMO_RECIPIENT_MOBILE, "amount": "100.00", "frequency": "ONE_TIME", "auto_pay": "1", "due_date": first_date.isoformat()}
        values.update(changes)
        return create_schedule(self.user_id, values)

    def test_lookup_is_authenticated_and_returns_registered_unknown_and_blocked_states(self):
        found = self.client.get("/operations/recipient", query_string={"kind": "SEND_MONEY", "number": DEMO_RECIPIENT_MOBILE}).get_json()
        self.assertEqual((found["status"], found["name"], found["can_transact"]), ("registered", "Demo Recipient Ayesha", True))
        unknown = self.client.get("/operations/recipient", query_string={"kind": "SEND_MONEY", "number": "01712345678"}).get_json()
        self.assertEqual((unknown["status"], unknown["can_transact"]), ("not_registered", False))
        blocked = self.client.get("/operations/recipient", query_string={"kind": "MOBILE_RECHARGE", "number": DEMO_BLOCKED_MOBILE, "provider": "Robi"}).get_json()
        self.assertEqual((blocked["status"], blocked["can_transact"]), ("blocked", False))
        provider = self.client.get("/operations/recipient", query_string={"kind": "BILL_PAYMENT", "number": "DEMO-METER-1001", "provider": "DESCO Electricity", "category": "electricity"}).get_json()
        self.assertEqual((provider["status"], provider["authorization_name"]), ("registered", "DESCO Electricity"))
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/operations/recipient?kind=SEND_MONEY&number=" + DEMO_RECIPIENT_MOBILE).status_code, 302)

    def test_blocked_recipient_rejected_server_side_for_all_payment_routes(self):
        blocked_wallet = User(full_name="Blocked Demo Wallet", mobile=DEMO_BLOCKED_MOBILE, balance=Decimal("0.00"))
        db.session.add(blocked_wallet)
        db.session.commit()
        cases = (
            ("/wallet/send-money", {"recipient_mobile": DEMO_BLOCKED_MOBILE, "amount": "10"}),
            ("/wallet/cash-out", {"agent_number": DEMO_BLOCKED_MOBILE, "amount": "10"}),
            ("/payments/recharge", {"operator": "Robi", "mobile": DEMO_BLOCKED_MOBILE, "amount": "10"}),
            ("/payments/pay-bill", {"category": "gas", "provider": "Titas Gas", "account_no": DEMO_BLOCKED_MOBILE, "amount": "10"}),
        )
        for path, values in cases:
            with self.subTest(path=path):
                response = self.client.post(path, data=values)
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Blocked number", response.data)
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(Transaction.query.count(), 0)

    def test_save_does_not_debit_and_early_payment_cannot_execute(self):
        payment = self.schedule()[0]
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(Transaction.query.count(), 0)
        with self.assertRaises(ValidationError):
            execute_schedule(self.user_id, payment.id)
        self.assertEqual(payment.status, "SCHEDULED")
        self.assertEqual(run_due_payments(user_id=self.user_id), [])

    def test_due_transfer_is_atomic_and_idempotent(self):
        recipient = User.query.filter_by(mobile=DEMO_RECIPIENT_MOBILE).one()
        opening = recipient.balance
        payment = self.schedule()[0]
        due = payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1)
        executed = execute_schedule(self.user_id, payment.id, now=due)
        self.assertEqual(executed.status, "COMPLETED")
        self.assertEqual(self.user.balance, Decimal("900.00"))
        self.assertEqual(recipient.balance, opening + Decimal("100.00"))
        self.assertEqual(Transaction.query.count(), 2)
        execute_schedule(self.user_id, payment.id, now=due)
        self.assertEqual(Transaction.query.count(), 2)
        self.assertEqual(run_due_payments(now=due), [])
        self.assertEqual(Transaction.query.filter_by(user_id=self.user_id).one().id, executed.transaction_id)

    def test_due_payment_failure_preserves_balance_and_records_reason(self):
        payment = self.schedule(amount="1001.00")[0]
        executed = execute_schedule(self.user_id, payment.id, now=payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1))
        self.assertEqual(executed.status, "FAILED")
        self.assertIn("Insufficient balance", executed.last_error)
        self.assertIsNone(executed.transaction_id)
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(Transaction.query.count(), 0)

    def test_recipient_newly_blocked_after_planning_is_rechecked_at_execution(self):
        payment = self.schedule()[0]
        db.session.add(RecipientRegistration(number=DEMO_RECIPIENT_MOBILE, name="Flagged", status="BLOCKED", kind="ANY", provider=""))
        db.session.commit()
        executed = execute_schedule(self.user_id, payment.id, now=payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1))
        self.assertEqual(executed.status, "FAILED")
        self.assertIn("Blocked number", executed.last_error)
        self.assertEqual(Transaction.query.count(), 0)

    def test_monthly_dates_keep_original_day_and_stop_at_horizon(self):
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        values = {"kind": "SEND_MONEY", "recipient_number": DEMO_RECIPIENT_MOBILE, "amount": "100", "frequency": "MONTHLY", "auto_pay": "1", "due_date": "2026-01-31"}
        payments = create_schedule(self.user_id, values, now=now)
        self.assertEqual([local_datetime(row.due_at).date().isoformat() for row in payments], ["2026-01-31", "2026-02-28", "2026-03-31"])
        self.assertEqual(len({row.recurrence_group for row in payments}), 1)
        values["due_date"] = "2026-04-01"
        with self.assertRaises(ValidationError):
            create_schedule(self.user_id, values, now=now)

    def test_other_users_cannot_cancel_or_execute_and_manual_plan_not_auto_executed(self):
        payment = self.schedule(auto_pay="0")[0]
        other = User.query.filter_by(mobile=DEMO_RECIPIENT_MOBILE).one()
        with self.assertRaises(ValidationError):
            cancel_schedule(other.id, payment.id)
        with self.assertRaises(ValidationError):
            execute_schedule(other.id, payment.id)
        due = payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1)
        self.assertEqual(run_due_payments(now=due), [])
        cancel_schedule(self.user_id, payment.id)
        self.assertEqual(payment.status, "CANCELLED")
        self.assertEqual(Transaction.query.count(), 0)

    def test_due_runner_skips_payment_cancelled_after_its_initial_query(self):
        payment = self.schedule()[0]
        due = payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1)

        def cancellation_race(owner, payment_id, **kwargs):
            cancel_schedule(owner, payment_id)
            raise ValidationError("Only pending scheduled payments can be paid.")

        with patch("app.services.schedule_service.execute_schedule", side_effect=cancellation_race):
            self.assertEqual(run_due_payments(user_id=self.user_id, now=due), [])
        self.assertEqual(payment.status, "CANCELLED")
        self.assertEqual(Transaction.query.count(), 0)

    def test_demo_seed_is_persisted_idempotent_and_covers_120_calendar_days(self):
        now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        seed_demo_operations(self.user, now=now)
        seed_demo_operations(self.user, now=now)
        rows = Transaction.query.filter_by(user_id=self.user_id).all()
        dates = {local_datetime(row.created_at).date() for row in rows}
        self.assertEqual(len(rows), 120)
        self.assertEqual(len(dates), 120)
        self.assertEqual((max(dates) - min(dates)).days, 119)
        self.assertEqual({row.kind for row in rows}, {"ADD_MONEY", "SEND_MONEY", "RECEIVE_MONEY", "CASH_OUT", "MOBILE_RECHARGE", "BILL_PAYMENT"})
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(ScheduledPayment.query.filter_by(user_id=self.user_id).count(), 4)
        self.assertTrue(all(local_datetime(row.due_at).month in {11, 12} for row in ScheduledPayment.query.filter_by(user_id=self.user_id).all()))

    def test_schedule_page_and_cli_show_future_plans_without_debiting(self):
        self.schedule()
        response = self.client.get("/schedules")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Print / Download", response.data)
        result = self.app.test_cli_runner().invoke(args=["run-due-payments"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Processed 0 due payments", result.output)
        self.assertEqual(Transaction.query.count(), 0)
