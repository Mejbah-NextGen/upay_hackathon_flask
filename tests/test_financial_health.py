import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from flask import template_rendered

from app.domain.demo import WalletOpeningBalance
from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.domain.payment_plans import PayLaterPurchase
from app.extensions import db
from app.services.financial_health_service import build_health_report, reconcile_ledger, review_signals
from app.services.navigation_service import find_services, service_return_target
from tests.helpers import AppTestCase


NOW = datetime(2026, 10, 2, 7, tzinfo=timezone.utc)


def tx(identifier=1, *, when=NOW, amount="100.00", fee="0.00", status="SUCCESS", direction="OUT", kind="BILL_PAYMENT", recipient="Demo Utility"):
    return SimpleNamespace(id=identifier, created_at=when, amount=Decimal(amount), fee=Decimal(fee),
                           status=status, direction=direction, kind=kind, counterparty=recipient)


def schedule(identifier=1, *, days=0, status="SCHEDULED", kind="SEND_MONEY", amount="200.00", linked=None, auto_pay=True):
    return SimpleNamespace(id=identifier, due_at=NOW + timedelta(days=days), amount=Decimal(amount),
                           status=status, kind=kind, transaction_id=linked, auto_pay=auto_pay)


def purchase(identifier=1, *, days=0, status="PENDING", amount="100.00", linked=None):
    return SimpleNamespace(id=identifier, due_on=NOW.date() + timedelta(days=days), amount=Decimal(amount),
                           status=status, repayment_transaction_id=linked)


class FinancialHealthUnitTests(unittest.TestCase):
    def test_seven_calendar_day_reserve_includes_overdue_manual_failed_and_pay_later_once(self):
        ledger = [tx(30), tx(31)]
        schedules = [schedule(1, days=-2), schedule(2, days=6, auto_pay=False),
                     schedule(3, days=2, status="FAILED"), schedule(4, days=7),
                     schedule(5, status="CANCELLED"), schedule(6, status="COMPLETED"),
                     schedule(7, linked=30)]
        purchases = [purchase(1, days=-1), purchase(2, days=6), purchase(3, days=7),
                     purchase(4, status="REPAID"), purchase(5, linked=31)]
        result = build_health_report("1000.00", ledger, schedules, purchases, now=NOW)
        self.assertEqual(result["scheduled_reserve"], Decimal("600.00"))
        self.assertEqual(result["pay_later_reserve"], Decimal("200.00"))
        self.assertEqual(result["safe_to_spend"], Decimal("200.00"))
        self.assertEqual(result["shortfall"], Decimal("0.00"))
        self.assertEqual(result["overdue_count"], 2)
        self.assertEqual(len(result["commitments"]), 5)
        self.assertTrue(all(row["fee"] == 0 for row in result["commitments"]))

    def test_overdrawn_and_empty_wallets_never_report_negative_safe_to_spend(self):
        empty = build_health_report("0", [], now=NOW)
        self.assertEqual(empty["safe_to_spend"], Decimal("0.00"))
        self.assertEqual(empty["daily_outgoing"], Decimal("0.00"))
        self.assertFalse(empty["reconciliation"]["available"])
        overdrawn = build_health_report("-50", [], [schedule(amount="200")], now=NOW)
        self.assertEqual(overdrawn["safe_to_spend"], 0)
        self.assertEqual(overdrawn["shortfall"], Decimal("250.00"))

    def test_cash_flow_uses_bd_days_actual_posting_and_excludes_non_success(self):
        # 30-day start is 3 Sep BD; midnight is 2 Sep 18:00 UTC.
        first = datetime(2026, 9, 2, 18, tzinfo=timezone.utc)
        ledger = [tx(1, when=first, amount="100", fee="5"),
                  tx(2, amount="300", fee="12", direction="IN"),
                  tx(3, when=first - timedelta(seconds=1), amount="900"),
                  tx(4, status="FAILED", amount="900"), tx(5, status="DEFERRED", amount="900"),
                  tx(6, when=NOW + timedelta(days=1), amount="900")]
        result = build_health_report("1000", ledger, now=NOW)
        self.assertEqual(result["incoming"], Decimal("300.00"))
        self.assertEqual(result["outgoing"], Decimal("105.00"))
        self.assertEqual(result["net_flow"], Decimal("195.00"))
        self.assertEqual(result["daily_outgoing"], Decimal("3.50"))
        self.assertEqual(result["observed_count"], 2)

    def test_reconciliation_uses_explicit_anchor_and_detects_tampered_wallet(self):
        anchor = SimpleNamespace(opening_balance=Decimal("1000"), recorded_at=NOW - timedelta(days=10), source="Test anchor")
        ledger = [tx(1, amount="500", fee="20", direction="IN"), tx(2, amount="100", fee="5"),
                  tx(3, status="PENDING", amount="700"), tx(4, status="DEFERRED", amount="800"),
                  tx(5, when=NOW - timedelta(days=11), amount="900")]
        result = reconcile_ledger("1395", ledger, anchor)
        self.assertTrue(result["matched"])
        self.assertEqual(result["incoming"], Decimal("500.00"))
        self.assertEqual(result["outgoing"], Decimal("105.00"))
        self.assertEqual(result["successful_count"], 2)
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(result["pre_anchor_count"], 1)
        tampered = reconcile_ledger("1400", ledger, anchor)
        self.assertFalse(tampered["matched"])
        self.assertEqual(tampered["difference"], Decimal("5.00"))
        self.assertEqual(tampered["expected_balance"], Decimal("1395.00"))

    def test_large_payment_needs_five_same_kind_prior_successes_and_both_thresholds(self):
        baseline = [tx(index, when=NOW - timedelta(days=index + 1), fee="10") for index in range(1, 6)]
        large = tx(20, amount="1800", fee="50")
        signals = review_signals(baseline + [large], now=NOW)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "unusual")
        self.assertEqual(signals[0]["baseline"], Decimal("110.00"))
        self.assertEqual(signals[0]["threshold"], Decimal("1000.00"))
        self.assertEqual(review_signals(baseline[:4] + [large], now=NOW), [])
        self.assertEqual(review_signals(baseline + [tx(20, amount="1000")], now=NOW), [])
        self.assertEqual(review_signals(baseline + [tx(20, amount="2000", kind="SEND_MONEY")], now=NOW), [])
        self.assertEqual(review_signals(baseline + [tx(20, amount="2000", status="FAILED")], now=NOW), [])

    def test_repeat_rule_counts_distinct_receipts_including_same_second_only_same_recipient_amount_fee(self):
        first = tx(1, when=NOW - timedelta(minutes=10))
        second = tx(2, when=NOW)
        self.assertEqual(review_signals([first, second], now=NOW)[0]["kind"], "repeated")
        simultaneous = review_signals([tx(1), tx(2)], now=NOW)
        self.assertEqual(len(simultaneous), 1)
        self.assertEqual(simultaneous[0]["other_transaction"].id, 1)
        for changed in [tx(2, fee="1"), tx(2, amount="101"), tx(2, recipient="Another Utility"),
                        tx(2, when=NOW + timedelta(seconds=1)), tx(2, status="FAILED")]:
            with self.subTest(changed=changed):
                self.assertEqual(review_signals([first, changed], now=NOW), [])
        self.assertEqual(review_signals([tx(1, recipient=None), tx(2, recipient=None)], now=NOW), [])


class FinancialHealthRouteTests(AppTestCase):
    def setUp(self):
        super().setUp()
        ScheduledPayment.query.delete()
        PayLaterPurchase.query.delete()
        WalletOpeningBalance.query.delete()
        db.session.commit()

    def capture_health(self):
        captured = []
        def record(sender, template, context, **extra):
            captured.append(context)
        template_rendered.connect(record, self.app)
        try:
            response = self.client.get("/insights")
        finally:
            template_rendered.disconnect(record, self.app)
        self.assertEqual(response.status_code, 200)
        return response, captured[-1]["health"]

    def test_login_required_and_empty_account_explains_missing_anchor(self):
        self.assertEqual(self.client.get("/insights").status_code, 302)
        self.login()
        response, result = self.capture_health()
        self.assertEqual(result["safe_to_spend"], Decimal("1000.00"))
        self.assertIn(b"Opening anchor unavailable", response.data)
        self.assertIn(b"No commitments due soon", response.data)
        self.assertIn(b"No review signals from these rules", response.data)

    def test_account_isolation_and_financial_reads_do_not_mutate_wallet_or_ledger(self):
        self.login()
        now = datetime.now(timezone.utc)
        other = User(full_name="Private Person", mobile="01912345678", balance=Decimal("9999"))
        db.session.add(other)
        db.session.flush()
        for owner, principal, label in [(self.user_id, "100", "My commitment"), (other.id, "5000", "Private commitment")]:
            db.session.add(ScheduledPayment(user_id=owner, kind="SEND_MONEY", recipient_number="01712345678",
                recipient_name=label, amount=Decimal(principal), due_at=now + timedelta(days=1),
                status="SCHEDULED", recurrence_group=label))
        for index in range(2):
            db.session.add(Transaction(user_id=other.id, kind="BILL_PAYMENT", direction="OUT", title="Private receipt",
                counterparty="Private Utility", amount=Decimal("2000"), created_at=now))
        db.session.add(WalletOpeningBalance(user_id=other.id, opening_balance=Decimal("12000"),
                                            recorded_at=now - timedelta(days=10), source="Private anchor"))
        db.session.commit()
        before = (self.user.balance, other.balance, Transaction.query.count(), ScheduledPayment.query.count())
        response, result = self.capture_health()
        self.assertEqual(result["safe_to_spend"], Decimal("900.00"))
        self.assertEqual(result["observed_count"], 0)
        self.assertEqual(result["signal_count"], 0)
        self.assertFalse(result["reconciliation"]["available"])
        self.assertIn(b"My commitment", response.data)
        for private in [b"Private commitment", b"Private receipt", b"Private Utility", b"Private anchor"]:
            self.assertNotIn(private, response.data)
        self.assertEqual(before, (self.user.balance, other.balance, Transaction.query.count(), ScheduledPayment.query.count()))

    def test_overdue_auto_pay_remains_unpaid_when_opening_read_only_health(self):
        self.login()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = True
        from app.services.demo_seed import DEMO_RECIPIENT_MOBILE
        recipient = User.query.filter_by(mobile=DEMO_RECIPIENT_MOBILE).one()
        recipient_balance = recipient.balance
        payment = ScheduledPayment(user_id=self.user_id, kind="SEND_MONEY", recipient_number=recipient.mobile,
            recipient_name=recipient.full_name, amount=Decimal("100.00"),
            due_at=datetime.now(timezone.utc) - timedelta(days=1), status="SCHEDULED",
            auto_pay=True, recurrence_group="read-only-health")
        db.session.add(payment)
        db.session.commit()
        _, result = self.capture_health()
        db.session.refresh(payment)
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(recipient.balance, recipient_balance)
        self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(payment.status, "SCHEDULED")
        self.assertIsNone(payment.transaction_id)
        self.assertEqual(result["scheduled_reserve"], Decimal("100.00"))
        self.assertEqual(result["overdue_count"], 1)
        # Other app pages retain the existing request-driven Auto Pay behavior.
        self.assertEqual(self.client.get("/schedules").status_code, 200)
        self.assertEqual(payment.status, "COMPLETED")
        self.assertEqual(self.user.balance, Decimal("900.00"))
        self.assertEqual(recipient.balance, recipient_balance + Decimal("100.00"))
        self.assertEqual(Transaction.query.count(), 2)

    def test_anchor_comparison_and_owned_receipt_links_return_to_health(self):
        self.login()
        now = datetime.now(timezone.utc)
        db.session.add(WalletOpeningBalance(user_id=self.user_id, opening_balance=Decimal("1200"),
                                            recorded_at=now - timedelta(days=1), source="Explicit test anchor"))
        rows = [Transaction(user_id=self.user_id, kind="BILL_PAYMENT", direction="OUT", title="My repeated bill",
                            counterparty="Own Utility", amount=Decimal("100"), created_at=now) for _ in range(2)]
        db.session.add_all(rows)
        db.session.commit()
        response, result = self.capture_health()
        self.assertTrue(result["reconciliation"]["matched"])
        self.assertIn(b"Matched to opening anchor", response.data)
        self.assertIn(b"Similar payments close together", response.data)
        self.assertIn(f"/wallet/transaction/{rows[0].id}?return_to=/insights".encode(), response.data)
        self.assertIn(b"Back to Financial Health", self.client.get(f"/wallet/transaction/{rows[0].id}?return_to=/insights").data)

    def test_health_is_discoverable_and_bangla_localizes_copy_without_rewriting_user_values(self):
        self.login()
        self.assertIn("financial-health", [service["id"] for service in find_services("health")])
        self.assertEqual(service_return_target("/insights")["label"], "Financial Health")
        self.assertIn(b"/insights", self.client.get("/").data)
        self.assertIn(b"/insights", self.client.get("/search?q=health").data)
        with self.client.session_transaction() as session:
            session["language"] = "bn"
        response, _ = self.capture_health()
        self.assertIn("আর্থিক অবস্থার কেন্দ্র".encode(), response.data)
        self.assertIn("ব্যয়যোগ্য অর্থের হিসাব".encode(), response.data)
        self.assertIn("প্রারম্ভিক হিসাব পাওয়া যায়নি".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
