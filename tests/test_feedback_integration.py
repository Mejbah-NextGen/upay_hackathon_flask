"""Verify the measured pilot uses the delivered planning/payment experiences."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.container import get_container
from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.domain.pilot import PilotEvent
from app.extensions import db
from app.services.pilot_service import enrol_participant, pilot_metrics
from tests.helpers import AppTestCase


class FeedbackIntegrationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = False

    def enrol(self, variant="treatment"):
        participant = enrol_participant(self.user_id, consent=True)
        participant.variant = variant
        db.session.commit()
        return participant

    def history(self):
        now = datetime.now(timezone.utc)
        for day in range(1, 30):
            db.session.add(Transaction(user_id=self.user_id, kind="BILL_PAYMENT", direction="OUT",
                                       title="Ordinary historical bill", amount=Decimal("10"),
                                       created_at=now - timedelta(days=day)))
        db.session.commit()

    def test_control_assignment_cannot_be_overridden_and_treatment_displays_model(self):
        participant = self.enrol("control")
        self.history()
        response = self.client.get("/insights?variant=treatment")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'id="forecastTitle"', response.data)
        self.assertEqual(PilotEvent.query.filter_by(kind="FORECAST_SHOWN").count(), 0)
        self.assertIn(b'id="planningReviewTitle"', response.data)
        participant.variant = "treatment"
        db.session.commit()
        response = self.client.get("/insights")
        self.assertIn(b'id="forecastTitle"', response.data)
        self.assertIn(b"Expected everyday money out", response.data)
        self.assertIn(b"Held-out mean absolute error", response.data)
        self.assertEqual(PilotEvent.query.filter_by(kind="FORECAST_SHOWN").count(), 1)
        self.assertEqual(PilotEvent.query.filter_by(user_id=self.user_id, kind="TASK_STARTED").count(), 1)

    def test_review_redirect_and_refresh_keep_one_task_denominator(self):
        self.enrol()
        self.client.get("/insights")
        self.client.post("/pilot/plan-reviewed", data={"acknowledge": "1"}, follow_redirects=True)
        self.client.get("/insights")
        self.client.post("/pilot/plan-reviewed", data={"acknowledge": "1"}, follow_redirects=True)
        arm = pilot_metrics(data_source="DEMO", user_id=self.user_id)["arms"]["treatment"]
        self.assertEqual(arm["planning_tasks_started"], 1)
        self.assertEqual(arm["planning_tasks_completed"], 1)

    def test_failed_render_does_not_record_task_or_exposure(self):
        self.enrol()
        with patch("app.blueprints.insights.routes.render_template", side_effect=RuntimeError("render interrupted")):
            with self.assertRaises(RuntimeError):
                self.client.get("/insights")
        self.assertEqual(PilotEvent.query.count(), 0)

    def test_model_download_is_offline_evidence_without_wallet_records(self):
        db.session.add(Transaction(user_id=self.user_id, kind="SEND_MONEY", direction="OUT",
                                   title="PRIVATE-WALLET-TITLE", reference="PRIVATE-REFERENCE", amount=Decimal("10")))
        db.session.commit()
        response = self.client.get("/insights/model-evaluation")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json["model"]["sample_count"], 0)
        self.assertFalse(response.json["real_customer_validation"])
        self.assertNotIn(b"PRIVATE-WALLET-TITLE", response.data)
        self.assertNotIn(b"PRIVATE-REFERENCE", response.data)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/insights/model-evaluation").status_code, 302)

    def test_successful_payment_hook_and_composing_rollback_are_atomic(self):
        self.enrol()
        wallet = get_container().wallet
        first = wallet.debit_for_payment(self.user_id, kind="BILL_PAYMENT", title="Measured bill",
                                        counterparty="Demo", amount_raw="100")
        self.assertEqual(PilotEvent.query.filter_by(kind="TRANSACTION", resource_id=first.id).count(), 1)
        second = wallet.debit_for_payment(self.user_id, kind="BILL_PAYMENT", title="Interrupted bill",
                                         counterparty="Demo", amount_raw="50", commit=False)
        second_id = second.id
        db.session.rollback()
        self.assertEqual(db.session.get(Transaction, second_id), None)
        self.assertEqual(PilotEvent.query.filter_by(kind="TRANSACTION", resource_id=second_id).count(), 0)
        self.assertEqual(wallet.get_user(self.user_id).balance, Decimal("900"))

    def test_scheduling_completion_tracks_saved_plan_without_early_debit(self):
        self.enrol()
        self.client.get("/schedules")
        from app.services.schedule_service import scheduling_window
        first_date, _ = scheduling_window()
        response = self.client.post("/schedules", data={
            "kind": "BILL_PAYMENT", "category": "electricity", "provider": "DESCO Electricity",
            "recipient_number": "DEMO-METER-1001", "amount": "25", "due_date": first_date.isoformat(),
            "frequency": "ONE_TIME", "auto_pay": "1",
        })
        self.assertEqual(response.status_code, 302)
        arm = pilot_metrics(data_source="DEMO", user_id=self.user_id)["arms"]["treatment"]
        self.assertEqual(arm["recurring_tasks_completed"], 1)
        self.assertEqual(arm["auto_pay_due"], 0)
        self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(self.user.balance, Decimal("1000"))
        self.assertEqual(PilotEvent.query.filter_by(kind="SCHEDULE_CREATED").count(), 1)

    def test_research_page_does_not_execute_due_payments(self):
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = True
        item = ScheduledPayment(user_id=self.user_id, kind="BILL_PAYMENT", recipient_number="DEMO-METER-1001",
                                provider="DESCO Electricity", category="electricity", amount=Decimal("25"),
                                due_at=datetime.now(timezone.utc) - timedelta(days=1), auto_pay=True,
                                recurrence_group="research-read-only")
        db.session.add(item)
        db.session.commit()
        self.assertEqual(self.client.get("/pilot").status_code, 200)
        self.assertEqual(self.user.balance, Decimal("1000"))
        self.assertEqual(item.status, "SCHEDULED")
