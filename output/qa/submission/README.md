# Reviewed judge evidence

These content-free JSON reports preserve measured prototype observations from
7 October 2026. The [provenance manifest](manifest.json) records each reviewed
artifact's SHA256, its source-report SHA256, recording timestamp, scope and
normalization. Raw logs, credential URLs, tokens, device identifiers, customer
questions, runtime databases and downloaded PostgreSQL binaries are excluded.

| Report | Observation | Scope |
| --- | --- | --- |
| [Current final regression](regression-current.json) | 335 discovered; 329 passed; 6 PostgreSQL-only cases skipped; 78.924 seconds | Final code after auth/scheduler/Bangla/favicon corrections; judge, 12 inventory and four packaging cases included. No optional ML or packaging skips. |
| [Regression baseline](regression-baseline.json) | 309 discovered; 303 passed; 6 PostgreSQL cases skipped in the default runner | Historical full suite before final submission polish. The manifest separately identifies the current final suite when available. |
| [Judge fixture and extracted-checkout readiness](submission-readiness.json) | 37 tables, reconciled 120-day ledger, available local model; CSRF login and seven HTTP 200 pages; byte-preserving restart; judge-only inventory | Initial fixture and independent extracted prebundle are separately labelled with independent source hashes. No main DB, `.env` or `.venv` included; the existing interpreter supplied installed dependencies. Exact tested runtime/source hashes still match the workspace. |
| [Final judge browser walkthrough](judge-browser.json) | 52 responsive checks, 64 actual UI assertions and 20 parsed exports; preserved main/judge files unchanged | Chrome EN/BN at 390/1440 after the final presentation fixes; zero walkthrough/page/CSP/overflow errors. Four deliberate offline-recipient abort console notices. |
| [PostgreSQL QA](postgres-qa.json) | PostgreSQL 18.6, migration `20261007_03`, six concurrency/recovery cases passed; disposable cluster stopped and removed | Actual local PostgreSQL evidence, separate from the default runner's skips. 39 tables include the 37 application tables, Alembic version and disposable fixture guard. |
| [SQLite HTTP load](load-sqlite.json) | 240 requests / 8 clients; 60 learned forecast reads; 10/10 integrity invariants | One synthetic user, one local instance, quota raised to 10,000/60s for measurement. |
| [PostgreSQL HTTP load](load-postgres.json) | Same workload; 10/10 integrity invariants | A measured run, not sustained capacity or managed failover validation. |
| [Provider recovery](provider-contract.json) | Dropped response recovered to `SUCCEEDED`, one independent charge, unchanged local wallet | Signed real loopback HTTP reference sandbox. No official upay connection or real settlement. |
| [Model reproduction](model-evaluation.json) | 300 synthetic held-out examples; MAE BDT 2,130.16; empirical coverage 94% | Offline benchmark reproduction; no real-customer evaluation or business uplift. |
| [Existing browser views](browser-base.json) | 170 responsive checks | Automated Chrome on isolated synthetic data. |
| [Focused planning views](browser-feedback.json) | 32 responsive checks plus six recorded planning/pilot flow assertions | Automated English/Bangla planning demonstration. |
| [Privacy/session browser flows](browser-security.json) | 20 responsive checks; 48 flow assertions; zero page/CSP errors | Four expected HTTP 400 resource console notices from negative consent probes are retained as an aggregate count. Hosted network disabled. |
| [Offline AI guard corpus](ai-safety.json) | 35/35 checks | Finite offline regression corpus. Live hosted model and independent penetration testing were not evaluated. |

The original source reports were generated under ignored `tmp` directories;
these reviewed copies are included in source control and the submission ZIP.
Source recording timestamps do not establish an external certification. The
[acceptance checklist](../../../docs/SUBMISSION_CHECKLIST.md) lists the customer,
provider and deployment validation that remains external, as well as the
unsupplied seventh feedback screenshot.

The current regression is distinct from the earlier 303-pass baseline. Its six
skips are PostgreSQL-only cases; their actual earlier PostgreSQL run is a
separately dated/scoped report. The extracted checkout was a preliminary source
bundle with the final runtime code, tested before later documentation/evidence
packaging. Its retained per-file source SHA256s identify exactly what ran; the
subsequent final ZIP is not described as a new runtime or dependency-install run.

Use the archive builder after the final guide and current regression report are
ready. It includes this evidence, the code/tests, all reviewed model artifacts,
deployment configuration and the historical synthetic database PDF. Its own
`SUBMISSION_MANIFEST.json` hashes every included file. ZIP timestamps are fixed
for reproducibility, so they are not observation dates.

```powershell
.venv\Scripts\python.exe scripts/build_submission.py
```

The default archive is `output/submission/UPAYX_SUBMISSION.zip`. An existing ZIP
is preserved unless `--overwrite` is explicitly supplied. Inspect the included
manifest and [phase 2 guide](../../../phase_2.md) before handover. The builder
does not publish or externally submit the project.
