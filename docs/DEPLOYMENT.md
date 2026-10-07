# Deployment infrastructure and operational verification

The new deployment artifacts provide PostgreSQL persistence, a separate Alembic
migration job, Gunicorn web processes, durable schedule/provider workers and a
bounded Nginx API gateway. They provide an executable infrastructure path, not
production certification or access to real Upay, SMS or banking APIs. Existing
`instance/upay_hackathon.db` data is never mounted into or replaced by Compose.

Docker and Nginx executables were unavailable in the implementation environment.
The YAML, service graph and command contracts were inspected and parsed, but the
container image, Nginx runtime and full Compose stack have not been launched here.
Run the checks below on a host with Docker Engine and current Docker Compose v2.

## Local infrastructure lab

`compose.yaml` exposes only `127.0.0.1:8080`. The database and Gunicorn have no
published ports. PostgreSQL 18 uses a separate Compose-managed `postgres18_data`
volume mounted at `/var/lib/postgresql`; the official image puts PGDATA in a
version-specific subdirectory. This follows the [official PostgreSQL image
layout](https://hub.docker.com/_/postgres).

The local database connection deliberately sets `DATABASE_SSL_REQUIRED=0` inside
the private Docker network. This is a local lab exception only. Secure browser
cookies remain enabled. Use HTTP for local health/API CLI checks; install valid
TLS termination before browser sign-in. The normal synthetic browser demo remains
available with `python run.py` and its separate SQLite database.

Generate unique secrets into the current PowerShell process after installing the
project environment. These commands do not print the generated values:

```powershell
$env:SECRET_KEY = (& .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
$env:POSTGRES_PASSWORD = (& .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
$env:OBSERVABILITY_TOKEN = (& .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
$env:DATA_ENCRYPTION_KEY = (& .venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl.exe --fail http://127.0.0.1:8080/health/ready
docker compose logs --tail 50 migrate scheduler provider-worker
```

Preserve the chosen database password and encryption/signing keys in a local
secret manager for later restarts. A PostgreSQL volume's password is initialized
once; changing the environment variable does not change existing database
credentials. Existing ciphertext requires its original encryption key. Do not
generate replacement secrets for an already initialized volume without a planned
credential/key rotation. Compose requires the secrets instead of embedding
default production passwords. Keep secrets out of commits and image builds.

The startup graph waits for database readiness, runs `alembic upgrade head` once,
then starts the web and both workers. The gateway waits for web readiness.
`service_completed_successfully` makes a failed migration stop dependent services,
as documented by [Docker Compose startup
ordering](https://docs.docker.com/compose/how-tos/startup-order/).

New databases contain no seeded customers and no demo credit. Production browser
authentication stays unavailable until a real trusted OTP adapter is registered.
The provider worker is idle without provider intents. Configure an actual signed
provider endpoint and contracted secret to enable the reference adapter; the
independent contract simulator is separate evidence and does not imply live Upay
access. See [API/provider integration](INTEGRATION.md).

## Gateway and process controls

Gunicorn runs two processes with four threads each. Images run the application as
an unprivileged user with a read-only filesystem, temporary `/tmp`, dropped
capabilities and bounded container log files. PDF fonts include Bengali Noto
fonts. Dependencies are installed from `requirements-production.txt`; browser
binaries are not installed into the server image. Pin approved image digests and
a reviewed dependency lock before a release.

The Nginx configuration limits connection counts, global requests, authentication
requests and API requests. Authentication payloads are bounded at 16 KiB, API
payloads at 64 KiB and other uploads at 6 MiB. Header/body/proxy timeouts are
bounded; request and response buffering protect the backend from slow clients.
The application additionally applies shared database-backed account/IP/token
quotas across workers. Nginx-generated 429/413/timeout responses occur before the
application and may have an Nginx response body instead of the API JSON envelope.
Use status codes as the boundary contract. Application rate failures retain the
documented JSON envelope and `Retry-After`.

Only the trusted Nginx hop supplies forwarding information. It overwrites
`X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` and strips `Forwarded`.
`TRUST_PROXY=1` configures exactly one trusted hop. Do not expose Gunicorn or add
another proxy without reviewing that count and the header chain. The local
gateway accepts localhost/127.0.0.1 hosts; public deployment requires an explicit
approved hostname and rejection of unknown hosts.

Gateway and Gunicorn access logs contain request IDs, statuses and timing; they
exclude IPs, URLs/query strings, credentials and bodies. Gateway error logging is
restricted to critical errors to avoid recording raw request paths. Application
structured logs and transaction audit provide the detailed operation outcomes.
Nginx buffering and timeout choices follow the [Gunicorn deployment
guide](https://gunicorn.org/deploy/) and [official Nginx proxy
documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

When Docker is installed, validate the native gateway syntax with the web running:

```powershell
docker compose exec gateway nginx -t
docker compose run --rm --no-deps migrate alembic current
docker compose exec web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).status)"
```

## Trusted OTP adapter registration

`wsgi.py` deliberately uses `ProductionConfig` without a fabricated SMS provider.
The authentication boundary requires a trusted callable and fails closed when it
is missing. Add a deployment-owned entry point, for example `deployment_wsgi.py`:

```python
from app import create_app
from config import ProductionConfig
from deployment_sms import deliver_otp

class DeploymentConfig(ProductionConfig):
    OTP_DELIVERY_ADAPTER = staticmethod(deliver_otp)

app = create_app(DeploymentConfig)
```

`deliver_otp(mobile, code, challenge_id)` must use the contracted SMS provider,
finite network timeouts, authenticated transport and deployment secrets. It
returns exactly `True` only when delivery is accepted. It must never log the code,
mobile or provider response body. Register the callable before `create_app`.
Keep `DEMO_OTP_ALLOWED=False`; do not introduce a shared production code. Replace
the Gunicorn target and Flask `--app` target with `deployment_wsgi:app` in the
deployment override. This module must be part of the reviewed server image;
untrusted HTTP input must never select an import path or delivery adapter.

## Schema migration and existing SQLite adoption

Fresh PostgreSQL uses `alembic upgrade head` in the one-shot service. The frozen
baseline is `20261007_01`, the infrastructure/governance update is
`20261007_02`, and the erasure-generation control is `20261007_03` (current head).
Application startup never auto-creates production tables. Do not
run `alembic stamp head` to bypass an actual upgrade. The readiness probe checks
the expected migration revision and worker schema.

For an existing SQLite demo, stop its web server and workers. Make a consistent
backup before adopting migrations. From the project root, the following Python
uses SQLite's backup API and creates a new uniquely named file:

```powershell
.venv\Scripts\python.exe -c "import pathlib,sqlite3,uuid; source=pathlib.Path('instance/upay_hackathon.db').resolve(); target=source.with_name('upay_hackathon.pre-feedback-5-6.'+uuid.uuid4().hex+'.db'); reader=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True); writer=sqlite3.connect(target); reader.backup(writer); writer.close(); reader.close(); print(target)"
$taskDbPath = (Resolve-Path -LiteralPath 'instance/upay_hackathon.db').Path.Replace('\', '/')
$env:DATABASE_URL = 'sqlite:///' + $taskDbPath
$env:ALEMBIC_ADOPT_EXISTING = '1'
.venv\Scripts\alembic.exe upgrade head
Remove-Item Env:\ALEMBIC_ADOPT_EXISTING
.venv\Scripts\alembic.exe current
```

`ALEMBIC_ADOPT_EXISTING=1` explicitly permits the frozen migrations to validate
existing column types/bounds/nullability, primary and foreign keys, uniqueness
constraints and existing index definitions as each table is adopted, while
creating missing update tables/indexes. These are per-table checks, not a complete
schema preflight before any DDL. SQLite DDL may remain partially applied when a
later incompatibility fails; test adoption on a backup copy first. It is not a
general permission to accept arbitrary schema drift. On incompatibility, restore
the backup and investigate; do not stamp past the failed check. Remove or restore
the temporary `DATABASE_URL` environment setting after maintenance. Run the
application tests and check ledger/opening-balance reconciliation before
restarting the SQLite demo.

This adoption updates a SQLite database in place. It does not copy customer
records into PostgreSQL. A future SQLite-to-PostgreSQL data transfer requires a
separate reviewed export/import, type conversion, encryption migration, identity
mapping, row-count comparison and ledger reconciliation. The supplied Compose
path starts with a fresh PostgreSQL volume.

For upgrades to an existing Compose lab, first take a tested PostgreSQL backup,
stop the web/workers, build the new image, run the migration job, then recreate
the dependent services and gateway:

```powershell
docker compose stop web scheduler provider-worker gateway
docker compose build
docker compose run --rm --no-deps migrate alembic upgrade head
docker compose up -d --force-recreate web scheduler provider-worker gateway
```

Use PostgreSQL's `pg_dump -Fc` and a restore rehearsal on a separate database for
backups; protect backup files and their encryption keys. Preserve the named
volume during ordinary shutdown. Destructive schema downgrades are disabled;
restore a tested backup for recovery.

## Workers, maintenance and observability

`durable-worker --watch --interval 10 --batch-size 50` processes bounded batches
of persisted schedules. Failed executions receive persisted bounded retries;
exhaustion requires review. Scheduler heartbeats are persisted. Hourly assistant
retention and expired security-state cleanup run in this worker; heartbeat state
older than one week is removed. `provider-worker --watch --interval 5
--limit 20` claims persisted outbox leases and resumes interrupted attempts with
the same external idempotency key. Ambiguous/failed attempts move to review;
`provider-reconcile` can query signed provider status without authorizing a new
debit. Restarting a process retains schedule/retry/outbox state.

Liveness is `/health/live`; schema/database readiness is `/health/ready`.
`/internal/metrics` requires `Authorization: Bearer <OBSERVABILITY_TOKEN>` and
returns aggregate due/retry/heartbeat/review information. Configure monitoring
to alert on stale workers, exhausted retries, review-required provider intents,
queue age, readiness failures and database saturation. A healthcheck in Compose
reports health; it does not itself restart an unhealthy running process.

Run expired security-state cleanup periodically and inspect aggregate review
signals without exposing identities:

```powershell
docker compose run --rm --no-deps scheduler flask --app wsgi:app security-prune
docker compose run --rm --no-deps scheduler flask --app wsgi:app monitor-report
```

## Requirements for an external deployment

Replace the local lab exception with a managed PostgreSQL endpoint and
`DATABASE_SSL_REQUIRED=1`, `sslmode=verify-full`, the correct trusted CA and a
verified hostname. Separate migration-owner credentials from a least-privilege
runtime role. Runtime audit access must allow append/read while denying update
and deletion. Private database networks, encrypted managed disks/backups and
restricted administrative access protect fields beyond the application's
encrypted conversation/reference boundary.

Terminate browser HTTPS at the trusted gateway with a valid certificate, current
TLS 1.2/1.3 configuration and HTTP-to-HTTPS redirects. The gateway must set the
actual `https` scheme after its own verified TLS termination. Keep Secure cookies
and HSTS enabled; do not fake `X-Forwarded-Proto=https` on a publicly accessible
HTTP link. An extra external load balancer changes the trusted proxy topology and
requires a reviewed forwarding/network configuration.

Store secrets in the deployment secret manager, retain encryption keys needed to
restore backups, establish immutable audit exports and a transaction review
process, verify provider authentication/reconciliation, and complete an
authorized independent penetration test before handling customer financial
data. Load/concurrency numbers in the repository are synthetic observations for
the tested host; repeat them against the selected deployment capacity. See
[security controls](SECURITY.md) and [responsible AI](RESPONSIBLE_AI.md).
