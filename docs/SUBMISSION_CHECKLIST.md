# Submission acceptance checklist

Use [the original judge feedback](JUDGE_FEEDBACK.md) as the source of requirements.
The six supplied scores are historical. No updated judge score is guaranteed.
The seventh screenshot is pending; it has no inferred category or acceptance
requirement. This checklist separates working prototype evidence from customer
or deployment validation that remains external.

## Acceptance by supplied criterion

| Criterion | Demonstrate and verify | Evidence to include or reproduce | External validation still pending |
| --- | --- | --- | --- |
| 1. Problem relevance — 16.67 / 20 | Lead the demo with weekly financial planning and recurring payments. Show recorded commitments, explained available-money planning and the next payment. Explain why these two problems are the focus. | [Feedback 1–4](FEEDBACK_1_4.md), [pilot protocol](PILOT_PROTOCOL.md), dashboard, `/insights`, `/schedules`. | Consented representative customer interviews, observed pain points and a real controlled pilot. Implemented research tools do not establish actual customer validation. |
| 2. AI/ML depth — 10.33 / 20 | Show the trained seven-day random forest, its input history, purged/disjoint synthetic evaluation, baseline comparison, empirical error range, cold-start limits and source labels. Confirm guidance cannot execute money movement. | [Model card](MODEL_CARD.md), [evaluation JSON](../app/ml/cashflow_evaluation.json), [governance manifest](../app/ml/governance_manifest.json), offline benchmark reproduction and model tests. | Consented later-date real histories, real subgroup evaluation, uncertainty calibration and drift monitoring on the deployment population. |
| 3. Business/customer impact — 12.0 / 20 | Demonstrate separate control/treatment assignment, consent, exposure/task outcomes, recurring-payment completion, retention maturity and support/transaction denominators. Display unavailable or synthetic results honestly. | `/pilot`, [pilot protocol](PILOT_PROTOCOL.md), source-separated pilot CLI reports and `tests/test_pilot.py`. | Measured real task-completion uplift, Auto Pay outcomes, mature 30/60/90-day retention, support reduction and incremental transactions. No measured revenue or adoption claim. |
| 4. Prototype quality — 13.0 / 15 | Complete login, planning, future Auto Pay creation, a due payment, receipt/report and failure recovery. Demonstrate ownership, CSRF, duplicate submission, rollback and responsive English/Bangla usability. | [Reliability](RELIABILITY.md), wallet/payment/schedule tests, `tests/test_reliability.py`, browser runners and their actual output. | Human usability sessions and an assessed production environment. Automated browser checks do not establish customer usability or production readiness. |
| 5. Scalability & integration — 6.33 / 10 | Show the scoped API, payload-bound idempotency, PostgreSQL migration, durable workers, private metrics, request controls and independent signed HTTP provider recovery after a lost response. Inspect workload and invariant results. | [OpenAPI](openapi.yaml), [integration](INTEGRATION.md), [load evidence](LOAD_TEST.md), [deployment](DEPLOYMENT.md), reference-provider and disposable PostgreSQL runners. | Official Bangladesh upay/biller contracts and credentials, real settlement/reconciliation, managed database failover, target-deployment capacity and native Docker/Nginx execution. The reference provider is a sandbox. |
| 6. Responsible AI & security — 3.33 / 5 | Show shared quotas, bounded OTPs, revocable sessions, CSRF/ownership failures, review-only transaction signals, transactional signed audits, encrypted fields, explicit AI consent, scoped erasure/export, retention, in-flight invalidation and injection checks. | [Security](SECURITY.md), [responsible AI](RESPONSIBLE_AI.md), [offline safety result](../output/qa/ai-safety.json), security/privacy/monitoring tests and bilingual privacy/session QA. | Trusted OTP delivery, hardware/device-risk controls beyond cookie possession, independent penetration testing, live-model red teaming, production TLS/storage/backup controls, restricted database roles and immutable audit retention. |
| 7. Pending original screenshot | Preserve the pending status until the original feedback arrives. | [Original feedback status](JUDGE_FEEDBACK.md#7-pending-original-feedback). | Category, score and judge comments have not been supplied. |

The checked-in synthetic model currently reports held-out MAE **BDT 2,130.16**
across **300** examples, compared with **BDT 2,200.76** for the trailing-mean
baseline and **BDT 2,579.16** for the last-week baseline. Its empirical interval
covered **94%** of the synthetic held-out examples. These are model experiment
results, not customer business outcomes; use the full model card and JSON when
presenting them.

## Fresh-checkout smoke test

Use Python 3.12 and the explicit environment interpreter. Serving the learned
JSON model needs only the base dependencies; NumPy/scikit-learn are offline
reproduction dependencies.

For judge review, use the dedicated reconciled fixture. It creates or reuses
`instance/judge-demo.db`, selects the most recent completed 120-day synthetic
period, enables local model guidance and preserves the ordinary wallet file:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/judge_demo.py --check
.venv\Scripts\python.exe scripts/judge_demo.py --port 5000
```

Follow [phase_2.md](../phase_2.md) for the judge narrative and durable-worker
command. The fixture's runtime secret sidecar is local operational state and is
excluded from the submission bundle. The [database catalog](DATABASE_CATALOG.md)
separates the preserved main file, backups and the current expected 37-table
schema. To inspect only the separate judge file:

```powershell
.venv\Scripts\python.exe scripts/database_inventory.py --database instance/judge-demo.db --json tmp/submission-qa/judge-inventory.json --markdown tmp/submission-qa/judge-catalog.md
```

Open `http://127.0.0.1:5000/?days=30`, sign in with synthetic mobile `01329097775`
and code `123456`. Confirm Dashboard, Financial Health, Auto Pay, Report, Device
sessions and Privacy & AI open without errors. The dedicated judge launcher
keeps hosted AI and provider network calls disabled.

The [readiness report](../output/qa/submission/submission-readiness.json)
separately records initial fixture creation and an independent extracted source
checkout without the main DB, `.env` or `.venv`. That check created the reconciled
37-table, 120-day fixture, completed CSRF login, returned HTTP 200 on seven pages,
preserved database bytes on restart and inventoried only the judge file. The
existing interpreter supplied installed dependencies; its exact tested source
hashes match the workspace. This does not claim a new dependency-install run.
The
[final judge browser walkthrough](../output/qa/submission/judge-browser.json)
completed 52 responsive checks, 64 UI assertions and 20 parsed exports across
English and Bangla at 390/1440 pixels after the final presentation fixes. Main
and default judge file hashes stayed unchanged. It recorded zero walkthrough,
page/CSP or overflow errors and four deliberate offline-recipient abort console
notices.

For historical context, an isolated legacy-development fresh-start check on
7 October 2026 created **37 application tables**,
two synthetic wallets and 124 legacy sample receipts, completed CSRF-protected
login, set a device cookie and returned HTTP 200 on those six pages and readiness.
It used a new QA database and did not open the normal project wallet database.
That legacy sample is distinct from the reconciled four-wallet judge fixture;
the legacy receipts explicitly disclose that an opening anchor is unavailable.
Use the dedicated judge launcher above for review. Advanced administration and
backup-protected migration adoption belong in [DEPLOYMENT.md](DEPLOYMENT.md);
the development app's automatic schema creation is not a PostgreSQL migration
substitute.

## Reproducible verification and evidence packaging

```powershell
.venv\Scripts\python.exe -m unittest discover -v
.venv\Scripts\python.exe scripts/evaluate_ai_safety.py --output output/qa/ai-safety.json
.venv\Scripts\python.exe scripts/provider_contract_demo.py --output tmp/infrastructure-qa/provider-contract.json
.venv\Scripts\python.exe scripts/load_test.py --output tmp/infrastructure-qa/load-sqlite.json
```

Install `requirements-ml.txt` before reproducing the offline model benchmark.
Without those optional libraries, that benchmark test is skipped; serving tests
still run. PostgreSQL tests are intentionally skipped without the disposable
runner; install `requirements-production.txt` and follow [LOAD_TEST.md](LOAD_TEST.md)
to obtain actual PostgreSQL evidence. A skipped test is not a successful
PostgreSQL or model-reproduction observation. Browser runners require installed
Chrome; follow their documented commands and preserve actual error counts.

The [current final suite](../output/qa/submission/regression-current.json)
discovered 335 tests: **329 passed and six PostgreSQL-only cases were skipped**
in 78.924 seconds. Judge fixture, 12 inventory and four packaging tests ran;
optional ML reproduction was installed. The six actual PostgreSQL observations
remain a separate report. The earlier 303-pass suite is retained as a historical
baseline, not relabelled as current.

Before handing over the submission, include:

- This canonical feedback transcription, code, model/evaluation/governance JSON,
  dependency files, migrations, deployment configuration and linked guides.
- Actual aggregate unit, browser, model, load and provider-recovery reports with
  observation dates, workload, platform, configuration scope and checksums.
- The [reviewed aggregate evidence bundle](../output/qa/submission/README.md) and
  [provenance manifest](../output/qa/submission/manifest.json), which retain run
  dates and source/artifact SHA256s. `tmp/infrastructure-qa` remains ignored and
  absent from a fresh checkout; reviewed JSON copies are checked in. The earlier
  303-pass report is explicitly a historical baseline, distinct from the current
  final-polish suite and its skipped test scopes.
- The external pending items above and the missing seventh screenshot status.

Exclude `.env`, private credentials, real customer records, live databases,
unnecessary backups and downloaded PostgreSQL binaries from the evidence bundle.
Do not relabel historical screenshots/PDFs as newly measured results. Docker
configuration parsing and CLI contract checks are documented; this environment
did not launch Docker or execute `nginx -t`.

Build the review archive only after final checks and guide updates:

```powershell
.venv\Scripts\python.exe scripts/build_submission.py
```

The default is `output/submission/UPAYX_SUBMISSION.zip`; use `--overwrite` for an
intentional rebuild. The deterministic allowlist excludes runtime databases,
sidecars, tokens, logs, caches, `.env`, private uploads and downloaded binaries.
Inspect `SUBMISSION_MANIFEST.json` for file SHA256s and the historical PDF label.
This packages the prototype locally; it does not externally submit or publish it.
