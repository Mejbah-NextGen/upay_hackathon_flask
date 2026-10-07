"""Reproducible synthetic experiment, not evidence of real customer impact.

Run: python scripts/train_cashflow_model.py
Verify checked-in learned trees: python scripts/train_cashflow_model.py --evaluate-only
Training requires requirements-ml.txt; Flask inference does not.
"""

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import sklearn

from app.services.cashflow_model import FEATURE_NAMES, extract_features, load_artifact, predict_daily_history


SEED = 20261007
TEST_SEED = 20261014  # Fresh holdout, frozen after the development prototype.
START = date(2025, 1, 1)
MODEL_PATH = PROJECT_ROOT / "app" / "ml" / "cashflow_random_forest.json"
EVALUATION_PATH = PROJECT_ROOT / "app" / "ml" / "cashflow_evaluation.json"
PROFILES = ("steady", "irregular", "sparse", "rising", "falling", "volatile")


def generate_series():
    """Independent synthetic users with noisy level, trend and weekday habits.

    Amounts are generated day by day before targets are constructed. User IDs,
    profile labels, latent generator parameters and future values never enter X.
    These patterns are hypotheses, not a Bangladesh customer dataset.
    """
    rng = np.random.default_rng(SEED)
    users = []
    for identifier in range(300):
        if identifier == 240:
            rng = np.random.default_rng(TEST_SEED)
        profile = PROFILES[identifier % len(PROFILES)]
        base = rng.uniform(120, 1500)
        trend = {"rising": 0.006, "falling": -0.003}.get(profile, rng.uniform(-0.001, 0.002))
        active_probability = {"sparse": 0.25, "irregular": 0.55}.get(profile, 0.92)
        noise = 0.55 if profile in {"volatile", "irregular"} else 0.20
        weekday = rng.uniform(0.65, 1.35, size=7)
        weekly_state = 0.0
        amounts = []
        for day in range(300):
            if day % 7 == 0:
                weekly_state = 0.65 * weekly_state + rng.normal(0, 0.12)
            expected = base * np.exp(trend * day + weekly_state)
            spend = (expected * weekday[(START + timedelta(days=day)).weekday()]
                     * rng.lognormal(-noise ** 2 / 2, noise))
            if rng.random() > active_probability:
                spend = 0
            elif rng.random() < 0.025:
                spend *= rng.uniform(1.8, 3.5)
            amounts.append(round(float(spend), 2))
        users.append({"id": identifier, "profile": profile, "daily": amounts})
    return users


def build_partitions(users):
    # All training labels end before calibration histories begin; the same holds
    # between calibration and test. IDs are disjoint as an additional safeguard.
    specifications = {"train": (0, 180, range(28, 127, 7)),
                      "model_selection": (180, 210, range(168, 190, 7)),
                      "calibration": (210, 240, range(168, 190, 7)),
                      "test": (240, 300, range(231, 260, 7))}
    partitions = {}
    for name, (first, last, origins) in specifications.items():
        rows = []
        for user in users[first:last]:
            for origin in origins:
                history = user["daily"][origin - 28:origin]
                target = sum(user["daily"][origin:origin + 7])
                rows.append({"user_id": user["id"], "profile": user["profile"],
                             "origin": origin, "history": history, "target": target})
        partitions[name] = rows
    return partitions


def score(actual, predicted):
    error = np.asarray(actual) - np.asarray(predicted)
    return {"mae_bdt": round(float(np.abs(error).mean()), 4),
            "rmse_bdt": round(float(np.sqrt(np.mean(error ** 2))), 4),
            "sample_count": len(actual)}


def summarize_partition(rows):
    origins = [row["origin"] for row in rows]
    return {"users": len({row["user_id"] for row in rows}), "samples": len(rows),
            "first_forecast_date": (START + timedelta(days=min(origins))).isoformat(),
            "last_forecast_date": (START + timedelta(days=max(origins))).isoformat(),
            "last_label_date": (START + timedelta(days=max(origins) + 6)).isoformat(),
            "first_history_date": (START + timedelta(days=min(origins) - 28)).isoformat()}


def evaluate(artifact, partitions):
    rows = partitions["test"]
    predictions = [predict_daily_history(row["history"], artifact) for row in rows]
    actual = [row["target"] for row in rows]
    model_score = score(actual, predictions)
    mean_score = score(actual, [sum(row["history"]) / 4 for row in rows])
    last_week_score = score(actual, [sum(row["history"][-7:]) for row in rows])
    radii = [max(1, sum(row["history"]) / 4) * artifact["error_radius_ratio"] for row in rows]
    coverage = sum(abs(value - prediction) <= radius for value, prediction, radius in zip(actual, predictions, radii)) / len(rows)
    per_profile = {}
    for profile in PROFILES:
        indexes = [index for index, row in enumerate(rows) if row["profile"] == profile]
        per_profile[profile] = score([actual[i] for i in indexes], [predictions[i] for i in indexes])
    return {"data_source": "synthetic training", "validation_scope": "held-out synthetic users and later dates",
            "real_customer_validation": False, "model": model_score,
            "baselines": {"trailing_28_day_mean": mean_score, "last_week": last_week_score},
            "mae_improvement_vs_mean_percent": round(100 * (1 - model_score["mae_bdt"] / mean_score["mae_bdt"]), 3),
            "mae_improvement_vs_last_week_percent": round(100 * (1 - model_score["mae_bdt"] / last_week_score["mae_bdt"]), 3),
            "empirical_interval": {"calibration_target_coverage": 0.90,
                                   "calibration_absolute_error_90th_percentile_bdt": round(artifact["absolute_error_radius"], 4),
                                   "spending_scaled_error_ratio": round(artifact["error_radius_ratio"], 6),
                                   "held_out_test_coverage": round(coverage, 4),
                                   "method": "90th percentile of absolute error / trailing weekly mean on calibration, higher quantile"},
            "by_synthetic_profile": per_profile,
            "partitions": {name: summarize_partition(rows) for name, rows in partitions.items()},
            "seed": SEED, "final_test_seed": TEST_SEED, "generator_version": "1",
            "model_selection": artifact["model_selection"],
            "training_library": f"scikit-learn {sklearn.__version__}",
            "limitations": ["No real user data, user research, adoption or revenue validation.",
                            "Overlapping histories within a user are correlated; metrics are descriptive.",
                            "Empirical interval has no guarantee under distribution shift.",
                            "Historical spending patterns do not account for unobserved commitments or income."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()
    users = generate_series()
    partitions = build_partitions(users)
    if args.evaluate_only:
        artifact = load_artifact(MODEL_PATH)
        evaluation = evaluate(artifact, partitions)
        checked = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
        if evaluation != checked:
            raise SystemExit("Evaluation differs from the checked-in report; reproduce with pinned ML dependencies.")
        print(json.dumps({"verified": True, "model": evaluation["model"],
                          "baselines": evaluation["baselines"],
                          "test_coverage": evaluation["empirical_interval"]["held_out_test_coverage"]}, indent=2))
        return
    rows = partitions["train"]
    features = np.asarray([extract_features(row["history"]) for row in rows])
    scales = np.asarray([sum(row["history"]) / 4 or 1.0 for row in rows])
    targets = np.asarray([row["target"] for row in rows]) / scales
    # Hyperparameters are fixed; calibration fits only the error
    # radius. Test outcomes are never used for fitting or parameter selection.
    regressor = RandomForestRegressor(n_estimators=48, max_depth=7, min_samples_leaf=20,
                                     random_state=SEED, n_jobs=1).fit(features, targets)
    selection_rows = partitions["model_selection"]
    selection_x = np.asarray([extract_features(row["history"]) for row in selection_rows])
    selection_scale = np.asarray([sum(row["history"]) / 4 for row in selection_rows])
    selection_y = [row["target"] for row in selection_rows]
    scaler = StandardScaler().fit(features)
    ridge = Ridge(alpha=20.0).fit(scaler.transform(features), targets)
    ridge_score = score(selection_y, np.maximum(0, ridge.predict(scaler.transform(selection_x))) * selection_scale)
    forest_score = score(selection_y, regressor.predict(selection_x) * selection_scale)
    if forest_score["mae_bdt"] >= ridge_score["mae_bdt"]:
        raise SystemExit("Frozen forest did not meet its model-selection criterion; do not inspect final test to tune it.")
    trees = [{"left": estimator.tree_.children_left.tolist(),
              "right": estimator.tree_.children_right.tolist(),
              "feature": estimator.tree_.feature.tolist(),
              "threshold": estimator.tree_.threshold.tolist(),
              "value": estimator.tree_.value[:, 0, 0].tolist()} for estimator in regressor.estimators_]
    artifact = {"schema_version": 1, "model_name": "Random forest cash-outflow regression",
                "model_version": "1.0.0", "history_days": 28, "horizon_days": 7,
                "algorithm": "random_forest_regressor",
                "data_source": "synthetic training", "feature_names": list(FEATURE_NAMES),
                "output_scaling": "trailing_28_day_weekly_mean",
                "trees": trees, "feature_importances": regressor.feature_importances_.tolist(),
                "training_parameters": {"n_estimators": 48, "max_depth": 7, "min_samples_leaf": 20,
                                        "random_state": SEED},
                "model_selection": {"criterion": "lower MAE on disjoint model-selection users",
                                    "ridge_alpha_20": ridge_score, "random_forest": forest_score,
                                    "selected": "random_forest",
                                    "development_note": "A previous synthetic prototype informed the model family; final test uses a fresh frozen independent seed.",
                                    "final_test_seed": TEST_SEED}}
    # Ensure exported inference agrees with the actual trained estimator.
    exported = np.asarray([predict_daily_history(row["history"], artifact) for row in rows])
    np.testing.assert_allclose(exported, scales * np.maximum(0, regressor.predict(features)), atol=1e-8)
    calibration = partitions["calibration"]
    residuals = [abs(row["target"] - predict_daily_history(row["history"], artifact)) for row in calibration]
    artifact["absolute_error_radius"] = float(np.quantile(residuals, 0.9, method="higher"))
    relative_residuals = [error / max(1, sum(row["history"]) / 4) for error, row in zip(residuals, calibration)]
    artifact["error_radius_ratio"] = float(np.quantile(relative_residuals, 0.9, method="higher"))
    artifact["training_counts"] = {name: summarize_partition(rows) for name, rows in partitions.items()}
    evaluation = evaluate(artifact, partitions)
    artifact["evaluation"] = evaluation
    artifact["training_dataset_sha256"] = hashlib.sha256(json.dumps(users, sort_keys=True).encode()).hexdigest()
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8", newline="\n")
    EVALUATION_PATH.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"artifact": str(MODEL_PATH), "model": evaluation["model"],
                      "baselines": evaluation["baselines"],
                      "improvement_percent": evaluation["mae_improvement_vs_mean_percent"]}, indent=2))


if __name__ == "__main__":
    main()
