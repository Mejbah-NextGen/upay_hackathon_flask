# Feedback 5–6 implementation and evidence

The supplied screenshots score scalability/integration at **6.33/10** and
responsible AI/security at **3.33/5**. This update implements the missing
integration and control paths and measures them with isolated synthetic data.
The seventh feedback screenshot is absent; no requirements or score are invented.
Feedback 1–4 remains covered by [the earlier update](FEEDBACK_1_4.md).

## 5. Scalability and integration

| Judge concern | Implemented behavior | Reviewable evidence |
| --- | --- | --- |
| APIs and actual backend integration are unspecified | Versioned bearer API with hashed, scoped, expiring/revocable tokens; strict schemas, ownership and payload-bound idempotency | [OpenAPI](openapi.yaml), [integration guide](INTEGRATION.md), `tests/test_api.py` |
| Provider integration is only a roadmap | Real signed HTTP reference provider, independent ledger, HMAC responses/callbacks, replay checks, leased persistent outbox and reconciliation after unknown outcomes | `scripts/provider_contract_demo.py`; a lost response recovers to one provider charge and leaves the local wallet unchanged |
| SQLite/demo architecture cannot support production claims | Separate PostgreSQL production profile, explicit frozen Alembic migrations, indexed due/history queries, connection pooling and startup rejection of demo persistence/credit | `migrations/versions`, `config.py`, `tests/test_infrastructure.py` |
| Scheduling depends on visits | Durable bounded schedule worker, persistent exponential retry state, failure exhaustion, atomic ledger claims and worker heartbeats; production disables request-driven processing | `app/services/worker_service.py`, worker interruption/restart tests |
| Gateway and observability are missing | Nginx connection/request/payload/time limits, Gunicorn worker configuration, readiness checks, request IDs, redacted structured logs and authenticated aggregate metrics | [deployment guide](DEPLOYMENT.md), `compose.yaml`, `deploy/nginx.conf` |
| No load evidence | Real loopback HTTP mixed read/planning benchmark with concurrent clients, model inference, duplicate writes and post-run integrity assertions; disposable PostgreSQL migration/race runner | [measured workload and limits](LOAD_TEST.md), `scripts/load_test.py`, `scripts/postgres_qa.py` |
| Data pipeline governance is unspecified | Explicit synthetic training source, generator/seeds/checksums, reviewed inference release hash, separate research export consent and no automatic customer training | [AI governance](RESPONSIBLE_AI.md), `app/ml/governance_manifest.json` |

The reference adapter is executable integration evidence, not Bangladesh upay's
official protocol. Live upay is explicitly disabled until the provider supplies
its contract, credentials and approved environment. Provider completion never
silently creates a local wallet debit. New PostgreSQL deployments start empty;
existing SQLite adoption requires a backup, explicit adoption and schema checks.

## 6. Responsible AI and security

| Judge concern | Implemented behavior | Reviewable evidence |
| --- | --- | --- |
| Authentication/device trust lacks depth | Random hashed one-use challenges with delivery, expiry, attempts and replacement controls; production rejects demo codes; expiring browser-bound server sessions and owner-only revocation | `tests/test_security.py`, [security guide](SECURITY.md), `/auth/devices` |
| Multi-worker rate limits are missing | Atomic database-backed IP/account/token quotas, independent of wallet rollback and process restart | Cross-application concurrent quota tests |
| Transaction monitoring and audit are absent | Deduplicated explainable outbound review signals; HMAC-signed append-only application audit, ledger events in the money transaction and separate denial/request audit | `tests/test_transaction_monitoring.py`; audit rollback, tamper and redaction tests |
| Encryption boundaries are undocumented | Authenticated field encryption and rotation for AI chat, provider references and durable response records; production requires keys and rejects legacy plaintext | Ciphertext rotation/tamper tests; [deployment prerequisites](DEPLOYMENT.md) |
| Privacy and consent are vague | Hosted AI off by default; explicit disclosed owner consent; separate research export; scoped download/erase receipts, bounded history and expiry | `tests/test_ai_safety.py`, English/Bangla `/assistant/privacy` |
| Prompt injection/explainability lack evidence | Multilingual adversarial corpus, sensitive-value redaction, constrained provider input/output/actions, no payment tools, source-labelled forecast and training importance limitations | `scripts/evaluate_ai_safety.py`, [model card](MODEL_CARD.md), [AI governance](RESPONSIBLE_AI.md) |

Browser possession binding is not hardware attestation or MFA. Review signals
are not fraud verdicts. Application field encryption is not encrypted database
storage or backups. Audit guards do not stop a privileged database administrator;
restricted roles and an immutable external audit sink remain deployment controls.
Automated negative-path tests and finite injection checks are not an independent
penetration test or a live hosted-model red-team assessment.

## Reproduce the demonstration

Verification on 7 October 2026:

- The historical implementation baseline passed **303** default regression tests. Six PostgreSQL-only tests are
  intentionally skipped by that runner and were executed separately.
- **6** actual PostgreSQL concurrency/recovery tests passed on a disposable
  PostgreSQL 18.6 cluster, migrated to `20261007_03`. Migrated constraints were
  preserved throughout the tests; the cluster was stopped and removed.
- SQLite and PostgreSQL each completed **240 actual HTTP requests with eight
  concurrent clients**, including 60 learned forecasts. All ten integrity
  invariants passed, with no early debit, duplicate plan or server error.
- **222** English/Bangla responsive checks passed across the existing, planning
  and privacy/session interfaces, plus **48** new privacy/security UI flow
  checks. The privacy flows were repeated after the erasure race fix.
- The independent reference HTTP provider recovered a dropped response with
  **one** provider charge and an unchanged local wallet.
- The finite multilingual safety corpus passed **35/35** offline checks. Hosted
  network calls in application tests are mocked; live-model evaluation and an
  independent penetration test remain separate work.

Reviewed content-free reports are checked in under
[output/qa/submission](../output/qa/submission/README.md), with source hashes,
artifact hashes and run dates in the [manifest](../output/qa/submission/manifest.json).
The earlier 303-pass regression observation is labelled a historical baseline;
the manifest identifies the current final-polish suite separately. Raw logs and
credential-bearing operational state are excluded. The source run outputs stay
under ignored `tmp/infrastructure-qa`; the safety corpus result also remains at
`output/qa/ai-safety.json`. Full workload timings and limits are recorded in
[LOAD_TEST.md](LOAD_TEST.md).

The [current final-polish suite](../output/qa/submission/regression-current.json)
has **329 passing tests and six PostgreSQL-only skips out of 335 discovered**.
The [final judge walkthrough](../output/qa/submission/judge-browser.json)
adds 52 responsive checks, 64 actual UI assertions and 20 parsed exports after
the final presentation fixes. The [independent extracted-checkout check](../output/qa/submission/submission-readiness.json)
created a reconciled 37-table fixture without a bundled database or `.env`,
completed CSRF login and seven HTTP 200 pages, and preserved bytes on restart.
Its exact source hashes and reused-interpreter dependency scope are retained;
later document/evidence packaging is not presented as a new runtime run.

1. Run the normal synthetic browser app. Open Settings → Device sessions and
   Privacy settings. Demonstrate independent consent, own-account export,
   erasure receipt and session revocation in English or Bangla.
2. Run `.venv\Scripts\python.exe -m unittest discover -v` against isolated data.
3. Run `.venv\Scripts\python.exe scripts/provider_contract_demo.py`. Show the
   lost response, persisted uncertainty, reconciliation and single provider charge.
4. Run `.venv\Scripts\python.exe scripts/evaluate_ai_safety.py --output output/qa/ai-safety.json`.
5. Run the [HTTP and PostgreSQL measurements](LOAD_TEST.md) and inspect all
   invariants along with latency/status counts. A skipped PostgreSQL suite is
   never PostgreSQL evidence.
6. Follow [deployment verification](DEPLOYMENT.md) on a Docker host. Container
   configuration was parsed here; Docker/Nginx runtime execution is not claimed.

All scripts use isolated QA databases and ports. The normal demo wallet dataset
is preserved. Genuine customer research, mature retention, live settlement,
independent security assessment and production capacity require external trials.
No revised judge score or production readiness is claimed.
