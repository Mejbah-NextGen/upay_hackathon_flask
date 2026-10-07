# Hackathon feedback 1–4: implementation and evidence

These changes address the supplied Phase 1 feedback. Scores are the judges' original scores, not revised scores or predictions.

| Feedback | Original score | Implemented response | Evidence |
| --- | --- | --- | --- |
| Problem relevance | 16.67/20 | Dashboard and navigation lead with two tasks: weekly financial planning and recurring payments. Additional wallet services remain available under an expandable section. Consented research captures which problem users experience and whether the flow helps. | `/`, `/insights`, `/schedules`, `/pilot`; [pilot protocol](PILOT_PROTOCOL.md) |
| AI/ML depth | 10.33/20 | Offline supervised seven-day ordinary-outflow forecasting, learned model parameters, chronological evaluation with disjoint users, simple baselines and empirical error bounds. Runtime inference is local and separate from rule-based commitment arithmetic and the optional assistant. | [model card](MODEL_CARD.md), `scripts/train_cashflow_model.py`, `app/ml/`, `/insights/model-evaluation` |
| Business/customer impact | 12/20 | Opt-in randomized pilot, actual treatment exposure, server-recorded task and payment outcomes, cohort denominators, maturity-aware retention and support feedback. Verified real participants are separated from demo activity; all payments remain simulated. | `/pilot`; [pilot protocol](PILOT_PROTOCOL.md); operator aggregate CLI |
| Prototype quality | 13/15 | File-backed concurrent wallet/payment tests, duplicate request handling and injected interruption tests verify rollback and safe retry. Existing wallet, receipts, reports, language and authentication flows are retained. | `tests/test_reliability.py`; [reliability evidence](RELIABILITY.md) |

The experiment compares forecast-supported planning (treatment) with the existing commitment calculation (control). Both groups see the same focused dashboard and recurring payment tools. Assignment alone does not establish impact: report exposure, completed tasks, sample sizes and observation time alongside outcomes.

## Demonstration

1. Sign in with the existing demo account and OTP. Show the two dashboard tasks.
2. Open Financial Health. Explain recorded commitment reserves, then the learned forecast and its synthetic evaluation. Download the machine-readable evaluation.
3. Create a future recurring payment. Show that creating it does not debit the wallet and that receipt links appear after successful execution.
4. Open Pilot & Feedback, consent to a demo pilot, perform a planning task and submit research feedback. Show your recorded results and the operator aggregate output separately from verified real research.
5. Run `python -m unittest tests.test_reliability -v` to demonstrate actual concurrent operations and failure recovery; run the complete regression suite before presenting.

## Verification performed on 7 October 2026

- Full isolated regression suite: **231 tests passed**, including 12 file-backed concurrency/failure tests with enrolled participants.
- Existing browser QA: **170** English/Bangla page/viewport checks passed.
- New-feature browser QA: **32** English/Bangla checks at 320, 375, 768 and 1440 pixels, plus six end-to-end flows: CSRF-protected sign-in, consent, actual control/treatment display, planning review, research feedback and recurring setup without a debit.
- `python scripts/train_cashflow_model.py --evaluate-only` reproduced the checked-in fresh synthetic benchmark exactly. Model MAE was BDT **2,130.16**, compared with BDT **2,200.76** for the trailing-mean baseline. Real-pilot CLI output correctly showed zero participants and unavailable uplift before genuine recruitment.

The browser runners use isolated databases and write screenshots/results under `tmp/browser-qa` and `tmp/feedback-qa`; they do not modify the normal wallet dataset.

## Remaining external evidence

Code can supply a trained model and a controlled measurement system. It cannot retrospectively produce genuine customer interviews, adoption, 30/60/90-day retention, production settlement reliability or revenue. The supplied fixture and model evaluation are synthetic. Recruit consenting real participants, follow the protocol and collect mature outcomes before making customer-impact claims. No new score or production-readiness claim is made.

The remaining three feedback screenshots were not supplied in this request.
