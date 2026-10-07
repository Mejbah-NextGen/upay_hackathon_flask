# Security and responsible AI controls

Feedback 6 scored 3.33/5. The repository now implements shared rate limiting,
bounded verification challenges, expiring browser sessions, safe audit records,
encryption boundaries and AI consent/evaluation. These are implementation and
automated test results; they do not constitute an independent penetration test,
bank certification, hardware device attestation or a real-money launch approval.

## Authentication and device sessions

The development profile continues to expose `123456` for synthetic accounts.
`ProductionConfig` disables that shared code, demo balances and demo seeding.
Production registration starts at zero balance and remains unverified until a
valid challenge is consumed. A missing/failed delivery adapter fails closed.

Supply `OTP_DELIVERY_ADAPTER` as a trusted application configuration callable:

```python
def deliver_otp(mobile: str, code: str, challenge_id: str) -> bool:
    # Call the contracted, authenticated SMS provider here. Return exactly True
    # only on accepted delivery. Never log the mobile, code or provider payload.
    ...

class DeploymentConfig(ProductionConfig):
    OTP_DELIVERY_ADAPTER = staticmethod(deliver_otp)
```

No Upay/SMS endpoint, SMS delivery or external identity provider is fabricated.
The adapter requires the deployment's actual contracted provider. OTPs are
cryptographically random six-digit values. The database retains an HMAC bound to
the challenge, a five-minute expiry, delivery state and an atomic attempt count.
Five attempts exhaust a challenge; successful verification consumes it once.
Issuing a replacement invalidates earlier challenges. IP and normalized-account
quotas persist independently of application transaction rollbacks. Unknown-account
and unavailable-delivery login responses are generic in production.

Successful sign-in clears and replaces the previous Flask session, revokes its
old server record, and issues two independent random tokens. The signed Flask
cookie contains a session token; a separate HTTP-only `upay_device` cookie binds
the server registry entry to that browser. The server verifies user ownership,
expiry, revocation, device token and user-agent hash on protected requests.
Sessions expire after one hour and logout revokes their server entry, preventing
replay of both cookies. `/auth/devices` permits owner-scoped session revocation.
This is browser possession binding, not hardware attestation; it cannot stop
replay if an attacker steals both cookies and matches the browser user agent.
Production requires HTTPS, Secure/HTTP-only cookies and server validation.

## API and rate boundaries

`rate_limit(key, category, limit=None, window_seconds=None)` performs an atomic
PostgreSQL/SQLite upsert. Multiple web workers share the same quota table; a
process restart and a failed money transaction do not reset counters. Only HMAC
digests of identities/IPs are retained. Limits are fixed-window quotas, with
bounded boundary bursts, rather than a claim of full fraud prevention.

Default quotas are auth 12/minute, money routes 30/minute, assistant 20/minute and
API 60/minute. `RATE_LIMITS` permits deployment tuning; rejected requests return
429 and `Retry-After`. API routes additionally bind quotas to authenticated bearer
tokens. Cookie-only authentication is not accepted by the API. Bearer-token and
signed webhook endpoints use their own authorization instead of a browser CSRF
token; browser money, logout, consent and device-revocation forms retain CSRF.
Keep the proxy-to-application port private. Enable `TRUST_PROXY` only behind the
single trusted proxy whose forwarded headers are configured and overwritten.

The [integration contract](INTEGRATION.md) describes versioned endpoints,
scoped/expiring tokens, replay controls and provider intent processing. A
contract simulator demonstrates interoperability without claiming actual Upay
certification or access to private Upay systems.

`monitor_transaction` stores review-only signals alongside successful outbound
ledger entries. `LARGE_OUTBOUND` defaults to 50,000 BDT and `OUTBOUND_BURST` to
five successful outbound payments within sixty seconds. Failed/inbound entries,
other accounts and older entries are excluded. Thresholds use
`MONITOR_LARGE_AMOUNT_BDT`, `MONITOR_BURST_COUNT` and `MONITOR_BURST_SECONDS`.
The unique transaction/rule constraint deduplicates signals; rollback removes
both the ledger mutation and its signals. Signals contain only an internal
transaction ID, rule, review status and timestamp. They do not block payments or
assert fraud. `flask --app run:app monitor-report` returns counts by rule/status
without account identities or free text. Operators must establish a review and
escalation process before treating these signals as operational monitoring.

## Auditing, encryption and privacy

Every non-static request receives a newly generated `X-Request-ID`. Caller IDs,
raw request bodies, mobile numbers, IP addresses, OTPs, authorization headers,
financial questions and chat text are excluded from request audit/log records.
Audit metadata uses a narrow allowlist of internal identifiers/outcomes. Money
mutation events append in the same transaction as the ledger mutation; request
success/denial/failure events persist separately. Audit rows carry an HMAC
signature and reject ORM update/deletion. `verify_audit_event` detects modified
fields. Database-owner access, SQL bulk updates and deletion are outside that
application guard: deploy a restricted database role and a separate immutable
audit export/sink for independent retention and deletion detection.

`SECRET_KEY` must be generated uniquely; deployments can independently configure
`SECURITY_HASH_KEY` and `AUDIT_SIGNING_KEY`. Changing the security hash key
invalidates outstanding challenges/sessions and quota identities. Retain the
appropriate historical audit signing keys when checking exported older events.

Application text encryption uses authenticated Fernet tokens with an explicit
`enc:v1:` envelope and key rotation through `DATA_ENCRYPTION_KEYS` (newest key
first). Production requires configured encryption; plaintext legacy fields fail
closed and require migration. Assistant conversations and provider biller
references use this boundary. This is field encryption, not whole-database
encryption: managed database disks/backups, remaining account/ledger fields and
transport require infrastructure encryption and access controls. Keys belong in
a deployment secret manager, separate from backups. The [AI governance
guide](RESPONSIBLE_AI.md) documents per-user cloud consent, redaction, retention,
erasure and adversarial evaluation. AI guidance has no authority to move money.

## Browser hardening and observability

Responses include CSP, `nosniff`, frame denial, no-referrer and disabled unused
browser sensor permissions. Executable scripts load from this application's
static files; inline script execution is blocked. Existing inline style
attributes are permitted by the style policy. Dynamic pages and exports use
`private, no-store`. Production adds HSTS. Structured request logs contain only
an endpoint name, request ID, status and elapsed time. Health/metrics and durable
worker status are described in the deployment guide.

The durable scheduler prunes expired quota, challenge and session state hourly;
audit history is preserved. Its operational heartbeats older than seven days are
also removed. `flask --app run:app security-prune` runs security cleanup manually
or from a separate supervisor. Configure deployment-specific audit retention and
immutable exports separately.

## Reproducible verification

```powershell
.venv\Scripts\python.exe -m unittest tests.test_security tests.test_transaction_monitoring tests.test_account tests.test_display_qr -q
```

The security suite verifies challenge expiry, replay, exhaustion and delivery
failure; production demo-code rejection and zero-credit registration; cookie
theft, tampering, user binding, expiry and logout replay; owner-only revocation;
CSRF without a debit; headers/caching/request IDs; immutable, signed, redacted,
transactional auditing; and cross-application quotas under concurrent requests.
These tests exercise negative paths against isolated synthetic data. Run the
documented PostgreSQL concurrency/load checks as deployment evidence and arrange
an authorized independent assessment before processing customer financial data.

Controls follow primary guidance from [Flask security
considerations](https://flask.palletsprojects.com/en/stable/web-security/),
[OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
and [OWASP session
management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
