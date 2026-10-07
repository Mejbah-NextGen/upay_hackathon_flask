# Prototype concurrency and failure evidence

This work addresses feedback 4 (prototype quality, 13/15): demonstrate important flows under concurrent and failure conditions. The evidence below comes from executable tests on the local demo database. It does not establish live payment-provider reliability or production readiness.

## Reproduce

From the project root:

```powershell
python -m unittest tests.test_reliability -v
python -m unittest tests.test_operations tests.test_payments tests.test_payment_plans tests.test_wallet tests.test_wallet_channels tests.test_payment_validation
```

The first command runs 12 tests. The affected existing suites run 74 tests. Both commands passed after these changes.

The reliability suite creates an isolated, uniquely named **file-backed SQLite database** under `instance`, with no seeded history or real customers. Both wallets are enrolled as demo pilot participants, so measurement hooks run during the same races and rollbacks. Concurrent workers use separate Flask application contexts, ORM sessions and database connections; the tests assert distinct session and connection identities. Barriers pause competing SQL statements after both workers have read the initial state. The database executes the actual claims, debits, inserts, unique constraints, savepoints, commits and rollbacks. Only failure injection and scheduling are controlled by test hooks.

## Demonstrated outcomes

| Scenario | Verified outcome |
| --- | --- |
| Two due-payment runners, separately exercised for Send Money, Mobile Recharge and Bill Payment | Exactly one runner processes each installment; the other returns no new result. One outgoing transaction is stored per installment. Send Money also stores one matching incoming entry. Re-running a completed installment returns its existing result. |
| Two transfers of BDT 750 against a BDT 1,000 wallet | One succeeds, one reports insufficient balance. Sender ends at BDT 250 and recipient at BDT 750, with two matching ledger entries and one reference. |
| Two identical wallet HTTP submissions | Both receive the same receipt redirect. The database contains one submission record and one pair of transfer ledger entries. |
| Cancellation commits before the runner claims the installment | The installment remains cancelled, with no debit or ledger entry. |
| The runner claims the installment before cancellation | Payment completes once and cancellation is rejected; its status and receipt stay consistent. |
| Two runners encounter the same insufficient-funds installment | Exactly one runner records the failed outcome. No debit or ledger entry is stored. |
| A payment rejection is injected after ledger flush, separately for all three schedule kinds | Ledger and balance changes roll back; the installment commits `FAILED` with an explanation, no transaction link and no invoice. Later automatic scans leave it alone. |
| An unexpected schedule failure is injected after balances and ledger entries have been flushed | The entire attempt rolls back, including its `PROCESSING` claim. It remains `SCHEDULED`, with original balances and no receipt. A later retry succeeds once. |
| An unexpected standalone wallet failure is injected after ledger flush | The service immediately rolls back. Even an explicit subsequent caller commit cannot save a partial payment. Retrying succeeds. |
| Two bill requests reuse the same submission token when the wallet funds only one payment | Both return the same transaction ID. There is one debit, invoice and token record; the second request does not falsely report insufficient balance. |
| Two bill requests use the same provider invoice reference | One succeeds and one reports that the invoice is already paid. There is one debit and one invoice. |
| A bill failure is injected after transaction, invoice and token flush | All three records and the debit roll back. The same invoice reference and submission token can safely be retried. |

The tests also assert one transaction observation per successful initiated payment, one Auto Pay outcome per completed/failed installment, no passive-receipt transaction observation for the recipient, and no retained payment-success observations after rollback. Duplicate requests and successful retries do not inflate the measured outcomes.

## Three reproduced bugs and fixes

1. **Standalone wallet failures could leave a payment commit-able.** The regression injected a failure after writes, caught the exception, and committed the session; the sender incorrectly ended at BDT 875. Committed wallet operations now own rollback on every exception. Calls with `commit=False` remain part of their caller's transaction.
2. **A duplicate bill submission could return insufficient balance instead of its existing receipt.** Both concurrent requests missed the initial token query. After the first consumed the available BDT 125, the second failed its debit before reaching the unique token constraint. Bill handling now rolls back the rejected attempt, re-reads committed token/invoice records and resolves that race to the existing receipt or already-paid message.
3. **Failed schedule outcomes could be processed by two runners.** The old executor released its claim with a full rollback before separately marking `FAILED`. A controlled real database race produced processed counts `[1, 1]`. The executor now keeps the outer installment claim and rolls payment writes back through a savepoint. It commits the failed decision while still holding that claim; counts are `[0, 1]`.

## Transaction contract and remaining limits

- The conditional wallet update (`balance >= amount`) is the final authority for available funds; a prior displayed/read balance cannot authorize an overdraft.
- Successful local schedule execution commits the claim, both transfer balances where applicable, receipt link and ledger entries together. A recognised payment rejection commits only the failed outcome. An unexpected exception rolls the entire attempt back for a later retry.
- `commit=False` is a composition contract: the caller must own commit/rollback, and may use a savepoint. Payment services do not destroy that caller's transaction when propagating a failure.
- Failed installments require review and a new plan rather than automatic unlimited retries. Cancelled and completed installments cannot be debited by the due runner.
- These tests exercise two workers on one SQLite database. They are not sustained load tests, PostgreSQL certification, real customer usability research, business-impact results, or external financial settlement evidence.
- The demo has no external provider side effects. A future live integration needs durable provider idempotency, an outbox/reconciliation flow, retry policy and tests for provider timeouts or ambiguous settlement results before making corresponding production claims.
