import builtins
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.domain.models import Transaction, User
from app.extensions import db
from app.services.cashflow_model import (FEATURE_NAMES, MODEL_PATH, extract_features,
    forecast_for_user, forecast_from_transactions, load_artifact, model_evaluation,
    predict_daily_history)
from app.services.reporting_service import local_datetime
from tests.helpers import AppTestCase


NOW = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)  # 8 October in Bangladesh.


def transaction(identifier, *, days=1, amount="100", fee="0", direction="OUT",
                status="SUCCESS", kind="SEND_MONEY", when=None):
    return SimpleNamespace(id=identifier, created_at=when or NOW - timedelta(days=days),
        amount=Decimal(amount), fee=Decimal(fee), direction=direction, status=status, kind=kind)


def history():
    return [transaction(day, days=day) for day in range(1, 29)]


class CashflowModelTests(unittest.TestCase):
    def test_requires_28_completed_days_or_explicit_account_coverage(self):
        result = forecast_from_transactions(history()[:27], now=NOW)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "insufficient_history")
        self.assertEqual(result["history_days"], 27)
        self.assertTrue(forecast_from_transactions(history()[:27], now=NOW,
            history_start=local_datetime(NOW).date() - timedelta(days=28))["available"])
        self.assertEqual(forecast_from_transactions([], now=NOW)["reason"], "insufficient_history")

    def test_bangladesh_history_boundaries_fees_and_full_seven_day_target(self):
        # Bangladesh start is 10 September; UTC storage midnight is 9 Sep 18:00.
        boundary = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)
        rows = history()
        rows[-1] = transaction(28, amount="100", fee="5", when=boundary.replace(tzinfo=None))
        clean = forecast_from_transactions(rows, now=NOW)
        changed = forecast_from_transactions(rows + [
            transaction(100, amount="99999", when=boundary - timedelta(seconds=1)),
            transaction(101, amount="99999", when=NOW + timedelta(days=1))], now=NOW)
        self.assertTrue(clean["available"])
        self.assertEqual(clean["horizon_start"].isoformat(), "2026-10-08")
        self.assertEqual(clean["horizon_end"].isoformat(), "2026-10-14")
        self.assertEqual(clean["history_start"].isoformat(), "2026-09-10")
        self.assertEqual(clean["history_end"].isoformat(), "2026-10-07")
        self.assertEqual(changed["observed_count"], 28)
        self.assertEqual(clean["predicted_outflow"], changed["predicted_outflow"])
        self.assertNotEqual(clean["predicted_outflow"], forecast_from_transactions(history(), now=NOW)["predicted_outflow"])

    def test_successful_ordinary_outgoing_only_no_future_leakage(self):
        extra = [transaction(100, amount="5000", status="FAILED"),
                 transaction(101, amount="5000", status="DEFERRED"),
                 transaction(102, amount="5000", direction="IN"),
                 transaction(103, amount="5000", when=NOW + timedelta(seconds=1))]
        base = forecast_from_transactions(history(), now=NOW)
        result = forecast_from_transactions(history() + extra, now=NOW)
        self.assertEqual(base["predicted_outflow"], result["predicted_outflow"])
        self.assertEqual(result["observed_count"], 28)

    def test_known_commitment_links_and_repayment_kind_are_excluded(self):
        rows = history() + [transaction(100, amount="9000"), transaction(101, amount="8000"),
                            transaction(102, amount="7000", kind="PAY_LATER_REPAYMENT")]
        result = forecast_from_transactions(rows, now=NOW,
            schedules=[SimpleNamespace(transaction_id=100)],
            purchases=[SimpleNamespace(repayment_transaction_id=101)])
        clean = forecast_from_transactions(history(), now=NOW)
        self.assertEqual(result["predicted_outflow"], clean["predicted_outflow"])
        self.assertEqual(result["excluded_commitment_count"], 3)

    def test_remaining_planning_subtracts_only_already_posted_ordinary_today(self):
        today = transaction(100, amount="300", fee="5", when=NOW - timedelta(minutes=1))
        future = transaction(101, amount="9000", when=NOW + timedelta(minutes=1))
        exact_now = transaction(102, amount="9000", when=NOW)
        commitment = transaction(103, amount="8000", when=NOW - timedelta(minutes=2))
        result = forecast_from_transactions(history() + [today, future, exact_now, commitment],
            schedules=[SimpleNamespace(transaction_id=103)], now=NOW)
        clean = forecast_from_transactions(history(), now=NOW)
        self.assertEqual(result["observed_today_outflow"], Decimal("305.00"))
        self.assertEqual(result["predicted_outflow"], clean["predicted_outflow"])
        self.assertEqual(result["predicted_remaining_outflow"], max(Decimal(0), result["predicted_outflow"] - 305))
        self.assertEqual(result["remaining_lower_bound"], max(Decimal(0), result["lower_bound"] - 305))
        self.assertEqual(result["remaining_upper_bound"], max(Decimal(0), result["upper_bound"] - 305))
        result = forecast_from_transactions(history() + [transaction(100, amount="99999", when=NOW - timedelta(minutes=1))], now=NOW)
        self.assertEqual(result["predicted_remaining_outflow"], Decimal("0.00"))

    def test_missing_invalid_or_cyclic_artifact_is_unavailable(self):
        artifact_path = MODEL_PATH.with_name("missing_forecast_test.json")
        self.assertEqual(forecast_from_transactions(history(), now=NOW, artifact_path=artifact_path)["reason"], "model_unavailable")
        with patch("pathlib.Path.open", return_value=StringIO('{"schema_version": 99}')):
            self.assertEqual(forecast_from_transactions(history(), now=NOW, artifact_path=artifact_path)["reason"], "model_unavailable")
        artifact = load_artifact()
        artifact["trees"][0]["left"][0] = 0
        artifact["trees"][0]["right"][0] = 0
        with patch("pathlib.Path.open", return_value=StringIO(json.dumps(artifact))):
            self.assertEqual(forecast_from_transactions(history(), now=NOW, artifact_path=artifact_path)["reason"], "model_unavailable")

    def test_invalid_amount_fails_without_fabricating_a_prediction(self):
        for value in ("NaN", "Infinity", "-100"):
            for when in (NOW - timedelta(days=1), NOW - timedelta(minutes=1)):
                with self.subTest(value=value, when=when):
                    result = forecast_from_transactions(history() + [transaction(100, amount=value, when=when)], now=NOW)
                    self.assertEqual(result["reason"], "invalid_history")
                    self.assertNotIn("predicted_outflow", result)

    def test_established_empty_account_does_not_fabricate_forecast_precision(self):
        result = forecast_from_transactions([], history_start=NOW - timedelta(days=28), now=NOW)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "insufficient_activity")
        self.assertEqual(result["history_days"], 28)
        self.assertNotIn("predicted_outflow", result)

    def test_fitted_tree_prediction_scales_with_wallet_outflow_and_has_metadata(self):
        artifact = load_artifact()
        one = predict_daily_history([100] * 28, artifact)
        two = predict_daily_history([200] * 28, artifact)
        self.assertAlmostEqual(two, one * 2, places=8)
        result = forecast_from_transactions(history(), now=NOW)
        self.assertEqual(result["data_source"], "synthetic training")
        self.assertEqual(result["metrics"]["model"]["sample_count"], 300)
        self.assertEqual(result["training_counts"]["train"]["samples"], 2700)
        self.assertEqual(result["model_version"], "1.0.0")
        self.assertEqual(len(result["top_drivers"]), 3)
        self.assertEqual(set(result["model_features"]), set(FEATURE_NAMES))

    def test_inference_does_not_import_training_libraries(self):
        original = builtins.__import__
        def reject_training_import(name, *args, **kwargs):
            if name.split(".")[0] in {"numpy", "sklearn"}:
                raise AssertionError("Inference imported an offline training dependency")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=reject_training_import):
            self.assertTrue(forecast_from_transactions(history(), now=NOW)["available"])

    def test_reproduced_fresh_holdout_metrics_and_purged_disjoint_partitions(self):
        try:
            from scripts.train_cashflow_model import build_partitions, evaluate, generate_series
        except ImportError:
            self.skipTest("Install requirements-ml.txt to reproduce the offline benchmark")
        partitions = build_partitions(generate_series())
        checked = model_evaluation()
        self.assertEqual(evaluate(load_artifact(), partitions), checked)
        groups = [partitions[name] for name in ("train", "model_selection", "calibration", "test")]
        for first_index, first in enumerate(groups):
            for second in groups[first_index + 1:]:
                self.assertTrue({row["user_id"] for row in first}.isdisjoint(row["user_id"] for row in second))
        self.assertLess(max(row["origin"] + 6 for row in partitions["train"]),
                        min(row["origin"] - 28 for row in partitions["calibration"]))
        self.assertLess(max(row["origin"] + 6 for row in partitions["calibration"]),
                        min(row["origin"] - 28 for row in partitions["test"]))
        self.assertEqual(checked["final_test_seed"], 20261014)
        self.assertFalse(checked["real_customer_validation"])
        self.assertGreaterEqual(checked["empirical_interval"]["held_out_test_coverage"], 0)
        self.assertLessEqual(checked["empirical_interval"]["held_out_test_coverage"], 1)

    def test_feature_contract_rejects_wrong_shape_and_nonfinite_values(self):
        for values in ([0] * 27, [float("nan")] * 28, [-1] * 28):
            with self.assertRaises(ValueError):
                extract_features(values)


class CashflowUserIsolationTests(AppTestCase):
    def test_authenticated_history_queries_are_scoped_and_read_only(self):
        other = User(full_name="Another person", mobile="01922223333", balance=Decimal("5000"),
                     created_at=NOW - timedelta(days=90))
        self.user.created_at = NOW - timedelta(days=90)
        db.session.add(other)
        db.session.flush()
        for day in range(1, 29):
            for owner, amount in ((self.user_id, "100"), (other.id, "2000")):
                db.session.add(Transaction(user_id=owner, kind="SEND_MONEY", direction="OUT",
                    title="Test history", amount=Decimal(amount), created_at=NOW - timedelta(days=day)))
        db.session.commit()
        before = (self.user.balance, other.balance, Transaction.query.count())
        mine = forecast_for_user(self.user_id, now=NOW)
        theirs = forecast_for_user(other.id, now=NOW)
        self.assertEqual(mine["observed_count"], 28)
        self.assertAlmostEqual(float(theirs["predicted_outflow"]), float(mine["predicted_outflow"] * 20), delta=0.11)
        self.assertEqual(before, (self.user.balance, other.balance, Transaction.query.count()))


if __name__ == "__main__":
    unittest.main()
