# UpayX — Phase 2 submission guide

**Reviewed: 7 October 2026 · Python 3.12 · Asia/Dhaka (UTC+6) · synthetic-money prototype**

UpayX focuses on two customer tasks: **planning the next week's available wallet money** and **managing recurring payments**. Existing wallet, receipt, reporting and Bangla/English flows remain available. Phase 2 adds a genuinely trained forecast, controlled pilot measurement, transactional failure/concurrency verification, scoped APIs, PostgreSQL migrations, durable workers and privacy/security controls.

This file is the judge's entry point for login, running the project, inspecting every database and reproducing the evidence. The [original judge comments and scores](docs/JUDGE_FEEDBACK.md) are preserved verbatim. The attachments contain categories **1–6**; category 7's screenshot, score and comments have not been supplied. Its response remains pending. The original scores are historical results; revised marks are determined by the judges.

## 1. Run the judge demo

Use Windows PowerShell from the project root. Python 3.12 is the tested version. No API key, SMS account, PostgreSQL server or `.env` file is needed for this demo.

```powershell
cd D:\upay_hackathon_flask
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/judge_demo.py
```

If the project was extracted elsewhere, change the first command to that directory. If `.venv` already exists, reuse it and install the requirements. Calling its Python executable directly avoids PowerShell activation-policy problems.

Open **http://127.0.0.1:5000/?days=30**. The 30-day filter makes the existing completed history visible; the default Today filter can correctly show no activity before a judge creates a payment. Keep the terminal open. Stop with `Ctrl+C`. If port 5000 is occupied:

```powershell
.venv\Scripts\python.exe scripts/judge_demo.py --port 5001
```

The launcher creates **`instance/judge-demo.db`** once, using the reconciled `household-ledger-v2` generator. The 120-day window ends on **yesterday's completed Bangladesh calendar day** on first creation. On 7 October, that is 9 June–6 October 2026 inclusive. Restart preserves the frozen window, balances, plans and later judge activity. A new independent demonstration can use an unused dedicated name:

```powershell
.venv\Scripts\python.exe scripts/judge_demo.py --database instance/judge-review.db --as-of 2026-10-06 --port 5001
```

`--as-of` determines a newly created fixture; it does not replace an existing fixture. The launcher requires a `judge-*.db` filename within the project's `instance` directory and rejects the main wallet database, outside paths, unsafe aliases and unidentified existing files. It has no reset/delete operation. It binds to `127.0.0.1`, disables debug/reloader, hosted AI and provider connections, keeps CSRF and trusted browser sessions, and executes no payments on page visits. It ignores production/provider environment settings and never touches `instance/upay_hackathon.db`.

Check the fixture's schema, synthetic provenance, ledger reconciliation and local model before serving:

```powershell
.venv\Scripts\python.exe scripts/judge_demo.py --check
```

The judge database has 37 application tables created explicitly for this development fixture. It is not a migrated production database and does not claim an Alembic deployment revision. Serving the learned JSON forecast needs only `requirements.txt`; training and full offline benchmark reproduction additionally need `requirements-ml.txt`.

### Login and demonstration accounts

| Purpose | Mobile/reference | Instructions |
| --- | --- | --- |
| Main household | `01329097775` | Continue on Login, then enter synthetic OTP `123456` |
| Recipient wallet | `01944000001` | Demo Recipient Ayesha; can receive local Send Money |
| Sender wallet | `01944000004` | Demo Sender Karim; same synthetic OTP |
| Landlord wallet | `01944000005` | Demo Landlord Rahman; same synthetic OTP |
| Authorized agent directory example | `01944000002` | Cash Out example; not a sign-in wallet |
| Recharge subscriber | `01944000003` | Select Banglalink; directory example, not a sign-in wallet |
| Blocked mobile fixture | `01944000099` | Server rejects applicable operations |
| Electricity bill | `DEMO-METER-1001` | DESCO Electricity |
| Gas bill | `DEMO-GAS-1001` | Titas Gas |
| Blocked bill fixture | `DEMO-BLOCKED-1001` | Server rejects the payment |

There is **no account password**. Request a new code if its five-minute challenge expires. Wrong-code attempts are bounded; login and assistant requests are rate limited. These accounts and the shared OTP are exclusively synthetic development fixtures. Production hides demo identity/code hints, starts new balances at zero and requires a trusted SMS delivery adapter. No production credentials are included in the submission.

## 2. Judge walkthrough

The six-minute walkthrough demonstrates the focused product and keeps its claims traceable to visible results.

| Step | Action | Evidence to inspect |
| --- | --- | --- |
| 1. Weekly planning | Login, select 30 days, open **Financial Health** | Known commitments, local seven-day ordinary-outflow prediction, error range, remaining-outflow adjustment and independent opening-balance reconciliation |
| 2. Genuine ML | Open the model explanation/evaluation; inspect [the model card](docs/MODEL_CARD.md) | Learned 48-tree random forest, disjoint synthetic train/selection/calibration/test users, a frozen fresh test seed and baseline comparisons |
| 3. Recurring payment | Open **Auto Pay**, create a small future DESCO plan and review its dates | Saving a plan creates a commitment and leaves the wallet balance unchanged; **Pay if due** rejects a future installment |
| 4. End-to-end receipt | Send a small synthetic amount to `01944000001`, inspect its summary and download PDF/JPG | Equal sender/recipient ledger effects, fee-inclusive balance, owned receipt and repeated-submission protection |
| 5. Report | Filter **Report**, drill into a chart and download Excel/PDF | Downloads use the displayed filters; pending plans are separate from successful wallet totals |
| 6. Guidance/privacy | Ask the local assistant about school fees; open **Privacy settings** and **Device sessions** | Guidance links to forms, separate consent controls, owner export/erasure receipt and session revocation; AI has no payment authority |
| 7. Measurement | Open **Planning pilot** (`/pilot`), enrol as DEMO with consent, perform a planning/task action | Persisted task denominators, randomized display assignment and source-separated aggregate report; generated activity is never verified as real research |

Switch **EN / বাংলা** and repeat planning, Auto Pay and privacy on a mobile viewport. The [complete user manual](USER_MANUAL.md) covers the remaining screens. Financial Health is read-only. The chosen receipt step intentionally changes only the isolated judge ledger; it does not make a real transfer.

For scheduler verification, use another terminal in the same project/environment:

```powershell
.venv\Scripts\python.exe -m flask --app scripts.judge_demo:create_judge_app durable-worker --watch --interval 5 --batch-size 20
```

Omit `--watch` for one batch. The default factory uses the same `instance/judge-demo.db`. For a custom fixture, use the explicit factory argument:

```powershell
.venv\Scripts\python.exe -m flask --app "scripts.judge_demo:create_judge_app(database='instance/judge-review.db')" durable-worker --batch-size 20
```

Only due, automatic, eligible plans execute. Successful execution claims the installment and commits its debit, receipt and ledger audit together. Business rejections deduct nothing and remain failed for review. Unexpected interruptions retain bounded retry/backoff state; exhaustion requires review. Run a supervised durable worker in deployment; browser visits are not the production scheduler.

## 3. Feedback response and acceptance evidence

The exact source comments are in [JUDGE_FEEDBACK.md](docs/JUDGE_FEEDBACK.md). This table describes the implemented response, without rewriting the judges' wording or scores.

| Supplied category | Original P1 score | Phase 2 response | Validation and remaining dependency |
| --- | --- | --- | --- |
| 1. Problem relevance | 16.67 / 20 | Dashboard prioritizes weekly planning and recurring payments; consented research/task flow captures prioritized needs | Working English/Bangla flows; representative user interviews and experimental pain-point validation require recruited users |
| 2. AI/ML depth | 10.33 / 20 | Offline-trained supervised random forest and standard-library JSON inference; documented features, leakage controls, baseline/error evaluation | Fresh 300-example synthetic holdout reproduced; real-history error and uncertainty validation remain pending |
| 3. Business/customer impact | 12.0 / 20 | Consent, fixed randomized control/forecast arms, trusted task/payment hooks, KPI numerators/denominators and mature follow-up windows | Automated prototype measurement verified; no fabricated adoption, retention, revenue or support-reduction results |
| 4. Prototype quality | 13.0 / 15 | Existing wallet/receipt/report flows preserved; atomic/idempotent writes, concurrent claim/debit and injected rollback tests | Isolated regression and real-browser flow/layout checks; local test results are not production certification |
| 5. Scalability & integration | 6.33 / 10 | Scoped versioned API, signed HTTP reference provider/outbox/reconciliation, PostgreSQL migrations, durable workers, gateway and observability | Actual PostgreSQL concurrency and HTTP load runs; official Bangladesh upay contract/credentials and deployed capacity tests remain external |
| 6. Responsible AI & security | 3.33 / 5 | One-use OTP boundary, revocable browser sessions, shared quotas, signed audit, review signals, field encryption, consent/retention/erasure and multilingual injection checks | Negative-path/race/security UI tests and 35 offline corpus checks; independent penetration and live hosted-model assessments remain pending |
| 7. Pending screenshot | Not supplied | No category, comments or score inferred | Supply the original seventh feedback before claiming all seven have been addressed |

See [feedback 1–4](docs/FEEDBACK_1_4.md), [feedback 5–6](docs/FEEDBACK_5_6.md) and [the submission checklist](docs/SUBMISSION_CHECKLIST.md) for code/test links.

### Model evidence

The model forecasts the total ordinary outflow over today through day +6, using the preceding 28 completed Dhaka days. It excludes linked scheduled-payment and Pay Later repayment debits, which are reserved separately. Current-day posted ordinary spending is subtracted for the planning estimate. It learns from synthetic spending histories, not rules or an LLM; balance reconciliation and commitment reserves remain explained deterministic calculations.

| Fresh synthetic final test | MAE, BDT | RMSE, BDT |
| --- | ---: | ---: |
| Learned random forest | 2,130.1645 | 3,588.8999 |
| Trailing 28-day mean × 7 | 2,200.7637 | 3,894.3859 |
| Repeat last week | 2,579.1641 | 4,270.2315 |

The 300 test examples belong to 60 held-out synthetic users. MAE is 3.208% lower than the trailing-mean baseline in this experiment. Synthetic error-range coverage is 94%; this is not a guaranteed real-world interval or a measured customer improvement. The model returns unavailable states for insufficient/invalid history or an unapproved/corrupt artifact. Training importances are split-use summaries, not causal explanations. Inference verifies the approved release hash; request handling never trains.

### Customer and business measurement

The pilot compares recorded-commitment planning with the same page plus the learned forecast. Allocation is fixed and source-labelled. Started tasks, acknowledgements, persisted plans and successful initiated transactions are collected through trusted server hooks; repeated visits and rolled-back payments cannot inflate completion totals. Follow-up retention windows are days 30–36, 60–66 and 90–96, with only mature participants in each denominator. Empty denominators are unavailable, not fabricated zeros. Prototype support reports are not call-center contacts and synthetic transactions are not real business growth.

```powershell
.venv\Scripts\python.exe -m flask --app scripts.judge_demo:create_judge_app pilot-report --source DEMO
.venv\Scripts\python.exe -m flask --app scripts.judge_demo:create_judge_app pilot-report --source REAL
```

No generated account is pre-enrolled or marked as verified human research. Never run `pilot-verify-real` on a judge demo, browser fixture or synthetic wallet. Real interview/recruitment records and a pre-agreed controlled study are required for that operator action. [PILOT_PROTOCOL.md](docs/PILOT_PROTOCOL.md) defines every KPI and limitation. `business_impact_validated` remains false in this prototype.

## 4. Reproduce verification

The app and tests use separate databases. Run from the project root:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.venv\Scripts\python.exe -m unittest discover -q
.venv\Scripts\python.exe scripts/train_cashflow_model.py --evaluate-only
.venv\Scripts\python.exe scripts/evaluate_ai_safety.py --output tmp/infrastructure-qa/ai-safety-final.json
.venv\Scripts\python.exe scripts/provider_contract_demo.py --output tmp/infrastructure-qa/provider-contract-final.json
.venv\Scripts\python.exe scripts/load_test.py --output tmp/infrastructure-qa/load-sqlite-final.json
```

The first command installs the optional pinned training libraries for full model benchmark validation. It is not required for browser serving. Run the following real-browser checks after installing Google Chrome (the existing QA runners use Playwright's Chrome channel):

```powershell
.venv\Scripts\python.exe -m tests.browser_qa
.venv\Scripts\python.exe -m tests.browser_feedback_qa
.venv\Scripts\python.exe -m tests.browser_security_qa
.venv\Scripts\python.exe -m tests.browser_submission_qa
```

These create isolated QA fixtures. Screenshots/results are written under `tmp/`; they never reset the main wallet. The default unittest runner skips the six PostgreSQL-only cases when the disposable fixture URL is absent. A skip is not PostgreSQL validation. To reproduce the separately observed PostgreSQL tests/load using an isolated local cluster:

The preservation test also skips when the historical main SQLite file is absent, as expected in the source-only ZIP. Without the optional ML libraries, offline benchmark reproduction has an additional skip. Report the actual skip reasons in each environment; the counts below describe the reviewed workspace run with its preserved synthetic main file and ML dependencies.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-production.txt
.venv\Scripts\python.exe scripts/postgres_qa.py --download-binaries
```

Gunicorn is omitted on Windows by the dependency marker. The optional Windows binary download is large; the runner can instead use an already-reviewed portable binary directory via `QA_PG_BIN`. It creates a fresh hidden loopback-only PostgreSQL cluster, applies the frozen migrations, preserves migrated constraints during tests, runs the actual HTTP workload and stops/removes the temporary cluster. It does not install a Windows service or touch an existing PostgreSQL cluster. [LOAD_TEST.md](docs/LOAD_TEST.md) explains the fixture guard, binary provenance and exact workload.

### Recorded evidence and scope

Reviewed content-free reports ship under [output/qa/submission](output/qa/submission/), with a manifest recording source hashes and observation dates. Regenerate reports to measure a new environment; do not present the previous measurement as a new run.

| Observed verification on 7 October 2026 | Result | Scope |
| --- | --- | --- |
| Final Phase 2 regression | **335 discovered; 329 passed; 6 PostgreSQL-only skipped; 78.924 seconds** | Includes 10 judge-startup tests, 12 inventory tests and four archive tests; final Bangla/auth/scheduler/favicon copy |
| Prior complete regression baseline | 309 discovered; 303 passed; 6 PostgreSQL-only skipped | SQLite/in-memory isolated suite with ML reproduction dependencies |
| Actual PostgreSQL 18.6 concurrency/recovery | 6 / 6 passed; migration head `20261007_03` | Disposable migrated cluster; 37 app tables plus Alembic and QA guard |
| Real HTTP mixed workload, each database | 240 requests; 8 clients; 10 / 10 invariants | Balance/forecast reads and idempotent future-plan writes; no early debit, duplicate plan or server error |
| SQLite latency/throughput | p50 242.58 ms; p95 1,635.97 ms; p99 2,767.27 ms; 16.80 requests/s | One bounded local measurement |
| PostgreSQL latency/throughput | p50 115.68 ms; p95 184.65 ms; p99 1,005.68 ms; 55.12 requests/s | Same bounded workload; not deployment capacity |
| Existing/planning/privacy responsive checks | 222 passed plus 48 privacy/session flow checks | English/Bangla; existing widths 320–1440; new flows 390/1440 |
| Final isolated judge browser walkthrough | **52 layouts, 64 UI flows and 20 validated exports passed** | English/Bangla at 390/1440; zero page/CSP/overflow errors; four intentionally aborted recipient-lookup console notices; both preserved DB hashes unchanged |
| Extracted source-bundle startup | **CSRF login and seven HTTP 200 review pages; 37-table/120-day fixture; local model/reconciliation passed** | No main database, `.env` or `.venv` included; uses the existing interpreter's installed dependencies. Restart preserves database bytes; inventory selects only the judge file; runtime source hashes match final code |
| Independent signed reference HTTP recovery | Dropped response → UNCERTAIN → SUCCEEDED; exactly one sandbox charge | Local wallet unchanged; official upay remains disconnected |
| Offline multilingual safety corpus | 35 / 35 passed | Finite guards/redaction checks; network calls mocked in application tests |
| Container/gateway artifacts | Static parsing and contract inspection | Docker/Nginx executables were unavailable; Compose runtime is not claimed |

The [submission evidence manifest](output/qa/submission/manifest.json) records the final regression and isolated judge walkthrough separately from historical baseline observations. [RELIABILITY.md](docs/RELIABILITY.md) documents rollback/idempotency; [SECURITY.md](docs/SECURITY.md) and [RESPONSIBLE_AI.md](docs/RESPONSIBLE_AI.md) document the controls and their limits.

## 5. Architecture and database environments

Routes resolve application services through `app/container.py`; services use repository boundaries and SQLAlchemy transactions. Monetary amounts use Decimal / `NUMERIC(12,2)`, fees round to paisa, stored timestamps are UTC and display/report windows use Dhaka calendar dates. SQLite and PostgreSQL implement the same application model with dialect-specific atomic upsert/claim behavior. Local synthetic wallet receipts do not represent bank/provider settlement.

| Database/environment | Location or ownership | Creation, data and lifecycle |
| --- | --- | --- |
| Preserved original household database | `instance/upay_hackathon.db` | Historical 2 October fixture: 18 tables, 4 wallets and 345 transactions; read-only inventory verifies integrity and ledger reconciliation. Phase 2 polish preserves its bytes. Legacy development startup can add missing tables; it has no migration revision until explicit adoption. |
| Judge review SQLite | `instance/judge-demo.db`, optionally another permitted `instance/judge-*.db` | 37 current application tables; fresh complete 120-day synthetic household ledger; date/provenance frozen on first creation; later activity retained. Created by judge launcher, not by production migrations. |
| Original reset backups | `instance/backups/*.db` | Two historical SQLite recovery snapshots; inventories distinguish their own schema/counts. Backups are separate from the live database, ignored by Git and excluded from submission ZIP. |
| Production or managed PostgreSQL | Deployment-owned `DATABASE_URL` | Empty until frozen Alembic upgrades; no demo OTP/funds/seeding/automatic schema creation; TLS and secret/encryption checks enforced. Row data, database name/host and credentials belong to the deployment. |
| Local Docker PostgreSQL lab | Compose `postgres18_data` named volume; database `upayx` | Separate fresh PostgreSQL18 volume. Main SQLite is not mounted. Private local network permits the documented TLS exception; browser deployment requires HTTPS and a registered real OTP adapter. |
| Independent reference-provider ledger | Standalone `instance/reference-provider.sqlite`, or isolated contract runner file | Provider-side reference payment/idempotency ledger; separate from SQLAlchemy's 37 tables. Synthetic, loopback-only; not an official upay database. |
| Unit/browser/load QA | In-memory SQLite or unique fixture subdirectories under `instance/` or ignored `tmp/` | Per-test synthetic fixtures; closed/disposed on completion; preservation checks read original file bytes/schema without changing them. No real research data. |
| Disposable PostgreSQL QA | Fresh guarded `upay_qa_<uuid>` database/temporary cluster | Frozen migrated schema plus QA marker; explicit fixture identity required; temporary cluster removed after verification. Six tests preserve all migration constraints. |

The full schema and safe read-only snapshot inventories appear below. Counts describe the observation time, not a guarantee after judge activity. Raw account, challenge, token, audit and chat values are intentionally excluded from public catalog output. All **columns, types, defaults, keys, constraints, indexes and relationships** are documented.

### Non-application database tables

The reference provider's SQLite database has one table, `sandbox_charges`, created by `ReferenceSandbox` in [provider_contract_demo.py](scripts/provider_contract_demo.py). It has no foreign keys or SQL defaults. `external_id` has SQLite's implicit unique primary-key index; other fields are explicitly `NOT NULL`. The HTTP protocol requires a 32-character hexadecimal external ID, a positive two-decimal BDT amount and a signed request; schema and protocol validation are separate. Its four columns are:

| Column | SQLite type / key | Purpose |
| --- | --- | --- |
| `external_id` | `TEXT PRIMARY KEY` | Independent external payment identity; repeated submissions reuse this key |
| `payload_hash` | `TEXT NOT NULL` | SHA-256 of the canonical authorized request; changed payload for the same key returns 409 |
| `amount` | `TEXT NOT NULL` | Exact decimal string, validated at the HTTP boundary; no floating-point money storage |
| `provider_reference` | `TEXT NOT NULL` | Persisted generated `SANDBOX-…` reference returned on replay/reconciliation |

The provider stores neither a local wallet balance nor a real settlement record. Its contract demo creates a fresh file, proves one charge after lost-response recovery, then closes/removes it. A separately served ledger persists at the operator-selected path. Do not point that server at an application database.

Migrated SQLite/PostgreSQL additionally has Alembic's `alembic_version` table: `version_num VARCHAR(32) NOT NULL`, primary key, holding the applied revision. Disposable PostgreSQL QA adds `_qa_cluster_guard(purpose TEXT NOT NULL)` with no default/key/FK; this content-free marker must match the dedicated fixture purpose before test row resets. Neither table is part of the 37 ORM application tables. Production never contains a QA guard. A development `create_all` judge fixture has neither migration metadata nor this PostgreSQL-only QA marker.

### Inventory and database health

The read-only inventory tool never starts or seeds the default application. It opens SQLite with `mode=ro`, checks integrity/foreign keys, computes counts and safe provenance/reconciliation aggregates and closes connections. It also describes the expected ORM schema using an isolated, unseeded app. Its public JSON excludes raw rows and credential values. See its help for explicit database/output selection:

```powershell
.venv\Scripts\python.exe scripts/database_inventory.py --help
.venv\Scripts\python.exe scripts/database_inventory.py --phase2 phase_2.md
```

The baseline main SHA-256 before and after Phase 2 polish is:

```text
817847e72276de7a484c81cd786d7196fcc6dd96c868ecdd4f1cb62c77bcd53b
```

The root guide embeds the generated catalog below; [docs/DATABASE_CATALOG.md](docs/DATABASE_CATALOG.md) is its standalone source. [output/qa/database-inventory.json](output/qa/database-inventory.json) supplies machine-readable schema/count metadata. Never copy `.env`, live database rows, API secrets or judge session sidecars into a public submission.

Stop web/workers before an inventory run; it refuses active WAL files and aborts if a file changes during inspection. `--phase2` refreshes only this guide's marked catalog block, keeping the login, judge feedback response and other authored sections intact. In a fresh source package without the historical main/backups, it documents only the existing judge database; with no files present it produces schema metadata without creating a database.

### Migrations, backups and recovery

The frozen migration chain is `20261007_01` → `20261007_02` → **`20261007_03`**. The first revision creates 21 baseline/pilot tables, the second adds 15 integration/security/governance tables and indexes, and the third adds `ai_conversation_controls`. The result is 37 application tables plus `alembic_version`. The schema is frozen in migration files; it is not regenerated from today's ORM during deployment.

Fresh PostgreSQL deployment runs `alembic upgrade head` with the intended `DATABASE_URL`. Production readiness checks both schema accessibility and the exact head revision. It rejects SQLite, weak secrets, absent encryption, insecure cookies and enabled demo flags. Do not stamp past an unapplied/incompatible migration. Downgrades that destroy data are disabled.

The preserved historical SQLite database has 19 missing Phase 2 tables. For an intentional migration, stop web/workers, use SQLite's backup API to make a consistent new recovery file, rehearse adoption on a copy, then run explicit `ALEMBIC_ADOPT_EXISTING=1` with the intended file URL. Adoption validates table definitions before accepting each existing table and creates missing ones. SQLite DDL can remain partially applied if a later check fails; restore the tested backup and investigate rather than stamp. The exact commands and recovery precautions are in [DEPLOYMENT.md](docs/DEPLOYMENT.md). Normal judge startup does not require main-database adoption or reset.

For PostgreSQL, use an encrypted/access-controlled `pg_dump -Fc` backup and a restore rehearsal into a separate database. Keep data-encryption read keys and audit-signing keys available for recovered records. An ordinary Compose shutdown preserves its volume; deleting it loses its database. SQLite-to-PostgreSQL row transfer is a separate reviewed migration with identity/type/encryption mapping and ledger/count reconciliation; this repository does not silently import the main SQLite file into production.

### Data rules, privacy and encryption

Financial ledgers, invoices, plans, opening anchors and idempotency claims are durable business records. Financial mutations and ledger audit commit together; unknown provider outcomes stay uncertain until a signed matching result resolves them. The reference provider never silently debits a local wallet. Transaction-monitoring signals prompt review; they are not fraud verdicts or automatic blocking decisions.

Hosted-AI consent and research-export consent are independent. Own-account chat history is bounded to eight messages with seven-day inactivity expiry; AI interaction events have 30-day retention. Clear/erase/revocation uses a persistent generation guard so an in-flight network response cannot recreate erased chat. The content-free guard persists until account deletion and is disclosed/exported. Durable workers perform expiry housekeeping; financial records and prior consented pilot observations follow their stated record/withdrawal policy.

Production requires authenticated field encryption for AI chat, provider biller references and saved idempotency responses. `DATA_ENCRYPTION_KEYS` supports an active write key followed by older read keys for rotation. Keys stay outside the database in a secret store. Disk/database/backups encryption, TLS, restricted database roles and external immutable audit storage are infrastructure controls; application encryption and ORM audit immutability do not replace them. [SECURITY.md](docs/SECURITY.md) specifies TTLs, rate limits, ownership, audit and monitoring boundaries.

## 6. Deployment, configuration and API review

The tested judge demo and the production profile are separate entry points:

| Entry point/configuration | Intended use |
| --- | --- |
| `scripts/judge_demo.py` / `scripts.judge_demo:create_judge_app` | Loopback synthetic judge browser/worker; dedicated database and persisted private fixture key; no real provider or hosted AI |
| `run.py` / `DevelopmentConfig` | Legacy local development; default preserved main SQLite, auto-create/seed compatibility and request-driven due execution |
| `wsgi:app` / `ProductionConfig` | PostgreSQL deployment; strict secrets, encryption, secure cookies, explicit migrations and supervised workers; trusted OTP callable must be registered |

`.env.example` lists configuration names and safe placeholders. No `.env` copy is required for the judge launcher. Production requires a unique ≥32-character `SECRET_KEY`, PostgreSQL `DATABASE_URL` with verified TLS, a Fernet `DATA_ENCRYPTION_KEY`, appropriate separate security/audit keys and private `OBSERVABILITY_TOKEN`. `OTP_DELIVERY_ADAPTER` is a trusted callable registered in deployment code; a missing adapter fails sign-in closed. `PROVIDER_BASE_URL`/signing secret configure only an approved reference environment; the live upay adapter stays disabled without the official contract. Provider/model keys are never judge login credentials.

The [OpenAPI contract](docs/openapi.yaml) covers `/api/v1/balance`, `/financial-health`, `/schedules`, provider intents and signed callbacks. Tokens are issued from the trusted CLI, scoped, hashed, expiring and revocable. Browser cookies cannot authorize bearer API calls. Writes require explicit confirmation, strict JSON and a payload-bound `Idempotency-Key`; matching retries replay the original result and changed payloads return 409. The reference contract demo is the simplest secret-free integration walkthrough.

Production/local-lab artifacts include `Dockerfile`, `compose.yaml`, `deploy/nginx.conf`, `wsgi.py`, `requirements-production.txt` and `migrations/`. [DEPLOYMENT.md](docs/DEPLOYMENT.md) contains secret generation, Compose commands, OTP registration, native Nginx validation, workers, migration/adoption and recovery. Docker/Nginx runtime execution has not been verified in this Windows environment. No public endpoint or live financial deployment is part of this submission.

`/health/live` checks process liveness. `/health/ready` checks the database/worker schema and production migration head. `/internal/metrics` requires the separate observability bearer secret and exposes aggregate queue/retry/heartbeat counts. Request IDs and redacted structured logs support diagnosis without logging request bodies, tokens or personal questions. Review exhausted schedules, stale heartbeats, uncertain/review-required provider intents, readiness failures and database saturation.

## 7. Troubleshooting and submission

| Symptom | Resolution |
| --- | --- |
| PowerShell refuses activation | Use `.venv\Scripts\python.exe` directly as above |
| `ModuleNotFoundError` | Install the requirements with that same executable; ML reproduction uses `requirements-ml.txt` |
| Port already occupied | Start with `--port 5001`; use the printed URL |
| Dashboard Today is empty | Select 30/120 days; seeded history ends yesterday and is preserved on restart |
| Forecast unavailable | Inspect the reason/coverage; a new empty wallet needs 28 completed history days with ordinary spending. Use the main synthetic household for review |
| OTP expired or wrong-code/rate rejection | Request a fresh code and respect the quota window; judge code is `123456` |
| Future plan does not pay | Expected: saving or browsing makes no debit. Wait until due and use the worker or explicit due-processing action |
| Browser QA cannot launch | Install Google Chrome and the project Playwright dependency; app serving itself needs no browser automation package installation step |
| Readiness fails on deployment | Verify migration head, database access and worker tables; do not stamp past a failed upgrade |
| Judge launcher rejects an existing file | Keep the preserved file; use a new permitted `instance/judge-*.db` name rather than overwrite/reset it |
| Hosted AI unavailable in judge demo | Expected local-only configuration; forecast inference still runs locally |

Use [SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) before handoff. Include source, tests, model/governance artifacts, dependencies, migrations, deployment artifacts, this guide, original feedback and reviewed evidence. Exclude `.env`, `.venv`, `.git`, `instance` databases/backups/secret sidecars, temporary QA clusters and downloaded PostgreSQL binaries. Fresh judge startup creates its own synthetic dataset, so a wallet DB is not needed in the source package.

Build the reviewed source/evidence archive:

```powershell
.venv\Scripts\python.exe scripts/build_submission.py
```

The output is [UPAYX_SUBMISSION.zip](output/submission/UPAYX_SUBMISSION.zip). Its `SUBMISSION_MANIFEST.json` records every included file's size and SHA-256. The builder uses an explicit source/model/document/evidence allowlist, excludes runtime data/credentials and produces identical ZIP bytes for identical inputs. Use `--overwrite` to rebuild this archive after an intentional code/document/evidence change. It creates a local artifact; the user submits it to the contest.

The remaining externally dependent acceptance items are the original seventh feedback, representative real-user research and mature controlled impact observations, contracted official upay/SMS/biller integration, a deployed representative capacity/recovery run, native Compose/TLS validation, and an independent penetration/live-model assessment. These are recorded openly; the prototype does not present them as completed or promise a target score.

## 8. Complete database catalog

The following generated section documents every expected application table and the safe observed inventories of the available SQLite databases. Refresh the standalone catalog and this embedded section together when schema or reviewed fixture state changes.

<!-- BEGIN GENERATED DATABASE CATALOG -->

# Database catalog

Generated by `scripts/database_inventory.py` at 2026-10-07T04:30:50.630812+00:00. This is a read-only snapshot of the files listed below; it does not migrate, seed, reset, decrypt or print account records.

The code declares **37 application tables and 240 columns**, with Alembic head `20261007_03`. The inspected main file contains **18 tables** and no Alembic version table. Its missing tables/indexes are reported below. ORM schema and inspected data are distinct evidence.

## Database environments

| Environment | Storage and lifecycle | Evidence / boundary |
| --- | --- | --- |
| Existing local demo | `instance/upay_hackathon.db`; persisted SQLite file | When present/selected, inspected using `mode=ro&immutable=1`, with identical before/after hashes. No upgrade performed. |
| Judge demo | `instance/judge-demo.db`; separately prepared seeded SQLite demonstration | Included if present, using the same read-only/hash checks. The historical main file is preserved. |
| Historical demo backups | `instance/backups/*.db`; snapshots before demo reset | Inspected individually; they are historical schemas/data, not automatically restored. |
| Compose infrastructure lab | PostgreSQL 18 image; named `postgres18_data` volume mounted at `/var/lib/postgresql` | `compose.yaml` runs migrations before web/workers. This inventory does not connect to that volume or claim current row counts. |
| Disposable infrastructure QA | Separate temporary PostgreSQL 18.6 cluster and unique SQLite fixtures under `tmp/infrastructure-qa` | Six PostgreSQL concurrency checks and SQLite/PostgreSQL mixed HTTP load reports in [LOAD_TEST.md](docs/LOAD_TEST.md). QA PostgreSQL cluster was stopped and removed. |
| Independent reference provider | Separate reference sandbox SQLite ledger selected explicitly by its runner | Signed HTTP integration fixture; provider results never debit the local wallet. Provider database is not the main application database or an official Upay connection. |

Only schema and aggregate metrics are published. Account identifiers, mobile/email/name values, password/PIN/OTP values and hashes, bearer tokens, challenges, chat rows and private payment references are excluded. Python defaults below are application-side defaults; **they are not SQL server defaults**. Callable defaults are named without execution. PostgreSQL timestamp types preserve timezone support; SQLite stores application UTC timestamps as `DATETIME`.

## Inspected files

| File | Bytes | Modified (UTC) | Tables | Total rows / application rows | Integrity / FK errors | Unchanged |
| --- | ---: | --- | ---: | --- | ---: | --- |
| `instance/upay_hackathon.db` | 311296 | 2026-10-07T02:27:31.675257+00:00 | 18 | 913 / 913 | ok / 0 | yes |
| `instance/judge-demo.db` | 585728 | 2026-10-07T04:25:56.242994+00:00 | 37 | 905 / 905 | ok / 0 | yes |
| `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db` | 212992 | 2026-10-02T16:52:58.296703+00:00 | 16 | 144 / 144 | ok / 0 | yes |
| `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db` | 311296 | 2026-10-02T16:56:16.571350+00:00 | 18 | 906 / 906 | ok / 0 | yes |

SHA256 `instance/upay_hackathon.db`: `817847e72276de7a484c81cd786d7196fcc6dd96c868ecdd4f1cb62c77bcd53b`. Before and after inspection matched.

SHA256 `instance/judge-demo.db`: `173054504569729d73bab0305b4e2d97da5989427ae2052269c886ad6efdbf66`. Before and after inspection matched.

SHA256 `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db`: `894e265df0982f69b34bde40b0c12480b06f5dd8eba5181b09ba855666ddc74a`. Before and after inspection matched.

SHA256 `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db`: `0ee20c34d61669760be22b20dc3477f4c8719128d69785f3e75a9f3196e74b0f`. Before and after inspection matched.

Filesystem modification dates are observations, not dataset creation dates. Backup filename timestamps are historical naming provenance. SQLite `schema_version` is an internal change counter, not an Alembic migration revision.

## Actual table row counts

| Table | Main | Judge demo | Backup 1 | Backup 2 |
| --- | ---: | ---: | ---: | ---: |
| `ai_consents` | absent | 0 | absent | absent |
| `ai_conversation_controls` | absent | 0 | absent | absent |
| `ai_conversation_retention` | absent | 0 | absent | absent |
| `ai_governance_events` | absent | 0 | absent | absent |
| `api_idempotency` | absent | 0 | absent | absent |
| `api_tokens` | absent | 0 | absent | absent |
| `assistant_conversations` | 4 | 4 | 1 | 4 |
| `demo_datasets` | 1 | 1 | absent | 1 |
| `display_preferences` | 4 | 4 | 1 | 4 |
| `notification_read_receipts` | 333 | 330 | 0 | 330 |
| `notification_read_states` | 4 | 4 | 1 | 4 |
| `pay_later_accounts` | 1 | 1 | 0 | 1 |
| `pay_later_purchases` | 2 | 2 | 0 | 2 |
| `payment_invoices` | 16 | 16 | 0 | 16 |
| `payment_submissions` | 16 | 16 | 0 | 16 |
| `pilot_events` | absent | 0 | absent | absent |
| `pilot_feedback` | absent | 0 | absent | absent |
| `pilot_participants` | absent | 0 | absent | absent |
| `provider_intents` | absent | 0 | absent | absent |
| `provider_outbox` | absent | 0 | absent | absent |
| `provider_webhooks` | absent | 0 | absent | absent |
| `recipient_registrations` | 8 | 8 | 6 | 8 |
| `savings_plans` | 2 | 2 | 0 | 2 |
| `schedule_retries` | absent | 0 | absent | absent |
| `scheduled_payments` | 5 | 5 | 4 | 4 |
| `security_audit_events` | absent | 0 | absent | absent |
| `security_otp_challenges` | absent | 0 | absent | absent |
| `security_rate_buckets` | absent | 0 | absent | absent |
| `security_trusted_sessions` | absent | 0 | absent | absent |
| `transaction_review_flags` | absent | 0 | absent | absent |
| `transactions` | 345 | 342 | 128 | 342 |
| `user_preferences` | 4 | 4 | 0 | 4 |
| `user_profiles` | 4 | 4 | 1 | 4 |
| `users` | 4 | 4 | 2 | 4 |
| `wallet_opening_balances` | 4 | 4 | absent | 4 |
| `wallet_submissions` | 156 | 154 | 0 | 156 |
| `worker_heartbeats` | absent | 0 | absent | absent |

Main: `instance/upay_hackathon.db`.
Judge demo: `instance/judge-demo.db`.
Backup 1: `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db`.
Backup 2: `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db`.

## Schema differences and startup requirements

The inventory command does not modify these files. Development startup normally uses `AUTO_CREATE_SCHEMA=True` and `SEED_DEMO_DATA=True`; do not start it merely to inspect a snapshot. `create_all` can add missing tables but does not add missing indexes on existing tables, alter columns or establish migration provenance. Use the reviewed backup/adoption procedure in [DEPLOYMENT.md](docs/DEPLOYMENT.md) with seeding disabled. Existing schemas require explicit `ALEMBIC_ADOPT_EXISTING=1`; frozen migrations validate their structure. Production requires PostgreSQL and ordinary migrations, with auto-create and demo seeding disabled.

### `instance/upay_hackathon.db`

Migration revision: unrecorded (no `alembic_version` table). Internal SQLite schema counter: 30.

Missing tables: `ai_consents`, `ai_conversation_controls`, `ai_conversation_retention`, `ai_governance_events`, `api_idempotency`, `api_tokens`, `pilot_events`, `pilot_feedback`, `pilot_participants`, `provider_intents`, `provider_outbox`, `provider_webhooks`, `schedule_retries`, `security_audit_events`, `security_otp_challenges`, `security_rate_buckets`, `security_trusted_sessions`, `transaction_review_flags`, `worker_heartbeats`.

Unexpected application tables: none.

`scheduled_payments`: missing_indexes: ["ix_schedules_due_auto_status"].

`transactions`: missing_indexes: ["ix_transactions_user_status_created"].

### `instance/judge-demo.db`

Migration revision: unrecorded (no `alembic_version` table). Internal SQLite schema counter: 77.

Missing tables: none.

Unexpected application tables: none.

Existing table column/constraint/index shapes match the expected SQLite metadata.

### `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db`

Migration revision: unrecorded (no `alembic_version` table). Internal SQLite schema counter: 1.

Missing tables: `ai_consents`, `ai_conversation_controls`, `ai_conversation_retention`, `ai_governance_events`, `api_idempotency`, `api_tokens`, `demo_datasets`, `pilot_events`, `pilot_feedback`, `pilot_participants`, `provider_intents`, `provider_outbox`, `provider_webhooks`, `schedule_retries`, `security_audit_events`, `security_otp_challenges`, `security_rate_buckets`, `security_trusted_sessions`, `transaction_review_flags`, `wallet_opening_balances`, `worker_heartbeats`.

Unexpected application tables: none.

`scheduled_payments`: missing_indexes: ["ix_schedules_due_auto_status"].

`transactions`: missing_indexes: ["ix_transactions_user_status_created"].

### `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db`

Migration revision: unrecorded (no `alembic_version` table). Internal SQLite schema counter: 1.

Missing tables: `ai_consents`, `ai_conversation_controls`, `ai_conversation_retention`, `ai_governance_events`, `api_idempotency`, `api_tokens`, `pilot_events`, `pilot_feedback`, `pilot_participants`, `provider_intents`, `provider_outbox`, `provider_webhooks`, `schedule_retries`, `security_audit_events`, `security_otp_challenges`, `security_rate_buckets`, `security_trusted_sessions`, `transaction_review_flags`, `worker_heartbeats`.

Unexpected application tables: none.

`scheduled_payments`: missing_indexes: ["ix_schedules_due_auto_status"].

`transactions`: missing_indexes: ["ix_transactions_user_status_created"].

## Dataset provenance and balance reconciliation

Reconciliation checks each anchored wallet independently before publishing aggregates: `opening + SUCCESS IN amount − SUCCESS OUT (amount + fee)`. Pending, failed and deferred receipts have no wallet effect. Matching aggregate totals alone do not prove each account reconciles. A historical file without explicit opening anchors is marked unverified.

### `instance/upay_hackathon.db`

| Aggregate | Observed value |
| --- | --- |
| accounts | 4 |
| anchored accounts | 4 |
| unanchored accounts | 0 |
| mismatched anchored accounts | 0 |
| invalid success directions | 0 |
| current balance total bdt | 183962.50 |
| opening balance total bdt | 40450.00 |
| success incoming total bdt | 256850.00 |
| success outgoing total including fees bdt | 113337.50 |
| success outgoing fees total bdt | 337.50 |
| net success change bdt | 143512.50 |
| absolute discrepancy total bdt | 0.00 |
| largest absolute discrepancy bdt | 0.00 |
| fully reconciled | yes |

Date ranges (stored application UTC timestamps):

- `transactions.created_at`: 2026-06-05T02:00:00 to 2026-10-02T10:00:00.
- `users.created_at`: 2026-06-04T18:00:00 to 2026-06-04T18:00:00.
- `scheduled_payments.due_at`: 2026-10-04T18:00:00 to 2026-12-04T18:00:00.
- `wallet_opening_balances.recorded_at`: 2026-06-04T18:00:00 to 2026-06-04T18:00:00.

Dataset: synthetic=yes; generator `household-ledger-v2`; period 2026-06-05 to 2026-10-02; generated 2026-10-02T16:56:16.695669.

Opening sources: {"synthetic opening fixture": 4}.

### `instance/judge-demo.db`

| Aggregate | Observed value |
| --- | --- |
| accounts | 4 |
| anchored accounts | 4 |
| unanchored accounts | 0 |
| mismatched anchored accounts | 0 |
| invalid success directions | 0 |
| current balance total bdt | 185485.00 |
| opening balance total bdt | 40450.00 |
| success incoming total bdt | 247650.00 |
| success outgoing total including fees bdt | 102615.00 |
| success outgoing fees total bdt | 315.00 |
| net success change bdt | 145035.00 |
| absolute discrepancy total bdt | 0.00 |
| largest absolute discrepancy bdt | 0.00 |
| fully reconciled | yes |

Date ranges (stored application UTC timestamps):

- `transactions.created_at`: 2026-06-09T02:00:00 to 2026-10-06T05:00:00.
- `users.created_at`: 2026-06-08T18:00:00 to 2026-06-08T18:00:00.
- `scheduled_payments.due_at`: 2026-10-08T18:00:00 to 2026-12-04T18:00:00.
- `wallet_opening_balances.recorded_at`: 2026-06-08T18:00:00 to 2026-06-08T18:00:00.

Dataset: synthetic=yes; generator `household-ledger-v2`; period 2026-06-09 to 2026-10-06; generated 2026-10-07T04:25:56.143665.

Opening sources: {"synthetic opening fixture": 4}.

### `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db`

| Aggregate | Observed value |
| --- | --- |
| accounts | 2 |
| anchored accounts | 0 |
| unanchored accounts | 2 |
| mismatched anchored accounts | 0 |
| invalid success directions | 0 |
| current balance total bdt | 18510.00 |
| opening balance total bdt | 0.00 |
| success incoming total bdt | 22100.00 |
| success outgoing total including fees bdt | 26370.00 |
| success outgoing fees total bdt | 60.00 |
| net success change bdt | -4270.00 |
| absolute discrepancy total bdt | 0.00 |
| largest absolute discrepancy bdt | 0.00 |
| fully reconciled | no |

Date ranges (stored application UTC timestamps):

- `transactions.created_at`: 2026-06-05T07:15:00 to 2026-10-02T06:30:39.796844.
- `users.created_at`: 2026-10-01T18:50:52.406142 to 2026-10-02T08:02:47.876637.
- `scheduled_payments.due_at`: 2026-11-04T18:00:00 to 2026-12-19T18:00:00.

No explicit `demo_datasets` provenance row/table in this snapshot; synthetic source cannot be established from the schema alone.

### `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db`

| Aggregate | Observed value |
| --- | --- |
| accounts | 4 |
| anchored accounts | 4 |
| unanchored accounts | 0 |
| mismatched anchored accounts | 0 |
| invalid success directions | 0 |
| current balance total bdt | 185662.50 |
| opening balance total bdt | 40450.00 |
| success incoming total bdt | 256850.00 |
| success outgoing total including fees bdt | 111637.50 |
| success outgoing fees total bdt | 337.50 |
| net success change bdt | 145212.50 |
| absolute discrepancy total bdt | 0.00 |
| largest absolute discrepancy bdt | 0.00 |
| fully reconciled | yes |

Date ranges (stored application UTC timestamps):

- `transactions.created_at`: 2026-06-05T02:00:00 to 2026-10-02T10:00:00.
- `users.created_at`: 2026-06-04T18:00:00 to 2026-06-04T18:00:00.
- `scheduled_payments.due_at`: 2026-11-04T18:00:00 to 2026-12-04T18:00:00.
- `wallet_opening_balances.recorded_at`: 2026-06-04T18:00:00 to 2026-06-04T18:00:00.

Dataset: synthetic=yes; generator `household-ledger-v2`; period 2026-06-05 to 2026-10-02; generated 2026-10-02T16:52:58.448769.

Opening sources: {"synthetic opening fixture": 4}.

## Sensitive-field storage observations

The application encrypts new conversation text, API replay payloads and provider biller references when configured keys are available. The following counts inspect only the `enc:v1:` prefix, without printing or decrypting values; a prefix is not cryptographic authentication. Historical demo rows and seeded synthetic legacy fields may remain plaintext. This is field encryption, not full SQLite/database/backup encryption; runtime secrets and key sidecars are excluded from this inventory.

| File | Field | Rows | `enc:v1:` prefix | Other / legacy |
| --- | --- | ---: | ---: | ---: |
| `instance/upay_hackathon.db` | `assistant_conversations.messages` | 4 | 0 | 4 |
| `instance/judge-demo.db` | `assistant_conversations.messages` | 4 | 0 | 4 |
| `instance/judge-demo.db` | `api_idempotency.response_json` | 0 | 0 | 0 |
| `instance/judge-demo.db` | `provider_intents.biller_reference` | 0 | 0 | 0 |
| `instance/backups/upay_hackathon-before-demo-reset-20261002T165258286574Z.db` | `assistant_conversations.messages` | 1 | 0 | 1 |
| `instance/backups/upay_hackathon-before-demo-reset-20261002T165616564537Z.db` | `assistant_conversations.messages` | 4 | 0 | 4 |

## Complete expected application schema

The following is the current ORM contract, not a claim that all tables exist in the main file. The [JSON inventory](output/qa/database-inventory.json) contains every observed SQLite column, FK, index, unique constraint, check and original table DDL for all inspected files, plus expected SQLite/PostgreSQL DDL and source checksums. SQL constraint enforcement and service validation are separate: SQLite does not enforce `VARCHAR` length or `NUMERIC` precision like PostgreSQL; no ORM CHECK constraints are currently declared.

### Wallet and ledger

#### `transactions`

Wallet receipts; only SUCCESS records affect the balance. OUT includes amount plus fee.

Source: [`app/domain/models.py`](app/domain/models.py). Main rows: 345.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `kind` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `direction` | VARCHAR(10) | VARCHAR(10) | no | no | — | — | — |
| `title` | VARCHAR(120) | VARCHAR(120) | no | no | — | — | — |
| `counterparty` | VARCHAR(120) | VARCHAR(120) | yes | no | — | — | — |
| `reference` | VARCHAR(80) | VARCHAR(80) | yes | no | — | — | — |
| `amount` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `fee` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | 0.00 | — | — |
| `status` | VARCHAR(30) | VARCHAR(30) | no | no | SUCCESS | — | — |
| `note` | VARCHAR(255) | VARCHAR(255) | yes | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.models.Transaction.&lt;lambda&gt; | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_transactions_created_at(created_at)`; `ix_transactions_user_id(user_id)`; `ix_transactions_user_status_created(user_id, status, created_at)`.

Checks: none declared in the ORM.

#### `users`

Account identity, password hash, verification and current synthetic wallet balance.

Source: [`app/domain/models.py`](app/domain/models.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `full_name` | VARCHAR(120) | VARCHAR(120) | no | no | — | — | — |
| `mobile` | VARCHAR(20) | VARCHAR(20) | no | no | — | — | — |
| `email` | VARCHAR(120) | VARCHAR(120) | yes | no | — | — | — |
| `password_hash` | VARCHAR(255) | VARCHAR(255) | yes | no | — | — | — |
| `balance` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | 0.00 | — | — |
| `verified` | BOOLEAN | BOOLEAN | no | no | yes | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | callable: app.domain.models.User.&lt;lambda&gt; | — | — |

Primary key: `id`.

Foreign keys: none.

Unique constraints: none.

Indexes: `ix_users_mobile(mobile)` UNIQUE.

Checks: none declared in the ORM.

### Demo provenance

#### `demo_datasets`

Synthetic generator version, covered dates and dataset provenance; no real-user validation implied.

Source: [`app/domain/demo.py`](app/domain/demo.py). Main rows: 1.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `run_key` | VARCHAR(80) | VARCHAR(80) | no | yes | — | — | — |
| `starts_on` | DATE | DATE | no | no | — | — | — |
| `ends_on` | DATE | DATE | no | no | — | — | — |
| `generated_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |
| `generator_version` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `synthetic` | BOOLEAN | BOOLEAN | no | no | yes | — | — |
| `description` | VARCHAR(500) | VARCHAR(500) | no | no | — | — | — |

Primary key: `run_key`.

Foreign keys: none.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `wallet_opening_balances`

Explicit opening balance anchors for exact per-account ledger reconciliation.

Source: [`app/domain/demo.py`](app/domain/demo.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `opening_balance` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `recorded_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |
| `source` | VARCHAR(120) | VARCHAR(120) | no | no | — | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### Payments and scheduling

#### `pay_later_accounts`

Outstanding deferred purchase balance for each synthetic wallet; the service enforces its limit.

Source: [`app/domain/payment_plans.py`](app/domain/payment_plans.py). Main rows: 1.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `outstanding` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | 0 | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `pay_later_purchases`

Merchant invoice purchases, amount due and repayment state.

Source: [`app/domain/payment_plans.py`](app/domain/payment_plans.py). Main rows: 2.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `merchant` | VARCHAR(100) | VARCHAR(100) | no | no | — | — | — |
| `invoice_no` | VARCHAR(60) | VARCHAR(60) | no | no | — | — | — |
| `amount` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `due_on` | DATE | DATE | no | no | — | — | — |
| `status` | VARCHAR(20) | VARCHAR(20) | no | no | PENDING | — | — |
| `purchase_transaction_id` | INTEGER | INTEGER | no | no | — | — | transactions.id |
| `repayment_transaction_id` | INTEGER | INTEGER | yes | no | — | — | transactions.id |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.payment_plans.PayLaterPurchase.&lt;lambda&gt; | — | — |
| `repaid_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |

Primary key: `id`.

Foreign key: `purchase_transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `repayment_transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `purchase_transaction_id`; `repayment_transaction_id`; `user_id, merchant, invoice_no` (uq_pay_later_merchant_invoice).

Indexes: `ix_pay_later_purchases_due_on(due_on)`; `ix_pay_later_purchases_user_id(user_id)`.

Checks: none declared in the ORM.

#### `payment_invoices`

User-owned paid bill/service receipt metadata and unique provider references.

Source: [`app/domain/payment_plans.py`](app/domain/payment_plans.py). Main rows: 16.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `transaction_id` | INTEGER | INTEGER | no | no | — | — | transactions.id |
| `invoice_number` | VARCHAR(90) | VARCHAR(90) | no | no | — | — | — |
| `category` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `provider` | VARCHAR(120) | VARCHAR(120) | no | no | — | — | — |
| `account_reference` | VARCHAR(60) | VARCHAR(60) | no | no | — | — | — |
| `invoice_reference` | VARCHAR(60) | VARCHAR(60) | yes | no | — | — | — |

Primary key: `id`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `invoice_number`; `transaction_id`; `user_id, category, provider, invoice_reference` (uq_payment_invoice_reference).

Indexes: `ix_payment_invoices_user_id(user_id)`.

Checks: none declared in the ORM.

#### `payment_submissions`

User-owned bill payment submission idempotency and receipt linkage.

Source: [`app/domain/payment_plans.py`](app/domain/payment_plans.py). Main rows: 16.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `token` | VARCHAR(32) | VARCHAR(32) | no | yes | — | — | — |
| `transaction_id` | INTEGER | INTEGER | no | no | — | — | transactions.id |

Primary key: `user_id, token`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `recipient_registrations`

Recipient/service registration and payment eligibility checks.

Source: [`app/domain/operations.py`](app/domain/operations.py). Main rows: 8.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `number` | VARCHAR(60) | VARCHAR(60) | no | no | — | — | — |
| `provider` | VARCHAR(120) | VARCHAR(120) | no | no |  | — | — |
| `kind` | VARCHAR(40) | VARCHAR(40) | no | no | ANY | — | — |
| `name` | VARCHAR(120) | VARCHAR(120) | no | no | — | — | — |
| `status` | VARCHAR(30) | VARCHAR(30) | no | no | REGISTERED | — | — |
| `reason` | VARCHAR(255) | VARCHAR(255) | yes | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.operations.RecipientRegistration.&lt;lambda&gt; | — | — |

Primary key: `id`.

Foreign keys: none.

Unique constraints: `number, provider, kind` (uq_recipient_service).

Indexes: `ix_recipient_registrations_number(number)`.

Checks: none declared in the ORM.

#### `savings_plans`

Stored fixed-contribution savings goals and estimated returns; saving a plan does not move money.

Source: [`app/domain/payment_plans.py`](app/domain/payment_plans.py). Main rows: 2.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `name` | VARCHAR(80) | VARCHAR(80) | no | no | — | — | — |
| `monthly_amount` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `months` | INTEGER | INTEGER | no | no | — | — | — |
| `annual_rate` | NUMERIC(5, 4) | NUMERIC(5, 4) | no | no | — | — | — |
| `contribution_total` | NUMERIC(14, 2) | NUMERIC(14, 2) | no | no | — | — | — |
| `estimated_return` | NUMERIC(14, 2) | NUMERIC(14, 2) | no | no | — | — | — |
| `starts_on` | DATE | DATE | no | no | — | — | — |
| `matures_on` | DATE | DATE | no | no | — | — | — |
| `status` | VARCHAR(20) | VARCHAR(20) | no | no | SAVED | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.payment_plans.SavingsPlan.&lt;lambda&gt; | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_savings_plans_user_id(user_id)`.

Checks: none declared in the ORM.

#### `scheduled_payments`

Individual installments, due dates, recurrence, completion and unique linked receipt.

Source: [`app/domain/operations.py`](app/domain/operations.py). Main rows: 5.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `kind` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `recipient_number` | VARCHAR(60) | VARCHAR(60) | no | no | — | — | — |
| `recipient_name` | VARCHAR(120) | VARCHAR(120) | yes | no | — | — | — |
| `provider` | VARCHAR(120) | VARCHAR(120) | no | no |  | — | — |
| `category` | VARCHAR(40) | VARCHAR(40) | no | no |  | — | — |
| `amount` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `note` | VARCHAR(255) | VARCHAR(255) | yes | no | — | — | — |
| `frequency` | VARCHAR(20) | VARCHAR(20) | no | no | ONE_TIME | — | — |
| `auto_pay` | BOOLEAN | BOOLEAN | no | no | yes | — | — |
| `due_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |
| `status` | VARCHAR(30) | VARCHAR(30) | no | no | SCHEDULED | — | — |
| `transaction_id` | INTEGER | INTEGER | yes | no | — | — | transactions.id |
| `recurrence_group` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `seed_key` | VARCHAR(80) | VARCHAR(80) | yes | no | — | — | — |
| `last_error` | VARCHAR(255) | VARCHAR(255) | yes | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.operations.ScheduledPayment.&lt;lambda&gt; | — | — |
| `executed_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |

Primary key: `id`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `seed_key`; `transaction_id`.

Indexes: `ix_scheduled_payments_due_at(due_at)`; `ix_scheduled_payments_status(status)`; `ix_scheduled_payments_user_id(user_id)`; `ix_schedules_due_auto_status(status, auto_pay, due_at)`.

Checks: none declared in the ORM.

#### `wallet_submissions`

Per-user wallet form idempotency and completed transaction link.

Source: [`app/domain/wallet_submissions.py`](app/domain/wallet_submissions.py). Main rows: 156.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `token` | VARCHAR(32) | VARCHAR(32) | no | no | — | — | — |
| `fingerprint` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `transaction_id` | INTEGER | INTEGER | yes | no | — | — | transactions.id |

Primary key: `id`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `user_id, token` (uq_wallet_submission_token).

Indexes: `ix_wallet_submissions_user_id(user_id)`.

Checks: none declared in the ORM.

### Profile and preferences

#### `display_preferences`

Persistent language and theme choices.

Source: [`app/domain/preferences.py`](app/domain/preferences.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `language` | VARCHAR(2) | VARCHAR(2) | no | no | en | — | — |
| `theme` | VARCHAR(6) | VARCHAR(6) | no | no | system | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `user_preferences`

Persistent notification-enabled preference; this setting does not control authentication.

Source: [`app/domain/preferences.py`](app/domain/preferences.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `notifications_enabled` | BOOLEAN | BOOLEAN | no | no | yes | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `user_profiles`

User-owned nickname, address and uploaded photo metadata/content.

Source: [`app/domain/profiles.py`](app/domain/profiles.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `nickname` | VARCHAR(40) | VARCHAR(40) | no | no |  | — | — |
| `address` | VARCHAR(300) | VARCHAR(300) | no | no |  | — | — |
| `photo_data` | BLOB | BYTEA | yes | no | — | — | — |
| `photo_mime` | VARCHAR(30) | VARCHAR(30) | yes | no | — | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### Notifications

#### `notification_read_receipts`

Per-user individual notification acknowledgement keys.

Source: [`app/domain/notifications.py`](app/domain/notifications.py). Main rows: 333.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `transaction_id` | INTEGER | INTEGER | no | yes | — | — | transactions.id |
| `read_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.notifications.NotificationReadReceipt.&lt;lambda&gt; | — | — |

Primary key: `user_id, transaction_id`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `notification_read_states`

Per-user notification read-through timestamp.

Source: [`app/domain/notifications.py`](app/domain/notifications.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `last_read_transaction_id` | INTEGER | INTEGER | no | no | 0 | — | — |
| `updated_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.notifications.NotificationReadState.&lt;lambda&gt; | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### AI privacy and guidance

#### `ai_consents`

Separate, revocable hosted-assistant and model-research purpose consent.

Source: [`app/domain/ai_governance.py`](app/domain/ai_governance.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `purpose` | VARCHAR(30) | VARCHAR(30) | no | yes | — | — | — |
| `policy_version` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `granted_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.ai_governance.utc_now | — | — |
| `revoked_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |

Primary key: `user_id, purpose`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `ai_conversation_controls`

Content-free erasure generation prevents in-flight requests recreating deleted chat.

Source: [`app/domain/ai_governance.py`](app/domain/ai_governance.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `generation` | INTEGER | INTEGER | no | no | 0 | — | — |
| `updated_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.ai_governance.utc_now | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete CASCADE, update NO ACTION.

Unique constraints: none.

Indexes: `ix_ai_conversation_controls_updated_at(updated_at)`.

Checks: none declared in the ORM.

#### `ai_conversation_retention`

Conversation expiry; chat retention is seven days by default.

Source: [`app/domain/ai_governance.py`](app/domain/ai_governance.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `expires_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_ai_conversation_retention_expires_at(expires_at)`.

Checks: none declared in the ORM.

#### `ai_governance_events`

Content-free consent, safety and privacy observations with bounded retention.

Source: [`app/domain/ai_governance.py`](app/domain/ai_governance.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `kind` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `reason` | VARCHAR(60) | VARCHAR(60) | no | no |  | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.ai_governance.utc_now | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_ai_governance_events_created_at(created_at)`; `ix_ai_governance_events_user_id(user_id)`.

Checks: none declared in the ORM.

#### `assistant_conversations`

Bounded conversation content; encrypted when deployment keys are configured.

Source: [`app/domain/assistant.py`](app/domain/assistant.py). Main rows: 4.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `messages` | TEXT | TEXT | no | no | [] | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### Pilot measurement

#### `pilot_events`

Deduplicated task, completion and retention observations; synthetic and real cohorts remain distinct.

Source: [`app/domain/pilot.py`](app/domain/pilot.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | pilot_participants.user_id |
| `kind` | VARCHAR(30) | VARCHAR(30) | no | no | — | — | — |
| `task_key` | VARCHAR(30) | VARCHAR(30) | yes | no | — | — | — |
| `resource_id` | INTEGER | INTEGER | yes | no | — | — | — |
| `task_token` | VARCHAR(32) | VARCHAR(32) | yes | no | — | — | — |
| `dedup_key` | VARCHAR(100) | VARCHAR(100) | no | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.pilot.utc_now | — | — |

Primary key: `id`.

Foreign key: `user_id` → `pilot_participants.user_id`; delete NO ACTION, update NO ACTION.

Unique constraints: `user_id, dedup_key` (uq_pilot_event_dedup).

Indexes: `ix_pilot_events_created_at(created_at)`; `ix_pilot_events_kind(kind)`; `ix_pilot_events_task_token(task_token)`; `ix_pilot_events_user_id(user_id)`.

Checks: none declared in the ORM.

#### `pilot_feedback`

Participant-reported research observations; values are not evidence of controlled uplift.

Source: [`app/domain/pilot.py`](app/domain/pilot.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | pilot_participants.user_id |
| `kind` | VARCHAR(10) | VARCHAR(10) | no | no | RESEARCH | — | — |
| `problem` | VARCHAR(30) | VARCHAR(30) | no | no | — | — | — |
| `usefulness` | INTEGER | INTEGER | yes | no | — | — | — |
| `ease` | INTEGER | INTEGER | yes | no | — | — | — |
| `missed_payments_last_30_days` | INTEGER | INTEGER | yes | no | — | — | — |
| `comment` | VARCHAR(1000) | VARCHAR(1000) | no | no |  | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.pilot.utc_now | — | — |

Primary key: `id`.

Foreign key: `user_id` → `pilot_participants.user_id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_pilot_feedback_user_id(user_id)`.

Checks: none declared in the ORM.

#### `pilot_participants`

Experiment cohort, variant, source classification and research consent.

Source: [`app/domain/pilot.py`](app/domain/pilot.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `user_id` | INTEGER | INTEGER | no | yes | — | — | users.id |
| `data_source` | VARCHAR(10) | VARCHAR(10) | no | no | DEMO | — | — |
| `variant` | VARCHAR(10) | VARCHAR(10) | no | no | — | — | — |
| `verified_real` | BOOLEAN | BOOLEAN | no | no | no | — | — |
| `consent_version` | VARCHAR(30) | VARCHAR(30) | no | no | — | — | — |
| `enrolled_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.pilot.utc_now | — | — |
| `withdrawn_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |

Primary key: `user_id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### Provider and API integration

#### `api_idempotency`

Unique token/key request digest and encrypted response replay cache.

Source: [`app/domain/integration.py`](app/domain/integration.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `token_id` | INTEGER | INTEGER | no | no | — | — | api_tokens.id |
| `key` | VARCHAR(128) | VARCHAR(128) | no | no | — | — | — |
| `request_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `response_json` | TEXT | TEXT | no | no |  | — | — |
| `status_code` | INTEGER | INTEGER | no | no | 201 | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |

Primary key: `id`.

Foreign key: `token_id` → `api_tokens.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `token_id, key` (uq_api_token_idempotency).

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

#### `api_tokens`

Expiring/revocable scoped bearer credential hashes; raw bearer tokens are not stored.

Source: [`app/domain/integration.py`](app/domain/integration.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `name` | VARCHAR(80) | VARCHAR(80) | no | no | — | — | — |
| `secret_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `prefix` | VARCHAR(12) | VARCHAR(12) | no | no | — | — | — |
| `scopes` | TEXT | TEXT | no | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |
| `expires_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |
| `revoked_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `secret_hash`.

Indexes: `ix_api_tokens_user_id(user_id)`.

Checks: none declared in the ORM.

#### `provider_intents`

Explicit provider authorization and status; independent of synthetic wallet money movement.

Source: [`app/domain/integration.py`](app/domain/integration.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | VARCHAR(32) | VARCHAR(32) | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `provider` | VARCHAR(40) | VARCHAR(40) | no | no | reference_sandbox | — | — |
| `amount` | NUMERIC(12, 2) | NUMERIC(12, 2) | no | no | — | — | — |
| `currency` | VARCHAR(3) | VARCHAR(3) | no | no | BDT | — | — |
| `biller_reference` | TEXT | TEXT | no | no | — | — | — |
| `status` | VARCHAR(20) | VARCHAR(20) | no | no | QUEUED | — | — |
| `provider_reference` | VARCHAR(80) | VARCHAR(80) | yes | no | — | — | — |
| `provider_sequence` | INTEGER | INTEGER | no | no | 0 | — | — |
| `authorized_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |
| `updated_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_provider_intents_user_id(user_id)`.

Checks: none declared in the ORM.

#### `provider_outbox`

Durable provider retries, unique intent, availability and competing-worker lease.

Source: [`app/domain/integration.py`](app/domain/integration.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `intent_id` | VARCHAR(32) | VARCHAR(32) | no | no | — | — | provider_intents.id |
| `status` | VARCHAR(20) | VARCHAR(20) | no | no | PENDING | — | — |
| `attempts` | INTEGER | INTEGER | no | no | 0 | — | — |
| `available_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |
| `lease_until` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |
| `lease_token` | VARCHAR(32) | VARCHAR(32) | yes | no | — | — | — |
| `last_error` | VARCHAR(80) | VARCHAR(80) | yes | no | — | — | — |
| `created_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |

Primary key: `id`.

Foreign key: `intent_id` → `provider_intents.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `intent_id`.

Indexes: `ix_provider_outbox_available_at(available_at)`; `ix_provider_outbox_status(status)`.

Checks: none declared in the ORM.

#### `provider_webhooks`

Deduplicated signed provider event IDs and payload hashes.

Source: [`app/domain/integration.py`](app/domain/integration.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `event_id` | VARCHAR(80) | VARCHAR(80) | no | no | — | — | — |
| `payload_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `intent_id` | VARCHAR(32) | VARCHAR(32) | no | no | — | — | provider_intents.id |
| `received_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | callable: app.domain.integration.now_utc | — | — |

Primary key: `id`.

Foreign key: `intent_id` → `provider_intents.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `event_id`.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

### Security and monitoring

#### `security_audit_events`

Signed append-only content-minimized audit events; ORM update/delete blocked.

Source: [`app/domain/security.py`](app/domain/security.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | VARCHAR(32) | VARCHAR(32) | no | yes | — | — | — |
| `created_at` | BIGINT | BIGINT | no | no | — | — | — |
| `request_id` | VARCHAR(32) | VARCHAR(32) | no | no | — | — | — |
| `user_id` | INTEGER | INTEGER | yes | no | — | — | — |
| `action` | VARCHAR(80) | VARCHAR(80) | no | no | — | — | — |
| `result` | VARCHAR(40) | VARCHAR(40) | no | no | — | — | — |
| `details` | TEXT | TEXT | no | no | {} | — | — |
| `signature` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |

Primary key: `id`.

Foreign keys: none.

Unique constraints: none.

Indexes: `ix_security_audit_events_action(action)`; `ix_security_audit_events_created_at(created_at)`; `ix_security_audit_events_request_id(request_id)`; `ix_security_audit_events_user_id(user_id)`.

Checks: none declared in the ORM.

#### `security_otp_challenges`

Hashed, expiring one-use OTP challenges and bounded verification attempts.

Source: [`app/domain/security.py`](app/domain/security.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | VARCHAR(64) | VARCHAR(64) | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `code_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `expires_at` | BIGINT | BIGINT | no | no | — | — | — |
| `attempts` | INTEGER | INTEGER | no | no | 0 | — | — |
| `consumed_at` | BIGINT | BIGINT | yes | no | — | — | — |
| `delivered` | BOOLEAN | BOOLEAN | no | no | no | — | — |

Primary key: `id`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_security_otp_challenges_expires_at(expires_at)`; `ix_security_otp_challenges_user_id(user_id)`.

Checks: none declared in the ORM.

#### `security_rate_buckets`

Shared hashed rate limit keys, windows and expiry across app workers.

Source: [`app/domain/security.py`](app/domain/security.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `key_hash` | VARCHAR(64) | VARCHAR(64) | no | yes | — | — | — |
| `category` | VARCHAR(32) | VARCHAR(32) | no | yes | — | — | — |
| `window_start` | BIGINT | BIGINT | no | yes | — | — | — |
| `hits` | INTEGER | INTEGER | no | no | — | — | — |
| `expires_at` | BIGINT | BIGINT | no | no | — | — | — |

Primary key: `key_hash, category, window_start`.

Foreign keys: none.

Unique constraints: none.

Indexes: `ix_security_rate_buckets_expires_at(expires_at)`.

Checks: none declared in the ORM.

#### `security_trusted_sessions`

Hashed session/device/agent trust, expiry and revocation.

Source: [`app/domain/security.py`](app/domain/security.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `token_hash` | VARCHAR(64) | VARCHAR(64) | no | yes | — | — | — |
| `user_id` | INTEGER | INTEGER | no | no | — | — | users.id |
| `device_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `agent_hash` | VARCHAR(64) | VARCHAR(64) | no | no | — | — | — |
| `created_at` | BIGINT | BIGINT | no | no | — | — | — |
| `expires_at` | BIGINT | BIGINT | no | no | — | — | — |
| `revoked_at` | BIGINT | BIGINT | yes | no | — | — | — |

Primary key: `token_hash`.

Foreign key: `user_id` → `users.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_security_trusted_sessions_expires_at(expires_at)`; `ix_security_trusted_sessions_user_id(user_id)`.

Checks: none declared in the ORM.

#### `transaction_review_flags`

Unique transaction/rule monitoring flags for human review.

Source: [`app/domain/monitoring.py`](app/domain/monitoring.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | INTEGER | INTEGER | no | yes | — | — | — |
| `transaction_id` | INTEGER | INTEGER | no | no | — | — | transactions.id |
| `rule` | VARCHAR(32) | VARCHAR(32) | no | no | — | — | — |
| `status` | VARCHAR(20) | VARCHAR(20) | no | no | OPEN | — | — |
| `created_at` | BIGINT | BIGINT | no | no | — | — | — |

Primary key: `id`.

Foreign key: `transaction_id` → `transactions.id`; delete NO ACTION, update NO ACTION.

Unique constraints: `transaction_id, rule` (uq_transaction_review_rule).

Indexes: `ix_transaction_review_flags_rule(rule)`; `ix_transaction_review_flags_status(status)`; `ix_transaction_review_flags_transaction_id(transaction_id)`.

Checks: none declared in the ORM.

### Durable workers

#### `schedule_retries`

Persistent retry/backoff and exhausted state per scheduled payment.

Source: [`app/domain/runtime.py`](app/domain/runtime.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `schedule_id` | INTEGER | INTEGER | no | yes | — | — | scheduled_payments.id |
| `failures` | INTEGER | INTEGER | no | no | 0 | — | — |
| `next_attempt_at` | DATETIME | TIMESTAMP WITH TIME ZONE | yes | no | — | — | — |
| `last_error_category` | VARCHAR(80) | VARCHAR(80) | yes | no | — | — | — |
| `exhausted` | BOOLEAN | BOOLEAN | no | no | no | — | — |

Primary key: `schedule_id`.

Foreign key: `schedule_id` → `scheduled_payments.id`; delete NO ACTION, update NO ACTION.

Unique constraints: none.

Indexes: `ix_schedule_retries_next_attempt_at(next_attempt_at)`.

Checks: none declared in the ORM.

#### `worker_heartbeats`

Worker role, last observation and completion/failure counts.

Source: [`app/domain/runtime.py`](app/domain/runtime.py). Main rows: table absent.

| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `worker_id` | VARCHAR(80) | VARCHAR(80) | no | yes | — | — | — |
| `role` | VARCHAR(30) | VARCHAR(30) | no | no | — | — | — |
| `seen_at` | DATETIME | TIMESTAMP WITH TIME ZONE | no | no | — | — | — |
| `completed` | INTEGER | INTEGER | no | no | 0 | — | — |
| `failed` | INTEGER | INTEGER | no | no | 0 | — | — |

Primary key: `worker_id`.

Foreign keys: none.

Unique constraints: none.

Indexes: none beyond primary/unique constraint indexes.

Checks: none declared in the ORM.

## Reproduce the inventory

```powershell
.\.venv\Scripts\python.exe scripts\database_inventory.py
```

Defaults inspect the main file if it exists, `instance/judge-demo.db` if present, and all `.db` files directly in `instance/backups`. With no database files present, it produces a complete schema-only catalog and marks counts as not inspected. Use repeatable `--database <workspace-file>` arguments to inspect selected snapshots, for example `--database instance/judge-demo.db`. `--json` and `--markdown` select workspace report destinations. No connection string is accepted or printed. Selected inputs must exist inside the project after path resolution; live WAL/journal files are refused. Connections close in `finally`, and changed hashes/size/mtime abort the report. Run against a quiescent snapshot; this utility is not an online backup tool.

Regenerate an existing submission document's marked catalog without changing its surrounding feedback or scores:

```powershell
.\.venv\Scripts\python.exe scripts\database_inventory.py --phase2 phase_2.md
```

The optional `--phase2` target must already contain exactly one `<!-- BEGIN GENERATED DATABASE CATALOG -->` and one `<!-- END GENERATED DATABASE CATALOG -->` in order. Only content between them is replaced; links are adjusted for the root document. Missing/duplicate/reversed markers fail before report writes.

<!-- END GENERATED DATABASE CATALOG -->
