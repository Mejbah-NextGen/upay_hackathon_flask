"""PostgreSQL-specific concurrent transactions in an isolated runner cluster.

Skipped unless QA_POSTGRES_URL is set. The URL must identify the marked,
disposable loopback database made by scripts/postgres_qa.py. No user DB is used.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
from threading import Barrier, get_ident
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import event

from app import create_app
from app.blueprints.api.routes import issue_token
from app.container import get_container
from app.domain.integration import ApiIdempotency, ProviderIntent, ProviderOutbox
from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.domain.security import SecurityAuditEvent
from app.extensions import db
from app.services.exceptions import InsufficientBalanceError
from app.services.provider_service import create_intent, process_provider_outbox, utc
from app.services.schedule_service import execute_schedule
from config import DevelopmentConfig
from scripts.load_test import verify_disposable_postgres
from scripts.provider_contract_demo import IsolatedDirectory, ReferenceSandbox


@unittest.skipUnless(os.environ.get("QA_POSTGRES_URL"), "Requires isolated QA PostgreSQL runner")
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        url = os.environ["QA_POSTGRES_URL"]
        verify_disposable_postgres(url)
        class PGConfig(DevelopmentConfig):
            TESTING = True
            DEBUG = False
            SQLALCHEMY_DATABASE_URI = url
            SQLALCHEMY_ENGINE_OPTIONS = {"pool_size": 12, "max_overflow": 12, "pool_pre_ping": True}
            SEED_DEMO_DATA = False
            AUTO_CREATE_SCHEMA = False
            SCHEDULE_AUTO_RUN_ON_REQUEST = False
            ASSISTANT_API_ENABLED = False
            SECURITY_PRODUCTION = False
            REQUIRE_TRUSTED_SESSIONS = False
            SECRET_KEY = "isolated-postgresql-fixture-secret-" + uuid4().hex
            DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
            DATA_ENCRYPTION_KEYS = ""
            REQUIRE_DATA_ENCRYPTION = True
            RATE_LIMITS = {"api": (10000, 60)}
        self.app = create_app(PGConfig)
        self.now = datetime.now(timezone.utc)
        with self.app.app_context():
            # Preserve the migrated PostgreSQL schema and its real constraints.
            # The QA guard was verified before these fixture-only row deletions.
            with db.engine.begin() as connection:
                for table in reversed(db.metadata.sorted_tables):
                    connection.execute(table.delete())
            sender = User(full_name="Synthetic PG Sender", mobile="01766000001", balance=Decimal("1000.00"), verified=True)
            recipient = User(full_name="Synthetic PG Recipient", mobile="01866000002", balance=Decimal("0.00"), verified=True)
            db.session.add_all([sender, recipient])
            db.session.commit()
            self.user_id, self.recipient_id = sender.id, recipient.id
            self.recipient_mobile = recipient.mobile
            self.engine = db.engine
        self.provider = None
        self.directory = None

    def tearDown(self):
        if self.provider:
            self.provider.close()
        if self.directory:
            self.directory.cleanup()
        with self.app.app_context():
            db.session.remove()
            with db.engine.begin() as connection:
                for table in reversed(db.metadata.sorted_tables):
                    connection.execute(table.delete())
            db.engine.dispose()

    def worker(self, action):
        with self.app.app_context():
            backend_pid = db.session.connection().connection.driver_connection.info.backend_pid
            try:
                return action(), backend_pid
            finally:
                db.session.remove()

    def parallel(self, actions):
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(self.worker, action) for action in actions]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len(actions), len({row[1] for row in results}), "Separate PostgreSQL connections are required")
        return [row[0] for row in results]

    @contextmanager
    def simultaneous_writes(self, prefix, workers=2):
        barrier = Barrier(workers, timeout=15)
        seen = set()
        def before_write(connection, cursor, statement, parameters, context, executemany):
            identity = get_ident()
            if statement.casefold().startswith(prefix.casefold()) and identity not in seen:
                seen.add(identity)
                barrier.wait()
        event.listen(self.engine, "before_cursor_execute", before_write)
        try:
            yield
        finally:
            event.remove(self.engine, "before_cursor_execute", before_write)

    def schedule(self, amount="125.00"):
        with self.app.app_context():
            row = ScheduledPayment(user_id=self.user_id, kind="SEND_MONEY", recipient_number=self.recipient_mobile,
                recipient_name="Synthetic PG Recipient", amount=Decimal(amount), provider="", category="",
                frequency="ONE_TIME", auto_pay=True, due_at=self.now-timedelta(seconds=1), recurrence_group=uuid4().hex)
            db.session.add(row)
            db.session.commit()
            return row.id

    def test_concurrent_duplicate_schedule_claim_has_one_debit_and_receipt(self):
        schedule_id = self.schedule()
        def run():
            result = execute_schedule(self.user_id, schedule_id, now=self.now)
            return result.status, result.transaction_id, result.processed_now
        with self.simultaneous_writes("UPDATE scheduled_payments SET status"):
            rows = self.parallel([run, run])
        self.assertEqual(1, sum(row[2] for row in rows))
        self.assertEqual(1, len({row[1] for row in rows}))
        with self.app.app_context():
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("875.00"))
            self.assertEqual(db.session.get(User, self.recipient_id).balance, Decimal("125.00"))
            self.assertEqual(Transaction.query.count(), 2)
            self.assertEqual(SecurityAuditEvent.query.filter_by(action="schedule.execute").count(), 1)

    def test_competing_debits_do_not_overdraw_or_leave_partial_ledger(self):
        def pay():
            try:
                return "paid", get_container().wallet.send_money(self.user_id, self.recipient_mobile, "750.00").id
            except InsufficientBalanceError:
                return "insufficient", None
        with self.simultaneous_writes("UPDATE users SET balance"):
            results = self.parallel([pay, pay])
        self.assertEqual(["insufficient", "paid"], sorted(row[0] for row in results))
        with self.app.app_context():
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("250.00"))
            self.assertEqual(db.session.get(User, self.recipient_id).balance, Decimal("750.00"))
            self.assertEqual(Transaction.query.count(), 2)
            self.assertEqual(SecurityAuditEvent.query.count(), 2)

    def test_failure_after_audit_flush_rolls_back_balances_ledger_and_audit(self):
        with self.app.app_context():
            wallet = get_container().wallet
            finish = wallet._finish
            def fail(commit):
                finish(False)
                raise RuntimeError("synthetic interrupted commit")
            with patch.object(wallet, "_finish", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "synthetic interrupted"):
                    wallet.send_money(self.user_id, self.recipient_mobile, "250.00")
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("1000.00"))
            self.assertEqual(db.session.get(User, self.recipient_id).balance, Decimal("0.00"))
            self.assertEqual(Transaction.query.count(), 0)
            self.assertEqual(SecurityAuditEvent.query.count(), 0)

    def test_api_idempotency_duplicate_parallel_requests_create_one_future_plan(self):
        with self.app.app_context():
            token, secret = issue_token(self.user_id, {"schedules:write"}, name="postgres-test", days=1)
            token_id = token.id
        from app.services.reporting_service import local_datetime
        body = {"kind": "SEND_MONEY", "amount": "25.00", "recipient_number": self.recipient_mobile,
                "due_date": (local_datetime(self.now).date()+timedelta(days=1)).isoformat(), "confirmed": True}
        def request():
            client = self.app.test_client()
            result = client.post("/api/v1/schedules", json=body,
                headers={"Authorization": "Bearer " + secret, "Idempotency-Key": "postgres-shared-key-0001"})
            self.assertEqual(result.status_code, 201, result.json)
            return result.json["data"]["items"][0]["id"]
        with self.simultaneous_writes("INSERT INTO api_idempotency", workers=8):
            ids = self.parallel([request] * 8)
        self.assertEqual(len(set(ids)), 1)
        with self.app.app_context():
            self.assertEqual(ScheduledPayment.query.count(), 1)
            self.assertEqual(ApiIdempotency.query.filter_by(token_id=token_id).count(), 1)
            self.assertEqual(Transaction.query.count(), 0)
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("1000.00"))

    def provider_fixture(self, *, dropped_response=False):
        self.directory = IsolatedDirectory("postgres-provider-")
        self.provider = ReferenceSandbox(Path(self.directory.name) / "provider.sqlite", "synthetic-signing-"+uuid4().hex,
                                         drop_after_commit_once=dropped_response).start()
        self.app.config.update(PROVIDER_BASE_URL=self.provider.url, PROVIDER_SIGNING_SECRET=self.provider.secret,
                               PROVIDER_ALLOW_LOOPBACK_HTTP=True)
        with self.app.app_context():
            intent = create_intent(self.user_id, {"amount": "25.00", "biller_reference": "SYNTHETIC-PG-001", "confirmed": True})
            db.session.commit()
            return intent.id

    def test_provider_outbox_two_workers_claim_once_and_preserve_local_wallet(self):
        intent_id = self.provider_fixture()
        with self.simultaneous_writes("UPDATE provider_outbox SET status"):
            rows = self.parallel([lambda: process_provider_outbox(now=self.now+timedelta(seconds=1))] * 2)
        self.assertEqual(sum(row["claimed"] for row in rows), 1)
        with self.app.app_context():
            self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "SUCCEEDED")
            self.assertEqual(ProviderOutbox.query.one().status, "DONE")
            self.assertEqual(ProviderOutbox.query.one().attempts, 1)
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("1000.00"))
            self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(self.provider.charge_count(), 1)

    def test_expired_provider_lease_reconciles_lost_response_without_double_external_charge(self):
        intent_id = self.provider_fixture(dropped_response=True)
        with self.app.app_context():
            first = process_provider_outbox(now=self.now+timedelta(seconds=1))
            self.assertEqual(first["retrying"], 1)
            job = ProviderOutbox.query.one()
            # Simulate the worker dying after lease commit before reconciliation.
            job.status = "PROCESSING"
            job.lease_token = uuid4().hex
            job.lease_until = self.now-timedelta(seconds=1)
            db.session.commit()
            second = process_provider_outbox(now=self.now+timedelta(seconds=10))
            self.assertEqual(second["completed"], 1)
            self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "SUCCEEDED")
            self.assertEqual(ProviderOutbox.query.one().status, "DONE")
            self.assertEqual(Transaction.query.count(), 0)
            self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("1000.00"))
        self.assertEqual(self.provider.charge_count(), 1)
