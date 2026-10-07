# Versioned APIs and provider integration

Feedback 5 requested evidence of APIs, payment integrations and scalable execution. The project now supplies an owner-scoped HTTP API, database-backed quotas, atomic payload-bound idempotency, a leased provider outbox, signed callbacks, and an executable HTTP integration with an independent reference-provider ledger. [OpenAPI](openapi.yaml) describes the API contract. PostgreSQL migrations, deployment and load evidence are documented separately in the infrastructure guide.

**The provider is a reference sandbox. It is not the Bangladesh upay service.** Official upay credentials and an official provider contract were not supplied. `UpayAdapter` therefore fails closed. No endpoint from a similarly named overseas company is presented as upay integration. A reference intent never debits the demo wallet, credits its recipients, or creates a local successful wallet receipt. Responses explicitly expose `environment: sandbox` and `wallet_debited: false`.

## Scoped credentials

Issue credentials from the trusted operator CLI; there is no cookie-authenticated token creation endpoint:

```powershell
python -m flask --app run:app api-token issue --user-id 1 --scope balance:read --scope insights:read --scope schedules:read --days 7
python -m flask --app run:app api-token revoke --token-id 1
```

The returned `upx_...` bearer secret is displayed once. Only its SHA-256 digest and short display prefix are stored. Random secrets contain 256 bits of entropy. Tokens expire after at most 30 days and can be revoked immediately. Scopes are explicit: `balance:read`, `insights:read`, `schedules:read`, `schedules:write`, `provider:read`, and `provider:write`. All owner IDs come from the token, never from user-supplied JSON or a session cookie. Browser cookies alone cannot authorize these endpoints. API CSRF exemption applies only to the bearer/HMAC blueprint; the browser's payment and scheduling forms retain CSRF protection.

GET `/api/v1/balance` and `/api/v1/financial-health` expose local, read-only financial planning. The forecast uses the existing local model and respects pilot control assignment. There are no hosted LLM calls or AI payment tools in this API. GET `/api/v1/schedules?limit=20&after=0` returns a bounded, owner-scoped ID cursor. Limits must be 1–100; duplicated or unknown query parameters are rejected.

Every mutation requires an `Idempotency-Key` of 8–128 ASCII letters, digits, underscores or hyphens. Keys bind the canonical body, method, path and token. The unique claim, schedule/intent, encrypted saved response and audit event commit together. Matching retries return the original result; changed payloads return 409. Validation failure rolls back the claim so it can safely be retried. Idempotency records must not be pruned while callers or provider reconciliation can still retry their keys.

JSON bodies are limited to 32 KiB, reject duplicate keys and non-finite JSON numbers, and reject unknown fields. Amounts are decimal strings with at most two decimal places. The response envelope is `data` plus a server-generated `request_id`, or `error: {code, message}` plus `request_id`. `X-Request-ID` matches the envelope. Sensitive responses disable caching. Independent IP and token quotas use a shared database; worker count does not multiply allowances.

## Demonstrate actual HTTP transport and failure recovery

```powershell
python scripts/provider_contract_demo.py --output tmp/infrastructure-qa/provider-contract.json
python -m unittest tests.test_api -v
```

The demo starts two separate HTTP servers on loopback, with separate persisted application and sandbox-provider databases. It submits an authorized intent via HTTP, repeats its idempotency key, and rejects a changed amount. The provider then commits its independent sandbox charge and deliberately drops the response. The worker persists `UNCERTAIN`; a later worker queries signed provider status using the original external ID and reaches `SUCCEEDED`. Assertions require one independent charge, a stable replay result, 409 on the payload conflict, and an unchanged local wallet with no local ledger entries. The report states `real_upay_connected: false`. These are synthetic contract results, not customer adoption, live financial settlement or production capacity evidence.

To run the reference provider separately, set a random `PROVIDER_SIGNING_SECRET` of at least 32 characters in the environment, then run:

```powershell
python scripts/provider_contract_demo.py --serve --port 8091 --database instance/reference-provider.sqlite
```

Configure the application with the same secret and `PROVIDER_BASE_URL=http://127.0.0.1:8091`. Development permits explicitly configured loopback HTTP; the production profile forbids it and requires HTTPS. Redirects are rejected. No request chooses its own upstream URL. The standalone sandbox is loopback-only and intended for synthetic test references.

POST `/api/v1/provider-intents` with bearer scope `provider:write`, an idempotency key and:

```json
{"provider":"reference_sandbox","amount":"75.00","biller_reference":"SYNTHETIC-DESCO-001","confirmed":true}
```

The immediate 202 response means queued. Run `python -m flask --app run:app provider-worker --limit 20` from a supervised worker/timer, then query GET `/api/v1/provider-intents/<id>` with `provider:read`.

For a continuously supervised process use `python -m flask --app wsgi:app provider-worker --watch --interval 5 --limit 20`. The interval accepts 1–60 seconds, batches accept 1–100 jobs, and the default runs one batch. Each batch releases its scoped database session. Unexpected batch faults retain recoverable leases and log only an exception category. A supervisor should restart process exits; the database handles crash recovery.

## Provider protocol and durable state

The reference contract supports POST `/v1/payment-intents` and GET `/v1/payment-intents/<external_id>`. The request contains `external_id`, decimal `amount`, `currency: BDT`, `biller_reference` and explicit authorization. The independent provider atomically deduplicates the external ID, binds it to the complete request hash, and returns `external_id`, `amount`, `currency`, `status`, `sequence` and `provider_reference`. It never trusts an unsigned request.

Both requests and responses carry `X-Provider-Timestamp` and `X-Provider-Signature`. The signature is hex HMAC-SHA256 over `timestamp + "." + method + "." + path + "." + raw_body`, with response method `RESPONSE`. Comparisons are constant time, timestamps have a 300-second acceptance window, and replies are capped at 32 KiB. Result amount, currency and intent ID must match persisted authorization. Authenticating responses prevents an unauthenticated 404 from triggering resubmission of an uncertain request.

POST `/api/v1/provider-webhooks/reference` uses the same HMAC protocol and an event body containing `event_id` plus the result fields. Unique event IDs and raw payload hashes persist replay state across workers. Identical duplicates acknowledge successfully; reuse of an event ID with a changed body is rejected. Lower sequences acknowledge without changing state. Terminal results cannot be reversed by a conflicting newer event. Signed completion can finish a queued, uncertain or review-required job; stale worker results cannot overwrite it.

An equal sequence cannot change the provider status or reference. A status transition requires a higher sequence; the provider reference remains bound once received. An outbox is completed only when the persisted intent is terminal, rather than trusting an incoming event's proposed outcome.

Intent and outbox rows are created in the same transaction. Workers claim jobs through a conditional SQL update and commit a lease before network I/O. No database lock is held while contacting a provider. Expired leases are recoverable after crashes. Every retry reconciles provider status before resubmitting; any submission retains the original external key. Network loss is `UNCERTAIN`, never fabricated success or a definitive payment failure. Exponential backoff is capped at 300 seconds. After the configured attempt budget the job becomes `REVIEW_REQUIRED`, with only a bounded diagnostic category retained. A signed provider result can still resolve it.

An operator can explicitly retry review reconciliation using `python -m flask --app run:app provider-reconcile --intent-id <id>`. This conditionally requeues the same job and key for signed status lookup; it cannot manually declare success or authorize a wallet debit. Biller references and saved idempotency responses use application-field encryption when configured, mandatory in the production profile. Provider result reference IDs remain available for reconciliation. Keys remain in the deployment secret store, outside the database.

Live deployment still requires the official provider contract, licensed operational arrangements, provider-specific authentication, reconciliation/settlement rules, biller test accounts, network/security review and provider certification. The reference adapter establishes a verifiable boundary and failure behavior; it does not claim those external requirements have been completed.
