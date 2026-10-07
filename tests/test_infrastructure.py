"""Migration, fail-closed configuration, durable restart and ciphertext evidence."""

from datetime import datetime, timedelta, timezone
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import os
import shutil
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask
from app import create_app

from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.domain.runtime import ScheduleRetry, WorkerHeartbeat
from app.domain.security import SecurityAuditEvent
from app.extensions import db
from app.services.cashflow_model import load_artifact
from app.services.demo_seed import DEMO_RECIPIENT_MOBILE
from app.services.encryption_service import decrypt_text, encrypt_text, rotate_text
from app.services.schedule_service import create_schedule, scheduling_window
from app.services.worker_service import process_schedules_once
from config import DevelopmentConfig, ProductionConfig, validate_runtime_config
from tests.helpers import AppTestCase

ROOT = Path(__file__).resolve().parents[1]


class CiphertextTests(AppTestCase):
    def test_authenticated_encryption_rotation_and_legacy_gate(self):
        first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        self.app.config["DATA_ENCRYPTION_KEY"] = first
        encrypted = encrypt_text("Private reference 123")
        self.assertTrue(encrypted.startswith("enc:v1:"))
        self.assertNotIn("Private reference", encrypted)
        self.assertEqual(decrypt_text(encrypted), "Private reference 123")
        self.app.config["DATA_ENCRYPTION_KEYS"] = second + "," + first
        rotated = rotate_text(encrypted)
        self.app.config["DATA_ENCRYPTION_KEYS"] = second
        self.assertEqual(decrypt_text(rotated), "Private reference 123")
        with self.assertRaises(InvalidToken):
            decrypt_text(encrypted)
        tampered = rotated[:-8] + "XXXXXXXX"
        with self.assertRaises(InvalidToken):
            decrypt_text(tampered)
        self.app.config["REQUIRE_DATA_ENCRYPTION"] = True
        with self.assertRaisesRegex(ValueError, "legacy"):
            decrypt_text("plaintext legacy data")
        self.app.config["DATA_ENCRYPTION_KEYS"] = ""
        self.app.config["DATA_ENCRYPTION_KEY"] = ""
        with self.assertRaises(ValueError):
            encrypt_text("data")

    def test_unapproved_model_release_is_unavailable(self):
        artifact = load_artifact()
        self.assertEqual(artifact["algorithm"], "random_forest_regressor")
        with patch("app.services.cashflow_model.MANIFEST_PATH") as manifest:
            manifest.read_text.return_value = '{"artifact_sha256":"changed","source":"synthetic training","customer_data_used":false,"approved_for_local_demo_inference":true}'
            with self.assertRaisesRegex(ValueError, "release approval"):
                load_artifact()


class ProductionConfigurationTests(unittest.TestCase):
    def settings(self, **changes):
        app = Flask(__name__)
        app.config.from_object(ProductionConfig)
        app.config.update(SECRET_KEY="unique-test-secret-" + uuid4().hex,
                          SQLALCHEMY_DATABASE_URI="postgresql://qa:qa@127.0.0.1/isolated?sslmode=verify-full",
                          DATA_ENCRYPTION_KEY=Fernet.generate_key().decode())
        app.config.update(changes)
        return app

    def test_production_requires_postgres_tls_encryption_and_separate_demo_profile(self):
        validate_runtime_config(self.settings())  # No connection or schema creation.
        for changes in ({"SECRET_KEY": "short"},
                        {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
                        {"SQLALCHEMY_DATABASE_URI": "postgresql://qa:qa@localhost/isolated"},
                        {"AUTO_CREATE_SCHEMA": True}, {"SEED_DEMO_DATA": True},
                        {"DEMO_OTP_ALLOWED": True}, {"DEMO_BALANCES_ALLOWED": True},
                        {"SESSION_COOKIE_SECURE": False}, {"REQUIRE_TRUSTED_SESSIONS": False},
                        {"REQUIRE_DATA_ENCRYPTION": False},
                        {"SECURITY_HASH_KEY": "weak"}, {"AUDIT_SIGNING_KEY": "weak"},
                        {"DATA_ENCRYPTION_KEY": "", "DATA_ENCRYPTION_KEYS": ""},
                        {"DATA_ENCRYPTION_KEY": "invalid-key", "DATA_ENCRYPTION_KEYS": ""}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                validate_runtime_config(self.settings(**changes))


class DurableWorkerTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = False
        ScheduledPayment.query.delete()
        db.session.commit()
        self.now = datetime.now(timezone.utc)
        self.initial = Decimal("1000.00")

    def plan(self, *, due=True, auto=True):
        start, _ = scheduling_window(self.now)
        payment = create_schedule(self.user_id, {"kind": "SEND_MONEY", "recipient_number": DEMO_RECIPIENT_MOBILE,
            "amount": "100", "frequency": "ONE_TIME", "auto_pay": "1" if auto else "0", "due_date": start.isoformat()}, now=self.now)[0]
        if due:
            payment.due_at = self.now - timedelta(minutes=1)
            db.session.commit()
        return payment.id

    def test_bounded_durable_pass_respects_due_dates_and_restart_dedup(self):
        ids = [self.plan() for _ in range(3)]
        future, manual = self.plan(due=False), self.plan(auto=False)
        result = process_schedules_once(limit=2, now=self.now, worker_id="worker-qa")
        self.assertEqual((result["selected"], result["completed"]), (2, 2))
        # Fresh ORM session represents a worker restart; persisted claims survive.
        db.session.remove()
        result = process_schedules_once(limit=2, now=self.now, worker_id="worker-qa")
        self.assertEqual(result["completed"], 1)
        self.assertEqual(process_schedules_once(now=self.now)["selected"], 0)
        self.assertTrue(all(db.session.get(ScheduledPayment, item).status == "COMPLETED" for item in ids))
        self.assertEqual(db.session.get(ScheduledPayment, future).status, "SCHEDULED")
        self.assertEqual(db.session.get(ScheduledPayment, manual).status, "SCHEDULED")
        self.assertEqual(db.session.get(User, self.user_id).balance, self.initial - 300)
        self.assertEqual(Transaction.query.filter_by(user_id=self.user_id, direction="OUT").count(), 3)
        self.assertEqual(WorkerHeartbeat.query.filter_by(worker_id="worker-qa").count(), 1)

    def test_interruption_rolls_back_money_then_backoff_survives_restart(self):
        identifier = self.plan()
        recipient_id = User.query.filter_by(mobile=DEMO_RECIPIENT_MOBILE).one().id
        recipient_before = db.session.get(User, recipient_id).balance
        with patch("app.services.wallet_service.WalletService._finish", side_effect=RuntimeError("PRIVATE ACCOUNT DETAILS")):
            result = process_schedules_once(now=self.now)
        self.assertEqual(result["retried"], 1)
        self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(db.session.get(User, self.user_id).balance, self.initial)
        self.assertEqual(db.session.get(User, recipient_id).balance, recipient_before)
        retry = db.session.get(ScheduleRetry, identifier)
        self.assertEqual(retry.failures, 1)
        self.assertEqual(retry.last_error_category, "RuntimeError")
        self.assertNotIn("PRIVATE", SecurityAuditEvent.query.filter_by(action="scheduler.interrupted").one().details)
        db.session.remove()
        self.assertEqual(process_schedules_once(now=self.now + timedelta(seconds=29))["selected"], 0)
        recovered = process_schedules_once(now=self.now + timedelta(seconds=31))
        self.assertEqual(recovered["completed"], 1)
        self.assertEqual(db.session.get(User, self.user_id).balance, self.initial - 100)

    def test_poison_job_is_bounded_and_does_not_block_other_due_plans(self):
        poison, good = self.plan(), self.plan()
        from app.services.worker_service import execute_schedule as real_execute
        def selective_failure(owner, identifier, **kwargs):
            if identifier == poison:
                raise OSError("private details")
            return real_execute(owner, identifier, **kwargs)
        self.app.config["WORKER_MAX_ATTEMPTS"] = 2
        with patch("app.services.worker_service.execute_schedule", side_effect=selective_failure):
            result = process_schedules_once(now=self.now)
            self.assertEqual((result["completed"], result["retried"]), (1, 1))
            exhausted = process_schedules_once(now=self.now + timedelta(seconds=31))
        self.assertEqual(exhausted["exhausted"], 1)
        self.assertEqual(db.session.get(ScheduledPayment, good).status, "COMPLETED")
        self.assertEqual(db.session.get(ScheduledPayment, poison).status, "FAILED")
        self.assertTrue(db.session.get(ScheduleRetry, poison).exhausted)
        self.assertEqual(process_schedules_once(now=self.now + timedelta(days=1))["selected"], 0)
        self.assertEqual(Transaction.query.filter_by(user_id=self.user_id).count(), 1)

    def test_health_and_private_metrics_reveal_only_aggregate_state(self):
        self.assertEqual(self.client.get("/health/live").get_json(), {"status": "alive"})
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        self.plan()
        self.assertEqual(self.client.get("/internal/metrics").status_code, 401)
        self.app.config["OBSERVABILITY_TOKEN"] = "qa-metrics-token"
        self.assertEqual(self.client.get("/internal/metrics", headers={"Authorization": "Bearer bad"}).status_code, 401)
        response = self.client.get("/internal/metrics", headers={"Authorization": "Bearer qa-metrics-token"})
        self.assertIn(b"upayx_due_schedules 1", response.data)
        self.assertNotIn(self.user.mobile.encode(), response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])
        db.session.remove()
        WorkerHeartbeat.__table__.drop(db.engine)
        failed = self.client.get("/health/ready")
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.get_json(), {"status": "not_ready"})


class FrozenMigrationTests(unittest.TestCase):
    def setUp(self):
        self.parent = (ROOT / "tmp" / "infrastructure-qa").resolve()
        self.target = self.parent / ("migration-" + uuid4().hex)
        self.target.mkdir(parents=True)
        self.path = self.target / "isolated.db"
        self.environment = patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + self.path.as_posix(),
                                                  "ALEMBIC_ADOPT_EXISTING": "0"})
        self.environment.start()
        self.configuration = AlembicConfig(str(ROOT / "alembic.ini"))
        self.configuration.set_main_option("script_location", str(ROOT / "migrations"))

    def tearDown(self):
        self.environment.stop()
        target = self.target.resolve()
        if target.is_relative_to(self.parent) and target != self.parent:
            shutil.rmtree(target)

    def test_fresh_schema_is_versioned_and_matches_application_metadata(self):
        command.upgrade(self.configuration, "head")
        command.check(self.configuration)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "20261007_03")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0], 0)

    def test_explicit_legacy_adoption_preserves_rows_and_adds_controls(self):
        command.upgrade(self.configuration, "20261007_01")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO users (id,full_name,mobile,balance,verified) VALUES (1,'Migration QA','01711111222',654.32,1)")
            connection.execute("DROP TABLE alembic_version")
        with self.assertRaisesRegex(RuntimeError, "explicit validated adoption"):
            command.upgrade(self.configuration, "head")
        with patch.dict(os.environ, {"ALEMBIC_ADOPT_EXISTING": "1"}):
            command.upgrade(self.configuration, "head")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT balance FROM users WHERE id=1").fetchone()[0], 654.32)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM security_trusted_sessions").fetchone()[0], 0)
        command.check(self.configuration)

    def test_adoption_rejects_incompatible_columns_without_erasing_data(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, full_name TEXT)")
            connection.execute("INSERT INTO users VALUES (1,'Preserve me')")
        with patch.dict(os.environ, {"ALEMBIC_ADOPT_EXISTING": "1"}):
            with self.assertRaisesRegex(RuntimeError, "incompatible"):
                command.upgrade(self.configuration, "head")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT full_name FROM users").fetchone()[0], "Preserve me")

    def test_adoption_after_demo_startup_accepts_existing_control_tables(self):
        configuration = type("AdoptionConfig", (DevelopmentConfig,), {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + self.path.as_posix(),
            "AUTO_CREATE_SCHEMA": True, "SEED_DEMO_DATA": False, "TESTING": True})
        app = create_app(configuration)
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        with patch.dict(os.environ, {"ALEMBIC_ADOPT_EXISTING": "1"}):
            command.upgrade(self.configuration, "head")
        command.check(self.configuration)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "20261007_03")
