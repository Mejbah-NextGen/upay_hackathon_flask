from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.domain.pilot import PilotEvent, PilotFeedback, PilotParticipant
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.pilot_service import (
    enrol_participant, participant_for_user, pilot_context, pilot_metrics,
    record_activity, record_exposure, record_forecast_exposure, record_schedule_created,
    record_schedule_execution, record_task_completion, record_task_start,
    record_transaction, submit_feedback, withdraw_participant,
)
from tests.helpers import AppTestCase


class PilotTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.start = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)

    def enrol(self, user_id=None, *, source="DEMO", variant=None, verified=False):
        participant = enrol_participant(user_id or self.user_id, consent=True, data_source=source,
                                        real_attestation=source == "REAL", now=self.start)
        if variant:
            participant.variant = variant
        participant.verified_real = verified
        db.session.commit()
        return participant

    def other_user(self, mobile="01711223344"):
        user = User(full_name="Other Participant", mobile=mobile, balance=Decimal("1000.00"))
        db.session.add(user)
        db.session.commit()
        return user

    def transaction(self, user_id=None, *, when=None, status="SUCCESS", kind="BILL_PAYMENT"):
        tx = Transaction(user_id=user_id or self.user_id, kind=kind, direction="OUT",
                         title="Pilot bill", amount=Decimal("100.00"), status=status,
                         created_at=when or self.start + timedelta(days=1))
        db.session.add(tx)
        db.session.flush()
        return tx

    def schedule(self, *, status="SCHEDULED", due_day=2, transaction=None):
        schedule = ScheduledPayment(user_id=self.user_id, kind="BILL_PAYMENT", recipient_number="TEST-1234",
                                    amount=Decimal("100.00"), auto_pay=True, frequency="ONE_TIME",
                                    recurrence_group="pilot-test", status=status,
                                    created_at=self.start + timedelta(days=1),
                                    due_at=self.start + timedelta(days=due_day),
                                    transaction_id=transaction.id if transaction else None,
                                    executed_at=self.start + timedelta(days=due_day) if transaction else None)
        db.session.add(schedule)
        db.session.flush()
        record_schedule_created([schedule])
        return schedule

    def test_consent_required_and_demo_is_default(self):
        with self.assertRaises(ValidationError):
            enrol_participant(self.user_id)
        self.assertEqual(0, PilotParticipant.query.count())
        self.client.post("/pilot/enrol", data={"consent": "0"})
        self.assertEqual(0, PilotParticipant.query.count())
        self.client.post("/pilot/enrol", data={"consent": "1"})
        self.assertEqual("DEMO", participant_for_user(self.user_id).data_source)

    def test_assignment_and_source_are_fixed(self):
        participant = self.enrol()
        assigned = participant.variant
        self.assertEqual(assigned, enrol_participant(self.user_id, consent=True).variant)
        self.assertEqual(1, PilotParticipant.query.count())
        with self.assertRaises(ValidationError):
            enrol_participant(self.user_id, consent=True, data_source="REAL", real_attestation=True)
        self.assertEqual("DEMO", participant_for_user(self.user_id).data_source)

    def test_real_attestation_and_operator_verification_do_not_convert_demo_payments(self):
        with self.assertRaises(ValidationError):
            enrol_participant(self.user_id, consent=True, data_source="REAL")
        self.enrol(source="REAL")
        pending = pilot_metrics(data_source="REAL", now=self.start + timedelta(days=40))
        self.assertEqual(0, pending["participants"])
        self.assertEqual(1, pending["unverified_real_participants"])
        runner = self.app.test_cli_runner()
        denied = runner.invoke(args=["pilot-verify-real", "--user-id", str(self.user_id)])
        self.assertNotEqual(0, denied.exit_code)
        accepted = runner.invoke(args=["pilot-verify-real", "--user-id", str(self.user_id), "--confirm-researched"])
        self.assertEqual(0, accepted.exit_code, accepted.output)
        report = pilot_metrics(data_source="REAL", now=self.start + timedelta(days=40))
        self.assertEqual(1, report["participants"])
        self.assertIn("simulated", report["payment_mode"])
        self.assertFalse(report["business_impact_validated"])

    def test_control_has_different_feature_exposure(self):
        self.assertTrue(pilot_context(self.user_id)["forecast_enabled"])
        self.enrol(variant="control")
        self.assertFalse(pilot_context(self.user_id)["forecast_enabled"])
        control_page = self.client.get("/insights").get_data(as_text=True)
        self.assertNotIn('id="forecastTitle"', control_page)
        self.assertIn("Record planning review", control_page)
        participant_for_user(self.user_id).variant = "treatment"
        db.session.commit()
        self.assertTrue(pilot_context(self.user_id)["forecast_enabled"])
        treatment_page = self.client.get("/insights").get_data(as_text=True)
        self.assertIn('id="forecastTitle"', treatment_page)
        self.assertIn("Record planning review", treatment_page)

    def test_task_completion_requires_a_server_start_and_retries_deduplicate(self):
        self.enrol()
        self.assertIsNone(record_task_completion(self.user_id, "financial_health", now=self.start))
        first = record_task_start(self.user_id, "financial_health", now=self.start)
        self.assertEqual(first.id, record_task_start(self.user_id, "financial_health", now=self.start).id)
        record_task_completion(self.user_id, "financial_health", now=self.start + timedelta(minutes=2))
        self.assertEqual(first.id, record_task_start(self.user_id, "financial_health", now=self.start + timedelta(minutes=3)).id)
        self.assertIsNone(record_task_completion(self.user_id, "financial_health", now=self.start + timedelta(minutes=3)))
        record_exposure(self.user_id, now=self.start)
        record_exposure(self.user_id, now=self.start)
        db.session.commit()
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=1))
        arm = report["arms"][participant_for_user(self.user_id).variant]
        self.assertEqual(1, arm["planning_tasks_started"])
        self.assertEqual(1, arm["planning_tasks_completed"])
        self.assertEqual(1, arm["exposed_participants"])
        self.assertIsNone(report["planning_completion_uplift_pp"])

    def test_numerical_forecast_exposure_requires_active_treatment_and_deduplicates(self):
        self.assertIsNone(record_forecast_exposure(self.user_id, now=self.start))
        participant = self.enrol(variant="control")
        self.assertIsNone(record_forecast_exposure(self.user_id, now=self.start))
        participant.variant = "treatment"
        db.session.commit()
        first = record_forecast_exposure(self.user_id, now=self.start + timedelta(hours=1))
        repeated = record_forecast_exposure(self.user_id, now=self.start + timedelta(hours=2))
        self.assertEqual(first.id, repeated.id)
        record_forecast_exposure(self.user_id, now=self.start + timedelta(days=1))
        db.session.commit()
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=2))
        self.assertEqual(1, report["arms"]["treatment"]["forecast_shown_participants"])
        self.assertEqual(0, report["arms"]["control"]["forecast_shown_participants"])
        self.assertEqual(2, PilotEvent.query.filter_by(kind="FORECAST_SHOWN").count())
        withdraw_participant(self.user_id, now=self.start + timedelta(days=2))
        self.assertIsNone(record_forecast_exposure(self.user_id, now=self.start + timedelta(days=3)))

    def test_no_public_arbitrary_success_endpoint_and_auth_is_required(self):
        self.client.post("/pilot/events", json={"kind": "TRANSACTION", "resource_id": 999})
        self.assertEqual(0, PilotEvent.query.count())
        self.client.post("/pilot/plan-reviewed", data={"acknowledge": "1"})
        self.assertEqual(0, PilotEvent.query.count())
        with self.client.session_transaction() as session:
            session.clear()
        for path in ("/pilot", "/pilot/enrol", "/pilot/feedback", "/pilot/plan-reviewed"):
            response = self.client.get(path) if path == "/pilot" else self.client.post(path)
            self.assertEqual(302, response.status_code)
            self.assertIn("/login", response.location)

    def test_transactions_deduplicate_exclude_failed_passive_and_pre_enrolment(self):
        self.enrol()
        tx = self.transaction()
        record_transaction(tx)
        record_transaction(tx)
        record_transaction(self.transaction(status="FAILED"))
        record_transaction(self.transaction(kind="RECEIVE_MONEY"))
        record_transaction(self.transaction(when=self.start - timedelta(days=1)))
        db.session.commit()
        self.assertEqual(1, PilotEvent.query.filter_by(kind="TRANSACTION").count())
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=30))
        arm = report["arms"][participant_for_user(self.user_id).variant]
        self.assertEqual(1, arm["transactions_first_30_days"])
        self.assertEqual(1, arm["mature_30_participants"])

    def test_observations_roll_back_with_the_financial_transaction(self):
        self.enrol()
        tx = self.transaction()
        record_transaction(tx)
        record_activity(self.user_id, now=self.start + timedelta(days=1))
        self.assertEqual(2, PilotEvent.query.count())
        db.session.rollback()
        self.assertEqual(0, Transaction.query.count())
        self.assertEqual(0, PilotEvent.query.count())

    def test_event_only_transaction_is_not_committed_by_a_dedup_savepoint(self):
        self.enrol()
        record_activity(self.user_id, now=self.start + timedelta(days=1))
        record_task_start(self.user_id, "financial_health", now=self.start + timedelta(days=1))
        self.assertEqual(2, PilotEvent.query.count())
        db.session.rollback()
        self.assertEqual(0, PilotEvent.query.count())

    def test_enrolment_waits_for_callers_commit(self):
        enrol_participant(self.user_id, consent=True, now=self.start)
        self.assertEqual(1, PilotParticipant.query.count())
        db.session.rollback()
        self.assertEqual(0, PilotParticipant.query.count())

    def test_due_auto_pay_completion_uses_successful_linked_ledger(self):
        self.enrol()
        record_task_start(self.user_id, "recurring_payment", now=self.start)
        tx = self.transaction(when=self.start + timedelta(days=2))
        completed = self.schedule(status="COMPLETED", transaction=tx)
        record_schedule_execution(completed)
        record_schedule_execution(completed)
        self.schedule(status="FAILED")
        self.schedule(status="CANCELLED")
        self.schedule(due_day=100)
        db.session.commit()
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=40))
        arm = report["arms"][participant_for_user(self.user_id).variant]
        self.assertEqual(2, arm["auto_pay_due"])
        self.assertEqual(1, arm["auto_pay_completed"])
        self.assertEqual(0.5, arm["auto_pay_completion_rate"])
        self.assertEqual(1, arm["auto_pay_cancelled"])
        self.assertEqual(1, arm["recurring_tasks_completed"])
        self.assertEqual(1, PilotEvent.query.filter_by(kind="AUTO_PAY_COMPLETED").count())

    def test_retention_waits_for_full_window_and_does_not_count_early_activity(self):
        self.enrol()
        record_activity(self.user_id, now=self.start + timedelta(days=29))
        record_activity(self.user_id, now=self.start + timedelta(days=31))
        db.session.commit()
        variant = participant_for_user(self.user_id).variant
        premature = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=36))
        self.assertIsNone(premature["arms"][variant]["retention"]["30"]["rate"])
        mature = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=37))
        self.assertEqual(1, mature["arms"][variant]["retention"]["30"]["retained"])
        self.assertEqual(1, mature["arms"][variant]["retention"]["30"]["eligible"])
        self.assertIsNone(mature["arms"][variant]["retention"]["60"]["rate"])

    def test_source_separation_private_web_view_and_aggregate_no_free_text(self):
        self.enrol(variant="control")
        other = self.other_user()
        self.enrol(other.id, source="REAL", variant="treatment", verified=True)
        submit_feedback(other.id, {"problem": "planning", "usefulness": "4", "ease": "5", "missed_payments_last_30_days": "2", "comment": "Private other participant answer"}, now=self.start)
        db.session.commit()
        own_page = self.client.get(f"/pilot?user_id={other.id}").get_data(as_text=True)
        self.assertNotIn("Private other participant answer", own_page)
        self.assertNotIn("Other Participant", own_page)
        self.assertEqual(1, pilot_metrics(data_source="DEMO")["participants"])
        self.assertEqual(1, pilot_metrics(data_source="REAL")["participants"])
        report = self.app.test_cli_runner().invoke(args=["pilot-report", "--source", "REAL"])
        self.assertEqual(0, report.exit_code, report.output)
        payload = json.loads(report.output)
        self.assertEqual(1, payload["participants"])
        self.assertNotIn("Private other participant answer", report.output)
        self.assertNotIn(other.mobile, report.output)

    def test_retention_calendar_boundary_matches_daily_activity_dedup(self):
        # Enrol at 18:00 Dhaka, then visit before 18:00 on calendar day 30.
        # A rolling-hour window would lose this legitimate retention activity.
        self.start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.enrol()
        first = record_activity(self.user_id, now=datetime(2026, 1, 31, 1, tzinfo=timezone.utc))
        later = record_activity(self.user_id, now=datetime(2026, 1, 31, 15, tzinfo=timezone.utc))
        self.assertEqual(first.id, later.id)
        db.session.commit()
        variant = participant_for_user(self.user_id).variant
        # Day 37 starts at 18:00 UTC the previous day, in Dhaka.
        before = pilot_metrics(data_source="DEMO", now=datetime(2026, 2, 6, 17, 59, tzinfo=timezone.utc))
        self.assertIsNone(before["arms"][variant]["retention"]["30"]["rate"])
        mature = pilot_metrics(data_source="DEMO", now=datetime(2026, 2, 6, 18, tzinfo=timezone.utc))
        self.assertEqual(1, mature["arms"][variant]["retention"]["30"]["retained"])
        self.assertEqual(1, mature["arms"][variant]["retention"]["30"]["eligible"])

    def test_uplift_and_incremental_transactions_use_equal_mature_windows(self):
        self.enrol(variant="control")
        other = self.other_user()
        self.enrol(other.id, variant="treatment")
        for user_id in (self.user_id, other.id):
            record_task_start(user_id, "financial_health", now=self.start)
        record_task_completion(other.id, "financial_health", now=self.start + timedelta(days=1))
        for user_id, count in ((self.user_id, 1), (other.id, 3)):
            for _ in range(count):
                record_transaction(self.transaction(user_id, when=self.start + timedelta(days=1)))
        # Outside the common first-30-day window is never included in the uplift.
        record_transaction(self.transaction(other.id, when=self.start + timedelta(days=35)))
        db.session.commit()
        immature = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=29))
        self.assertIsNone(immature["incremental_transactions_per_participant_30_days"])
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=40))
        self.assertEqual(100, report["planning_completion_uplift_pp"])
        self.assertEqual(2, report["incremental_transactions_per_participant_30_days"])
        self.assertTrue(report["small_cohort"])

    def test_withdrawal_stops_collection_but_keeps_intention_to_treat_denominator(self):
        self.enrol()
        withdraw_participant(self.user_id, now=self.start + timedelta(days=5))
        db.session.commit()
        self.assertIsNone(record_activity(self.user_id, now=self.start + timedelta(days=31)))
        with self.assertRaises(ValidationError):
            submit_feedback(self.user_id, {})
        with self.assertRaises(ValidationError):
            enrol_participant(self.user_id, consent=True)
        report = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=40))
        arm = report["arms"][participant_for_user(self.user_id).variant]
        self.assertEqual(1, arm["withdrawn"])
        self.assertEqual(1, arm["retention"]["30"]["eligible"])
        self.assertEqual(0, arm["retention"]["30"]["retained"])

    def test_feedback_validation_and_latest_response_per_participant_summary(self):
        self.enrol()
        with self.assertRaises(ValidationError):
            submit_feedback(self.user_id, {"problem": "planning", "usefulness": "6", "ease": "3"})
        submit_feedback(self.user_id, {"problem": "planning", "usefulness": "1", "ease": "2", "missed_payments_last_30_days": "2"}, now=self.start)
        submit_feedback(self.user_id, {"problem": "recurring_payments", "usefulness": "5", "ease": "4", "missed_payments_last_30_days": "1"}, now=self.start + timedelta(days=1))
        submit_feedback(self.user_id, {"problem": "planning", "comment": "Could not understand the reserve."}, support=True, now=self.start + timedelta(days=2))
        db.session.commit()
        arm = pilot_metrics(data_source="DEMO", now=self.start + timedelta(days=40))["arms"][participant_for_user(self.user_id).variant]
        self.assertEqual(2, arm["research_responses"])
        self.assertEqual(1, arm["research"]["participants_responded"])
        self.assertEqual(5, arm["research"]["mean_usefulness"])
        self.assertEqual(1, arm["support_reports_first_30_days"])
        self.assertEqual(3, PilotFeedback.query.count())
