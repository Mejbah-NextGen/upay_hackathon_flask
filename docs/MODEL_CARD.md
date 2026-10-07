# Seven-day ordinary-outflow forecast — model card

Version 1.0.0, added 7 October 2026. This is an offline-trained predictive model
for the focused Financial Health flow. It predicts the total ordinary wallet
outflow over **today through day +6 in Bangladesh**, using the preceding **28
completed Bangladesh calendar days**. It does not execute payments or determine
eligibility for a financial product.

## What is actually learned

A scikit-learn `RandomForestRegressor` learns a supervised relationship between
historical spending features and subsequently observed seven-day totals. There
are 48 trees, a maximum depth of 7, and at least 20 training samples per leaf.
Features are the four weekly totals (oldest to newest), recent three-day total,
daily standard deviation, number of active days, median daily total, largest
daily total, and days since the latest debit. Monetary features and the target
are divided by the trailing 28-day weekly mean; the prediction is scaled back
to BDT. This allows a learned relationship across different wallet sizes.

The JSON artifact contains learned tree edges, thresholds and leaf values.
Inference uses the standard library and matches the estimator's float32 input
conversion. The training script verifies exported predictions against the
trained estimator before writing the artifact. Request handling does not train
a model and does not require NumPy, scikit-learn, an API key or an LLM.

Feature importances shown in the returned metadata describe split use across
the training forest. They are not causal explanations, individual monetary
contributions or evidence that a recommendation improves an outcome.

## Data and leakage controls

The entire training, selection, calibration and test corpus is **synthetic**.
The generator simulates independent users with steady, irregular, sparse,
rising, falling and volatile habits. Levels, weekday preferences, noisy weekly
state, intermittent activity and occasional large purchases vary by user.
These are development hypotheses, not measured Bangladesh customer behavior.
Amounts are generated first; forecast examples are then assembled from their
past and future windows. User IDs, profile labels, latent generator parameters
and future outcomes do not enter the features.

| Partition | Users | Forecast examples | Forecast dates | Last outcome date |
| --- | ---: | ---: | --- | --- |
| Train | 180 | 2,700 | 29 Jan–7 May 2025 | 13 May 2025 |
| Model selection | 30 | 120 | 18 Jun–9 Jul 2025 | 15 Jul 2025 |
| Error calibration | 30 | 120 | 18 Jun–9 Jul 2025 | 15 Jul 2025 |
| Final test | 60 | 300 | 20 Aug–17 Sep 2025 | 23 Sep 2025 |

User IDs are disjoint across all four partitions. All training outcome windows
end before the first selection/calibration input history; all calibration
outcome windows end before the first final-test input history. This purges the
seven-day target horizon and additionally separates the input histories.
Selection and calibration share dates but use different users. Within a user,
overlapping histories are correlated, so example counts must not be interpreted
as counts of independent customers or as inferential confidence.

The forest was selected against a standardized Ridge regression (`alpha=20`)
on the separate model-selection set: MAE BDT 1,192.4067 versus BDT 1,235.7077.
An earlier synthetic development prototype informed the family choice. After
freezing the generator and forest parameters, the final holdout users were
generated from a fresh independent seed, **20261014**, which was not used to fit
the model, choose its family or calibrate its range. Training, selection and
calibration use seed 20261007. The checked-in results below refer exclusively
to that fresh final holdout. No changes were selected using its outcomes.

## Measured results

| Method | Final-test MAE, BDT | Final-test RMSE, BDT |
| --- | ---: | ---: |
| Learned random forest | 2,130.1645 | 3,588.8999 |
| Trailing 28-day mean × 7 | 2,200.7637 | 3,894.3859 |
| Repeat last week's total | 2,579.1641 | 4,270.2315 |

On this synthetic holdout, MAE is 3.208% lower than the trailing mean and
17.409% lower than repeating the last week. This is a modest development
benchmark result; it is not evidence of real customer benefit, statistical
significance or guaranteed superiority on another corpus. Per-profile errors
are included in the JSON evaluation report so aggregate numbers do not hide
weaknesses in an individual pattern.

The error range uses the 90th percentile (`higher` quantile) of absolute
calibration error divided by trailing weekly mean. At inference that ratio is
multiplied by the user's own trailing weekly mean, with a minimum scale of BDT
1. Accounts with no ordinary outflow in the input window receive no prediction.
The lower endpoint is floored at zero.
The nominal calibration target is 90%; empirical coverage on the fresh test
is 94%. This is a descriptive synthetic error range, not a guaranteed
confidence interval. Distribution shift and unobserved commitments can make
coverage substantially worse.

## Wallet integration and failure behavior

Only successful outgoing transactions contribute principal plus fee. Incoming,
failed, deferred, today and future transactions cannot enter model history.
Naive database timestamps are interpreted as UTC and grouped into Bangladesh
dates, matching existing reporting. Linked completed scheduled-payment debits,
linked Pay Later repayments, and the `PAY_LATER_REPAYMENT` kind are excluded
from both history and today's ordinary spending. Known commitments are reserved
separately by Financial Health, which prevents the forecast from treating them
as ordinary spending again.

The model target covers the entire seven-day window including today. Because
the current wallet balance already reflects posted transactions today, planning
uses `predicted_remaining_outflow = max(0, predicted_outflow − observed_today_outflow)`.
The same subtraction is applied to range endpoints. Today's ordinary spending
must have posted strictly before `now`; later records are ignored. This
subtraction is a planning heuristic, not a probabilistic forecast update.

Insufficient coverage returns `available=false` and `reason=insufficient_history`.
Without an explicit account/ledger coverage date, the earliest completed receipt
is a conservative proxy. A provided coverage date allows known zero-spend days
to remain zero. A window with no ordinary outflow returns `insufficient_activity`
rather than a zero prediction and a misleadingly narrow error range.
Missing, malformed or cyclic model artifacts return
`model_unavailable`, and non-finite/negative historical debits return
`invalid_history`. No fabricated estimate is returned in these cases.

`forecast_for_user` scopes every query to the requested user and performs no
database writes. Training/evaluation calendar cutoffs are exposed as metadata;
they are synthetic experiment dates, not dates of real customer observations.
There is no claim that this artifact has been refreshed on current customer
behavior. The evaluation download contains only aggregate synthetic metrics.

## Reproduce and verify

```powershell
python -m pip install -r requirements-ml.txt
python scripts/train_cashflow_model.py --evaluate-only
python -m unittest tests.test_cashflow_model -v
# To recreate the frozen artifact and benchmark:
python scripts/train_cashflow_model.py
```

The first command is needed only for training or benchmark reproduction.
The evaluation-only command regenerates the synthetic corpus, reruns exported
inference and compares the full report to the checked-in evaluation. Training
also records a SHA-256 fingerprint of the generated dataset. The tests check
Bangladesh day boundaries, target/historical separation, commitment exclusions,
today's balance adjustment, user isolation, invalid-artifact behavior and
reproduced held-out metrics. They verify inference does not import training
libraries.

Artifacts: `app/ml/cashflow_random_forest.json` and
`app/ml/cashflow_evaluation.json`. Serving API:
`app/services/cashflow_model.py`; experiment:
`scripts/train_cashflow_model.py`.

Before claiming production readiness or measurable business benefit, collect
consented representative user data, measure forecast errors over later dates,
calibrate uncertainty on independent real histories, assess cold-start and
irregular-income cohorts, and run the controlled outcome measurements described
in the project's feedback response. There is no measured adoption, retention,
revenue, support reduction or user-research result in this model card.

Method references: [scikit-learn RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html)
and [time-ordered evaluation and gaps](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
