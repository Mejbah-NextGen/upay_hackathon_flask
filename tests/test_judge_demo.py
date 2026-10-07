"""Judge fixture creation/restart and protection of the ordinary wallet file."""

from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from app.domain.models import User
from app.extensions import db
from scripts.judge_demo import (
    DEFAULT_DATABASE, ROOT, completed_demo_date, create_judge_app,
    main, prepare_judge_demo, validated_judge_path,
)
from scripts.provider_contract_demo import IsolatedDirectory


class JudgeDemoTests(unittest.TestCase):
    def setUp(self):
        self.directory = IsolatedDirectory("judge-tests-")
        self.path = Path(self.directory.name) / "judge-review.db"
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        self.directory.cleanup()

    def prepare(self, **kwargs):
        app, report = prepare_judge_demo(self.path, **kwargs)
        self.apps.append(app)
        return app, report

    def test_fresh_reconciled_120_day_fixture_uses_yesterday_and_local_model(self):
        app, report = self.prepare()
        self.assertTrue(report["created"])
        self.assertEqual(report["dataset"]["days"], 120)
        self.assertEqual(report["dataset"]["end_date"], completed_demo_date().isoformat())
        self.assertGreater(report["table_counts"]["transactions"], 300)
        self.assertTrue(report["ledger_reconciled"])
        self.assertTrue(report["model"]["artifact_approved"])
        self.assertTrue(report["model"]["forecast_available"])
        self.assertEqual(report["table_counts"]["pilot_participants"], 0)
        self.assertEqual(report["table_counts"]["ai_consents"], 0)
        self.assertTrue(app.config["WTF_CSRF_ENABLED"])
        self.assertFalse(app.debug)
        self.assertFalse(app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"])

    def test_restart_preserves_every_database_byte_and_ignores_new_seed_date(self):
        app, first = self.prepare(as_of=completed_demo_date() - timedelta(days=1))
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        original = self.path.read_bytes()
        _, restarted = self.prepare(as_of=completed_demo_date())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(restarted["reused_without_reset"])
        self.assertEqual(restarted["dataset"], first["dataset"])
        self.assertEqual(restarted["table_counts"], first["table_counts"])

    def test_restart_preserves_operator_changes_and_runtime_secrets(self):
        app, _ = self.prepare()
        secret = app.config["SECRET_KEY"]
        with app.app_context():
            owner = User.query.filter_by(mobile="01329097775").one()
            owner.full_name = "Synthetic judge review edited name"
            db.session.commit()
        restarted, _ = self.prepare()
        self.assertEqual(restarted.config["SECRET_KEY"], secret)
        with restarted.app_context():
            self.assertEqual(User.query.filter_by(mobile="01329097775").one().full_name, "Synthetic judge review edited name")

    def test_legacy_environment_cannot_route_fixture_or_enable_remote_services(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://dangerous.invalid/original",
                "OPENAI_API_KEY": "legacy-sensitive-key", "DATA_ENCRYPTION_KEY": "invalid-legacy-key",
                "DATA_ENCRYPTION_KEYS": "invalid-rotation-key", "SECRET_KEY": "legacy-secret",
                "PROVIDER_BASE_URL": "https://unapproved.invalid", "PROVIDER_SIGNING_SECRET": "legacy-provider-secret"}):
            app, report = self.prepare()
        self.assertEqual(app.config["OPENAI_API_KEY"], "")
        self.assertEqual(app.config["DATA_ENCRYPTION_KEYS"], "")
        self.assertEqual(app.config["PROVIDER_BASE_URL"], "")
        self.assertNotEqual(app.config["SECRET_KEY"], "legacy-secret")
        self.assertNotIn("legacy", json.dumps(report))
        self.assertEqual(app.config["SESSION_COOKIE_NAME"].split("_")[0], "judge")

    def test_main_database_and_outside_paths_are_rejected_without_opening_them(self):
        for candidate in (ROOT / "instance" / "upay_hackathon.db", ROOT / "outside-judge.db",
                ROOT / "instance" / "backups" / "original.db", "instance/../judge-review.db"):
            with self.subTest(candidate=candidate), patch("scripts.judge_demo.create_app") as factory:
                with self.assertRaises(ValueError):
                    prepare_judge_demo(candidate)
                factory.assert_not_called()
        self.assertEqual(validated_judge_path(DEFAULT_DATABASE), (ROOT / DEFAULT_DATABASE).resolve())

    def test_unrecognized_existing_database_is_not_changed_or_migrated(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE original_records (value TEXT)")
            connection.execute("INSERT INTO original_records VALUES ('preserve')")
            connection.commit()
        original = self.path.read_bytes()
        with patch("scripts.judge_demo.create_app") as factory:
            with self.assertRaises(ValueError):
                self.prepare()
            factory.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name(self.path.name + ".runtime.json").exists())

    def test_hard_link_alias_is_rejected_before_opening_either_file(self):
        original = self.path.with_name("review-source.db")
        original.write_bytes(b"Synthetic hard-link guard fixture")
        try:
            os.link(original, self.path)
        except OSError as exc:
            self.skipTest("This filesystem cannot create a test hard link: " + str(exc))
        with patch("scripts.judge_demo.create_app") as factory:
            with self.assertRaisesRegex(ValueError, "hard-link"):
                prepare_judge_demo(self.path)
            factory.assert_not_called()
        self.assertEqual(original.read_bytes(), b"Synthetic hard-link guard fixture")

    def test_original_wallet_hash_and_schema_survive_fixture_creation_and_restart(self):
        original = ROOT / "instance" / "upay_hackathon.db"
        if not original.exists():
            self.skipTest("No ordinary local wallet exists in this checkout.")
        before_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        with closing(sqlite3.connect("file:" + original.as_posix() + "?mode=ro", uri=True)) as connection:
            before_schema = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        self.prepare()
        self.prepare()
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before_hash)
        with closing(sqlite3.connect("file:" + original.as_posix() + "?mode=ro", uri=True)) as connection:
            self.assertEqual(connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall(), before_schema)

    def test_factory_routes_worker_to_same_fixture_and_future_date_rejected(self):
        app = create_judge_app(str(self.path))
        self.apps.append(app)
        self.assertEqual(app.extensions["judge_demo_report"]["database"], str(self.path))
        self.assertIn("durable-worker", app.cli.commands)
        self.assertEqual(app.test_cli_runner().invoke(args=["durable-worker"]).exit_code, 0)
        with self.assertRaises(ValueError):
            prepare_judge_demo(self.path, as_of=completed_demo_date() + timedelta(days=2))

    def test_check_mode_prints_evidence_without_runtime_secrets(self):
        with patch("builtins.print") as output:
            report = main(["--database", str(self.path), "--check"])
        text = output.call_args.args[0]
        self.assertIn("isolated_synthetic_judge_demo", text)
        self.assertEqual(report["dataset"]["days"], 120)
        runtime = json.loads(self.path.with_name(self.path.name + ".runtime.json").read_text(encoding="utf8"))
        self.assertNotIn(runtime["secret_key"], text)
        self.assertNotIn(runtime["data_encryption_key"], text)
