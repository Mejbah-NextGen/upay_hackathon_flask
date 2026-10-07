# Reproducible infrastructure evidence

Feedback 5 (6.33 / 10) requested evidence of API integration and scalability.
The project now has scoped APIs, durable jobs and disposable database tests.
This document records a bounded local measurement and its practical limits.

## Real HTTP workload

```powershell
.venv\Scripts\python.exe scripts/load_test.py --output tmp/infrastructure-qa/load-sqlite.json
```

The script creates a unique SQLite fixture under the QA workspace and serves the
actual Flask app on a free loopback port with a threaded WSGI server. Eight
concurrent clients make 240 real HTTP requests, split evenly between:

- `GET /api/v1/balance`
- `GET /api/v1/financial-health`
- `POST /api/v1/schedules` with one shared idempotency key
- `POST /api/v1/schedules` with fresh idempotency keys

Every mutation explicitly confirms a synthetic future payment plan. A fixture
scoped bearer token is issued locally and is never printed or written in the
report. The test overrides only its API quota to 10,000 requests per 60 seconds
so quota rejection does not obscure this short measurement. Production limits
remain unchanged. Assistant provider calls and request-driven schedule execution
are disabled in this isolated fixture.

The assertions require all requests to succeed, zero HTTP 5xx/transport failures,
exactly one shared-key plan plus 60 fresh-key plans, matching durable idempotency
records, pending future plans, unchanged sender/recipient balances and no early
new ledger transactions. The fixture includes 28 synthetic historical outflow
receipts; all 60 financial-health reads must produce an available learned
forecast, so the test exercises model inference too. The report contains status counts, p50/p95/p99 latency,
throughput, measured platform and all invariant outcomes. Server, connections
and the temporary SQLite files are closed and removed in `finally`.

Measured on 7 October 2026 in the local Windows/AMD64 environment, Python
3.12.10, 12 logical CPUs:

| Database | Requests / concurrency | Statuses | Throughput | p50 | p95 | p99 | Invariants |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SQLite | 240 / 8 | 120 × 200; 120 × 201 | 16.80 req/s | 242.58 ms | 1,635.97 ms | 2,767.27 ms | 10 / 10 passed |
| PostgreSQL 18.6 | 240 / 8 | 120 × 200; 120 × 201 | 55.12 req/s | 115.68 ms | 184.65 ms | 1,005.68 ms | 10 / 10 passed |

Sources: `tmp/infrastructure-qa/load-sqlite.json` and `load-postgres.json`. These timings are one measured
run, not a capacity guarantee. Repeat on the intended deployment hardware and
report the complete workload and quota settings when comparing results.

## Disposable PostgreSQL validation

```powershell
.venv\Scripts\python.exe scripts/postgres_qa.py --download-binaries
```

The optional download follows the Windows binary archive listed by the official
PostgreSQL website and EDB, with source URL and SHA256 recorded in
`tmp/infrastructure-qa/postgres-binaries-source.json`. Only the `pgsql/bin`,
`pgsql/lib` and `pgsql/share` components are extracted under the project. There
is no installer, registered Windows service or change to an existing cluster.
An already-reviewed portable binary directory can instead be selected with
`QA_PG_BIN`.

The runner creates a fresh cluster in a verified workspace subtree, uses a
random bootstrap password file, binds a free port on `127.0.0.1`, and starts
PostgreSQL in a hidden process. Authentication uses SCRAM; fsync and synchronous
commit remain enabled. The generated password file is removed after init.
Neither the password nor credential-bearing URL enters the report. A unique
`upay_qa_<uuid>` database and an out-of-metadata fixture marker protect the
destructive test setup from accidental use against a user database.

The runner executes the checked-in frozen migrations with `DATABASE_URL` set
only for its isolated subprocess, checks the final migration revision, runs
six actual PostgreSQL tests and repeats the HTTP workload against the marked
database. Fixture reset deletes rows in dependency order and preserves the
migrated schema and its constraints; tests never replace it with `create_all`.
The tests use separate connections and barriers at competing SQL
writes to exercise:

- Concurrent duplicate scheduled payment claims: one debit and one receipt.
- Competing wallet debits: no overdraft or partial ledger.
- Failure after ledger/audit flush: balances, ledger and audit roll back together.
- Eight parallel API retries: one future plan and one durable response record.
- Two provider outbox workers: one lease and one independent sandbox charge.
- Lost provider response and expired lease: status reconciliation without a second charge.

The independent signed reference sandbox uses its own ledger and real loopback
HTTP. Its completion does not debit the local wallet and is not an official
upay integration. The temporary PostgreSQL cluster is stopped and removed in
`finally`; portable binaries and content-free measurement reports remain for
repeatable verification.

On 7 October 2026 the actual PostgreSQL 18.6 run applied revision
`20261007_03`, verified 39 tables including the Alembic version and disposable
fixture guard, passed all six concurrent transaction tests, and passed all ten
HTTP workload invariants. The temporary cluster was stopped and removed.
Portable archive SHA256:
`e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2`.

Artifacts are `postgres-qa.json`, `postgres-migration.log`, `postgres-tests.log`
and `load-postgres.json` under `tmp/infrastructure-qa`. The default unit suite
skips `tests.test_postgres` when its isolated fixture URL is absent; a skipped
test must never be reported as PostgreSQL validation.

## Scope and remaining validation

These tests measure one local instance, one fixture user and a short mixed
read/planning workload. They do not measure managed PostgreSQL failover,
distributed worker crashes, sustained multi-tenant production traffic,
network/provider SLAs or real upay settlement. Real upay access still needs its
official provider contract, credentials and approved integration environment.
Run sustained representative load and recovery tests on the deployment before
claiming production readiness.

The binary-source and startup workflow follows the official
[PostgreSQL Windows downloads](https://www.postgresql.org/download/windows/),
[initdb](https://www.postgresql.org/docs/18/app-initdb.html) and
[pg_ctl](https://www.postgresql.org/docs/18/app-pg-ctl.html) documentation.
