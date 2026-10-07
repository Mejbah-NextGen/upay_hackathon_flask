"""Read-only, offline-trained forecast of ordinary wallet outflow.

Known scheduled debits and Pay Later repayments are omitted because Financial
Health reserves those commitments separately. No model is trained at request
time, and no prediction authorizes or executes a payment.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math
from pathlib import Path
from statistics import median
import struct

from app.services.reporting_service import local_datetime


HISTORY_DAYS = 28
HORIZON_DAYS = 7
FEATURE_NAMES = (
    "week_1_outflow", "week_2_outflow", "week_3_outflow", "week_4_outflow",
    "recent_3_day_outflow", "daily_standard_deviation", "active_days",
    "median_daily_outflow", "largest_daily_outflow", "days_since_outflow",
)
FEATURE_LABELS = (
    "Oldest week's spending share", "Second week's spending share",
    "Third week's spending share", "Most recent week's spending share",
    "Recent three-day spending share", "Variation in daily spending",
    "Days with ordinary spending", "Median daily spending share",
    "Largest day's spending share", "Days since ordinary spending",
)
MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "cashflow_random_forest.json"
CENT = Decimal("0.01")


def extract_features(daily_amounts):
    """The training and serving contract: oldest-to-newest completed days."""
    values = [float(value) for value in daily_amounts]
    if len(values) != HISTORY_DAYS or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Expected 28 finite, non-negative daily outflow totals.")
    weeks = [sum(values[start:start + 7]) for start in range(0, HISTORY_DAYS, 7)]
    mean = sum(values) / HISTORY_DAYS
    deviation = math.sqrt(sum((value - mean) ** 2 for value in values) / HISTORY_DAYS)
    active = [index for index, value in enumerate(values) if value > 0]
    scale = sum(values) / 4 or 1.0
    # Ratios allow inference for wallet sizes beyond the synthetic training range.
    return [value / scale for value in weeks] + [sum(values[-3:]) / scale,
                    deviation / scale, len(active), median(values) / scale,
                    max(values) / scale, HISTORY_DAYS - 1 - active[-1] if active else HISTORY_DAYS]


def load_artifact(path=None):
    """Use declarative JSON, never pickle or executable model deserialization."""
    with Path(path or MODEL_PATH).open(encoding="utf-8") as source:
        artifact = json.load(source)
    if (artifact.get("schema_version") != 1 or artifact.get("feature_names") != list(FEATURE_NAMES)
            or artifact.get("history_days") != HISTORY_DAYS
            or artifact.get("horizon_days") != HORIZON_DAYS
            or artifact.get("output_scaling") != "trailing_28_day_weekly_mean"
            or artifact.get("algorithm") != "random_forest_regressor"
            or not artifact.get("trees")):
        raise ValueError("Unsupported forecast artifact schema.")
    numbers = [artifact["absolute_error_radius"], artifact["error_radius_ratio"]]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in numbers):
        raise ValueError("Forecast artifact contains invalid coefficients.")
    if any(value < 0 for value in numbers):
        raise ValueError("Forecast error radius must be non-negative.")
    if (len(artifact.get("feature_importances", [])) != len(FEATURE_NAMES)
            or not isinstance(artifact.get("model_name"), str)
            or not isinstance(artifact.get("model_version"), str)
            or not isinstance(artifact.get("evaluation"), dict)
            or not {"train", "calibration", "test"}.issubset(artifact.get("training_counts", {}))):
        raise ValueError("Missing forecast metadata.")
    for tree in artifact["trees"]:
        size = len(tree["value"])
        if not size or any(len(tree[field]) != size for field in ("left", "right", "feature", "threshold")):
            raise ValueError("Invalid forecast tree shape.")
        for index in range(size):
            if not math.isfinite(tree["value"][index]) or not math.isfinite(tree["threshold"][index]):
                raise ValueError("Non-finite forecast tree.")
            if tree["left"][index] == -1 and tree["right"][index] == -1:
                continue
            if (not 0 <= tree["feature"][index] < len(FEATURE_NAMES)
                    or not 0 <= tree["left"][index] < size or not 0 <= tree["right"][index] < size):
                raise ValueError("Invalid forecast tree edge.")
    return artifact


def predict_daily_history(daily_amounts, artifact):
    """Run exported learned trees; match sklearn's float32 input conversion."""
    features = [struct.unpack("f", struct.pack("f", value))[0] for value in extract_features(daily_amounts)]
    scale = sum(float(value) for value in daily_amounts) / 4
    predictions = []
    for tree in artifact["trees"]:
        node = 0
        for _ in range(len(tree["value"])):
            if tree["left"][node] == -1:
                predictions.append(tree["value"][node])
                break
            node = tree["left"][node] if features[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
        else:
            raise ValueError("Cyclic forecast tree.")
    return scale * max(0.0, sum(predictions) / len(predictions))


def model_evaluation(artifact_path=None):
    """Public offline benchmark only; no customer identifiers or transactions."""
    return load_artifact(artifact_path)["evaluation"]


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _day(value):
    return local_datetime(value).date() if isinstance(value, datetime) else value


def forecast_from_transactions(transactions, *, schedules=(), purchases=(), now=None,
                               history_start=None, artifact_path=None):
    """Forecast today through day +6, from the 28 preceding Bangladesh days.

    ``history_start`` is an account/ledger coverage date, not a first-spend date.
    When unavailable, the earliest completed transaction is a conservative proxy.
    The interval is empirical synthetic calibration error, not a guaranteed bound.
    """
    now = _utc(now or datetime.now(timezone.utc))
    today = local_datetime(now).date()
    start = today - timedelta(days=HISTORY_DAYS)
    result = {"available": False, "reason": None, "horizon_start": today,
              "horizon_end": today + timedelta(days=HORIZON_DAYS - 1),
              "history_start": start, "history_end": today - timedelta(days=1),
              "history_days": 0, "required_history_days": HISTORY_DAYS,
              "data_source": "synthetic training", "forecast_scope": "ordinary outflow",
              "interval_description": "90% empirical spending-scaled error range on synthetic calibration data"}
    transactions = list(transactions)
    completed = [tx for tx in transactions if tx.status == "SUCCESS" and _utc(tx.created_at) < now]
    coverage_start = _day(history_start) if history_start is not None else min(
        (_day(tx.created_at) for tx in completed if _day(tx.created_at) < today), default=today)
    if not isinstance(coverage_start, date):
        raise ValueError("history_start must be a date or datetime.")
    result["history_days"] = max(0, (today - coverage_start).days)
    result["coverage_source"] = "provided ledger coverage" if history_start is not None else "earliest completed receipt"
    if coverage_start > start:
        result["reason"] = "insufficient_history"
        return result
    schedule_ids = {item.transaction_id for item in schedules if item.transaction_id is not None}
    repayment_ids = {item.repayment_transaction_id for item in purchases
                     if item.repayment_transaction_id is not None}
    excluded_ids = schedule_ids | repayment_ids
    observed_today = Decimal("0.00")
    for tx in completed:
        if (tx.direction != "OUT" or _day(tx.created_at) != today
                or tx.id in excluded_ids or tx.kind == "PAY_LATER_REPAYMENT"):
            continue
        try:
            cost = Decimal(str(tx.amount)) + Decimal(str(tx.fee or 0))
        except InvalidOperation:
            result["reason"] = "invalid_history"
            return result
        if not cost.is_finite() or cost < 0:
            result["reason"] = "invalid_history"
            return result
        observed_today += cost
    result["observed_today_outflow"] = _money(observed_today)
    daily = [Decimal("0.00")] * HISTORY_DAYS
    observed_count = excluded_count = 0
    for tx in completed:
        day = _day(tx.created_at)
        if tx.direction != "OUT" or not start <= day < today:
            continue
        # The kind exclusion covers repayments even if a legacy link is absent.
        if tx.id in excluded_ids or tx.kind == "PAY_LATER_REPAYMENT":
            excluded_count += 1
            continue
        try:
            cost = Decimal(str(tx.amount)) + Decimal(str(tx.fee or 0))
        except InvalidOperation:
            result["reason"] = "invalid_history"
            return result
        if not cost.is_finite() or cost < 0:
            result["reason"] = "invalid_history"
            return result
        daily[(day - start).days] += cost
        observed_count += 1
    result.update(observed_count=observed_count, excluded_commitment_count=excluded_count,
                  active_days=sum(value > 0 for value in daily))
    if not any(value > 0 for value in daily):
        result["reason"] = "insufficient_activity"
        return result
    try:
        artifact = load_artifact(artifact_path)
        prediction = predict_daily_history(daily, artifact)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, IndexError, struct.error):
        result["reason"] = "model_unavailable"
        return result
    scale = sum(float(value) for value in daily) / 4
    radius = max(1.0, scale) * artifact["error_radius_ratio"]
    features = extract_features(daily)
    # Feature importances describe training split use; they are not causal
    # explanations or monetary contributions for this individual's prediction.
    top_drivers = [{"feature": FEATURE_NAMES[index], "label": FEATURE_LABELS[index],
                    "importance": importance, "value": features[index],
                    "value_units": "days" if index in {6, 9} else "ratio of trailing weekly mean"}
                   for index, importance in sorted(
        enumerate(artifact["feature_importances"]), key=lambda pair: pair[1], reverse=True)[:3]]
    result.update(available=True, predicted_outflow=_money(prediction),
                  lower_bound=_money(max(0, prediction - radius)),
                  upper_bound=_money(prediction + radius),
                  model_name=artifact["model_name"], model_version=artifact["model_version"],
                  metrics=artifact["evaluation"], training_counts=artifact["training_counts"],
                  error_quantile=0.90, top_drivers=top_drivers,
                  importance_scope="Training forest split importance; not an individual or causal contribution",
                  model_scale_bdt=_money(scale),
                  training_last_label_date=artifact["training_counts"]["train"]["last_label_date"],
                  evaluation_last_label_date=artifact["training_counts"]["test"]["last_label_date"],
                  predicted_remaining_outflow=_money(max(0, prediction - float(observed_today))),
                  remaining_lower_bound=_money(max(0, prediction - radius - float(observed_today))),
                  remaining_upper_bound=_money(max(0, prediction + radius - float(observed_today))),
                  remaining_method="Subtract observed ordinary outflow today; not a probabilistic model update",
                  model_features=dict(zip(FEATURE_NAMES, features)))
    return result


def forecast_for_user(user_id, *, now=None):
    """Only the authenticated user's history and commitment links are queried."""
    from app.domain.models import Transaction, User
    from app.domain.operations import ScheduledPayment
    from app.domain.payment_plans import PayLaterPurchase
    from app.extensions import db

    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError("Unknown forecast user.")
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    # Imported/demo ledgers may predate the local account record.
    coverage_start = min([_day(user.created_at)] + [_day(tx.created_at) for tx in transactions])
    return forecast_from_transactions(
        transactions, schedules=ScheduledPayment.query.filter_by(user_id=user_id).all(),
        purchases=PayLaterPurchase.query.filter_by(user_id=user_id).all(), now=now,
        history_start=coverage_start,
    )
