# Responsible AI and privacy controls

Feedback 6 (3.33 / 5) requested consent, security depth, explainability and
prompt-injection evaluation. These changes add enforceable controls and
reproducible evidence. They do not establish production certification.

## Consent and data paths

Open **Assistant → Privacy & AI** (`/assistant/privacy`). Hosted assistance is
off for every account by default, even when the deployment has a provider key.
Only a CSRF-protected explicit checkbox can grant the versioned
`hosted_assistant` purpose. Neither a question payload nor pilot enrollment can
grant it. A changed policy version requires fresh consent. Local guidance and
the local random forest forecast remain available without external AI sharing.

With consent, the existing provider transport receives a redacted question,
eight bounded server-owned messages and account aggregates. The snapshot is
strictly authenticated-user-scoped; profile fields, recipients, references,
invoice identifiers, transaction notes and merchant details are excluded.
Mobile numbers, email, card-shaped numbers and labelled OTP/PIN/password/CVV
values are redacted before storage and outbound transport. Redaction is
heuristic: the UI explicitly warns that it cannot detect every private detail.
Questions should never contain credentials. Browser-supplied conversation
history is never replayed to the provider.

The API request retains `store: false`. This is an API request option, not a
claim that the provider holds no data under its applicable account policies.
Turning hosted AI off stops new calls and erases the app's chat. Deletion cannot
revoke an already-sent request or remove downloaded copies or provider-held
data. The configured provider's terms and retention must be reviewed before
using customer information.

**Model research** is a separate consent purpose. Its export contains only
daily incoming/outgoing aggregates, a checksum and a governance manifest.
Patterns can still identify a person. Export is user initiated; it never sends
data, starts training or labels it approved for training. The manifest states
`training_approved: false`. No application path automatically trains on wallet
or pilot data. The checked-in model remains synthetic-source-only. An export
must receive a separate purpose/source, minimization, access and retention
review before any reuse.

## Retention and user rights

Chat retains at most eight messages. The default expiry is seven days of
inactivity (`AI_CHAT_RETENTION_DAYS`, bounded to 1–30). A new retention table
tracks expiry without adding columns to existing conversations. Existing chats
without reliable timestamps are erased on policy adoption rather than kept
indefinitely. AI events record outcome categories and reasons, never prompts,
raw errors or account amounts, and expire after 30 days.

Expired records are purged before history/privacy reads. Run the standalone
maintenance command daily to purge dormant users too:

```powershell
.venv\Scripts\python.exe -m flask --app run:app assistant prune-ai-data
```

The production worker also needs its regular retention cleanup enabled. Purge
commits its own transaction and must not run within an in-progress wallet write.
Consent records remain until revoke/erasure because they represent the current
purpose authorization; revocation prevents reuse.

Privacy & AI provides an authenticated, private/no-store JSON download of the
user's account wallet ledger and AI data. Credentials and other accounts are
excluded. **Erase my AI data** deletes that user's AI conversation, retention
row, consent and AI event records and returns a request receipt containing
counts and a random ID. Wallet transactions remain for receipts/reports;
security audit records have their separate operational retention. A per-user
content-free invalidation counter and its update time remain until account
deletion, and are disclosed in the account export. Clear, revoke and erase lock
this separate privacy-control row briefly, invalidate the generation, and remove
the selected records in the same transaction. In-flight hosted and local answers
with the old generation are discarded; neither chat nor staged AI events can
recreate erased data. No wallet row or privacy-control lock is held across
provider network I/O. This endpoint
does not claim to delete the entire wallet account or third-party copies.

## AI containment and explanation

The assistant has no payment tools or write authorities. All action buttons
come from server-owned deterministic guidance and a local navigation allowlist.
User text and hosted answers cannot authorize a debit. Payment forms and
explicit user confirmation remain the only money-movement paths.

The input guard covers instruction override, fake role messages, private-data
requests and external destinations in English, Bangla and romanized Bangla.
Unicode normalization removes selected invisible-character obfuscations.
Provider output is bounded plain text; URLs, HTML/markdown links, secret-shaped
data, requests for OTP/PIN/password, claims of completed payments and provider
tool calls fail closed to the local guide. Currency amounts in hosted text must
match fresh server aggregates or deterministic app calculations. This does not
guarantee every financial statement or unseen adversarial wording is correct.

Forecast UI, model card and offline evaluation disclose the learned method,
synthetic source, prediction horizon, uncertainty and feature contributions.
Feature importance and scenario evidence describe associations, not causal
effects. The forecast is guidance, never a credit eligibility, fraud verdict or
payment decision. Synthetic profile errors do not establish demographic
fairness or accuracy for real Bangladesh customers.

## Encryption and source governance

Existing conversation `messages` values use authenticated field encryption
when `DATA_ENCRYPTION_KEY` / `DATA_ENCRYPTION_KEYS` is configured. New writes are
encrypted; reads decrypt at the boundary. Development without a key deliberately
uses plaintext, while production requires a key and rejects unmigrated legacy
plaintext. Multi-key reads support key rotation. Keys belong in a secret manager,
separate from the database and exports; use the documented rotation/migration
commands before removing an old key. This does not claim that every historical
profile or wallet column has been encrypted. Database volume, backup encryption,
TLS and access policies remain deployment responsibilities.

`app/ml/governance_manifest.json` records the synthetic source approval scope,
dataset and artifact SHA256, generator/version/seeds, no customer-data use and
release review gates. The inference artifact is declarative JSON, not executable
pickle. Runtime artifact integrity checks both the manifest and the reviewed
release hash in inference code; a newly
trained file is not approved merely because its adjacent manifest was edited.
Customer exports are excluded from the synthetic generator pipeline.

## Verification and limits

```powershell
.venv\Scripts\python.exe -m unittest tests.test_assistant tests.test_ai_safety -q
.venv\Scripts\python.exe scripts/evaluate_ai_safety.py --output output/qa/ai-safety.json
```

The safety corpus is checked in at `tests/fixtures/ai_safety_cases.json`; its
SHA256 is included in the JSON report. Current offline result is **35 / 35**
deterministic guard/redaction checks. The assistant/privacy suites include
consent isolation/versioning, CSRF, retention, scoped export/erasure, encrypted
storage, malicious mock output, action-call rejection, fabricated amounts and
no money movement. Hosted network calls are mocked; no real customer data or
provider secrets are used.

These are application regression tests and finite attack cases. They are not
an independent penetration test, live-model adversarial evaluation or proof
against unseen injection, multilingual obfuscation, model drift or human
misinterpretation. Before real financial-data operation, run an independent
assessment, provider-specific live red teaming with approved test data,
customer evaluation, real subgroup checks and incident-response rehearsal.
Review cases whenever prompts, models, sources or provider transport change.

The implementation follows the bounded inputs, constrained outputs,
adversarial tests and human review principles in
[official OpenAI safety guidance](https://developers.openai.com/api/docs/guides/safety-best-practices).
