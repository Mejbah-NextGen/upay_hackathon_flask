"""Read-only catalog evidence: byte preservation, privacy, schema and cleanup."""

import json
from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import database_inventory as inventory


class DatabaseInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = inventory.expected_schema()

    def setUp(self):
        self.directory = inventory.ROOT / "tmp" / "inventory-tests" / uuid4().hex
        self.directory.mkdir(parents=True)
        self.database = self.directory / "snapshot.db"
        self.secret = "Private customer secret 01988888888 user@example.invalid"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript("""
                CREATE TABLE users(id INTEGER PRIMARY KEY, balance NUMERIC(12,2) NOT NULL,
                    full_name TEXT, mobile TEXT, password_hash TEXT, created_at DATETIME);
                CREATE TABLE transactions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    amount NUMERIC(12,2) NOT NULL, fee NUMERIC(12,2) NOT NULL, direction TEXT NOT NULL,
                    status TEXT NOT NULL, created_at DATETIME, CHECK(amount >= 0 AND (fee >= 0)));
                CREATE TABLE wallet_opening_balances(user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    opening_balance NUMERIC(12,2) NOT NULL, recorded_at DATETIME, source TEXT);
                CREATE TABLE assistant_conversations(user_id INTEGER PRIMARY KEY REFERENCES users(id), messages TEXT);
                CREATE UNIQUE INDEX ux_test_mobile ON users(mobile);
                CREATE TABLE demo_datasets(starts_on DATE,ends_on DATE,generated_at DATETIME,
                    generator_version TEXT,synthetic BOOLEAN);
            """)
            connection.execute("INSERT INTO users VALUES(1,155,?,?,?,?)", (self.secret, "01988888888", "not-a-public-password-hash", "2026-10-01 00:00:00"))
            connection.execute("INSERT INTO transactions VALUES(1,1,100,0,'IN','SUCCESS','2026-10-01 12:00:00')")
            connection.execute("INSERT INTO transactions VALUES(2,1,40,5,'OUT','SUCCESS','2026-10-02 12:00:00')")
            connection.execute("INSERT INTO transactions VALUES(3,1,999,0,'OUT','PENDING','2026-10-03 12:00:00')")
            connection.execute("INSERT INTO wallet_opening_balances VALUES(1,100,'2026-09-30 00:00:00',?)", (self.secret,))
            connection.execute("INSERT INTO assistant_conversations VALUES(1,?)", (self.secret,))
            connection.execute("INSERT INTO demo_datasets VALUES('2026-10-01','2026-10-03','2026-10-03 13:00:00',?,1)", ("01988888888",))
            connection.commit()

    def tearDown(self):
        # Every fixture path is resolved inside this owned UUID directory.
        self.assertTrue(self.directory.resolve().is_relative_to(inventory.ROOT / "tmp" / "inventory-tests"))
        shutil.rmtree(self.directory)

    def test_inventory_preserves_bytes_mtime_sidecars_and_excludes_record_content(self):
        before = self.database.read_bytes()
        before_mtime = self.database.stat().st_mtime_ns
        files_before = sorted(path.name for path in self.directory.iterdir())
        result = inventory.inspect_database(self.database, self.expected)
        serialized = json.dumps(result)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.database.stat().st_mtime_ns, before_mtime)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), files_before)
        self.assertEqual(result["sha256_before"], result["sha256_after"])
        self.assertEqual(result["integrity_check"], "ok")
        self.assertEqual(result["foreign_key_violation_count"], 0)
        self.assertEqual(result["tables"]["transactions"]["row_count"], 3)
        self.assertEqual(result["total_rows"], 7)
        for secret in (self.secret, "01988888888", "user@example.invalid", "not-a-public-password-hash"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(result["provenance"]["opening_anchor_sources"], {"other source (label withheld)": 1})
        self.assertEqual(result["provenance"]["synthetic_datasets"][0]["generator_version"], "other generator (version withheld)")
        reconciliation = result["balance_reconciliation"]
        self.assertTrue(reconciliation["fully_reconciled"])
        self.assertEqual(reconciliation["net_success_change_bdt"], "55.00")
        self.assertEqual(reconciliation["current_balance_total_bdt"], "155.00")

    def test_wallet_mismatch_cannot_cancel_at_aggregate_level(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE users SET balance=160 WHERE id=1")
            connection.execute("INSERT INTO users(id,balance) VALUES(2,95)")
            connection.execute("INSERT INTO wallet_opening_balances(user_id,opening_balance) VALUES(2,100)")
            connection.commit()
        result = inventory.inspect_database(self.database, self.expected)["balance_reconciliation"]
        self.assertFalse(result["fully_reconciled"])
        self.assertEqual(result["mismatched_anchored_accounts"], 2)
        self.assertEqual(result["absolute_discrepancy_total_bdt"], "10.00")
        self.assertEqual(result["largest_absolute_discrepancy_bdt"], "5.00")

    def test_readonly_connection_blocks_writes_and_closes_on_exception(self):
        captured = None
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            with inventory.readonly_snapshot(self.database) as connection:
                captured = connection
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("DELETE FROM users")
                raise RuntimeError("fixture failure")
        with self.assertRaises(sqlite3.ProgrammingError):
            captured.execute("SELECT 1")
        self.assertEqual(inventory.inspect_database(self.database, self.expected)["tables"]["users"]["row_count"], 1)

    def test_inventory_connection_closes_after_success_and_failed_inspection(self):
        original_connect, connections = sqlite3.connect, []

        def connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch.object(inventory.sqlite3, "connect", side_effect=connect):
            inventory.inspect_database(self.database, self.expected)
            with patch.object(inventory, "observed_schema", side_effect=RuntimeError("failed read")):
                with self.assertRaisesRegex(RuntimeError, "failed read"):
                    inventory.inspect_database(self.database, self.expected)
        self.assertEqual(len(connections), 2)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_live_wal_nonexistent_and_outside_workspace_inputs_are_refused(self):
        Path(str(self.database) + "-wal").write_bytes(b"owned fixture WAL")
        with self.assertRaisesRegex(ValueError, "WAL"):
            inventory.inspect_database(self.database, self.expected)
        missing = self.directory / "missing.db"
        with self.assertRaisesRegex(ValueError, "existing"):
            inventory.inspect_database(missing, self.expected)
        self.assertFalse(missing.exists())
        with self.assertRaisesRegex(ValueError, "workspace"):
            inventory.workspace_path(inventory.ROOT.parent / "outside.db", exists=False)

    def test_schema_provenance_includes_actual_checks_foreign_keys_indexes_and_drift(self):
        result = inventory.inspect_database(self.database, self.expected)
        transaction = result["tables"]["transactions"]
        self.assertEqual(transaction["checks"], ["amount >= 0 AND (fee >= 0)"])
        self.assertIn("CHECK", transaction["ddl"])
        self.assertEqual(transaction["foreign_keys"][0]["table"], "users")
        self.assertEqual(transaction["foreign_keys"][0]["from"], "user_id")
        users = result["tables"]["users"]
        self.assertEqual(users["indexes"][0]["name"], "ux_test_mobile")
        self.assertTrue(users["indexes"][0]["unique"])
        self.assertIn("ai_conversation_controls", result["schema_comparison"]["missing_tables"])
        self.assertIn("ix_transactions_user_status_created", result["schema_comparison"]["table_differences"]["transactions"]["missing_indexes"])
        self.assertEqual(result["migration_heads"], [])

    def test_metadata_config_does_not_connect_seed_or_modify_default_database(self):
        main = inventory.ROOT / "instance" / "upay_hackathon.db"
        before = inventory.sha256_file(main) if main.is_file() else None
        from app import create_app as original_create_app

        def isolated_create_app(settings):
            self.assertEqual(settings.SQLALCHEMY_DATABASE_URI, "sqlite:///:memory:")
            self.assertFalse(settings.AUTO_CREATE_SCHEMA)
            self.assertFalse(settings.SEED_DEMO_DATA)
            return original_create_app(settings)

        with patch("app.create_app", side_effect=isolated_create_app), patch("app._seed_demo_data", side_effect=AssertionError("must not seed")):
            expected = inventory.expected_schema()
        if before:
            self.assertEqual(inventory.sha256_file(main), before)
        control = expected["ai_conversation_controls"]
        self.assertEqual(control["foreign_keys"][0]["ondelete"], "CASCADE")
        self.assertIn("app/domain/ai_governance.py", control["source"])
        consent = expected["ai_consents"]
        self.assertEqual(consent["primary_key"], ["user_id", "purpose"])
        self.assertEqual(expected["transactions"]["columns"][-1]["postgresql_type"], "TIMESTAMP WITH TIME ZONE")
        self.assertEqual(expected["api_idempotency"]["unique_constraints"][0]["columns"], ["token_id", "key"])
        self.assertTrue(all(table["group"] != "Unclassified" for table in expected.values()))

    def test_cli_cannot_overwrite_snapshot_and_generates_selected_schema_catalog(self):
        before = self.database.read_bytes()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            inventory.main(["--database", str(self.database), "--json", str(self.database)])
        self.assertEqual(self.database.read_bytes(), before)
        json_path, markdown_path = self.directory / "inventory.json", self.directory / "catalog.md"
        with redirect_stdout(StringIO()):
            self.assertEqual(inventory.main(["--database", str(self.database), "--json", str(json_path), "--markdown", str(markdown_path)]), 0)
        report = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(report["databases"]), 1)
        self.assertEqual(report["databases"][0]["sha256_before"], report["databases"][0]["sha256_after"])
        self.assertIn("migrations/versions/20261007_03.py", report["source_sha256"])
        self.assertIn("#### `users`", markdown_path.read_text(encoding="utf-8"))
        self.assertEqual(self.database.read_bytes(), before)

    def test_fresh_checkout_with_no_database_renders_every_column_without_creating_data(self):
        fresh = self.directory / "fresh-checkout"
        fresh.mkdir()
        paths = inventory.default_databases(fresh)
        self.assertEqual(paths, [])
        with patch.object(inventory, "inspect_database", side_effect=AssertionError("no database should be opened")):
            report = inventory.build_inventory(paths)
        catalog = inventory.render_catalog(report)
        self.assertEqual(report["databases"], [])
        self.assertIn("The historical main file was **not inspected**", catalog)
        self.assertIn("schema metadata only", catalog)
        for name, table in report["expected_tables"].items():
            self.assertIn("#### `" + name + "`", catalog)
            for column in table["columns"]:
                self.assertIn("| `" + column["name"] + "` |", catalog)
        self.assertFalse((fresh / "instance" / "upay_hackathon.db").exists())

    def test_only_judge_selected_does_not_claim_main_was_inspected(self):
        report = inventory.build_inventory([self.database])
        report["databases"][0]["path"] = "instance/judge-demo.db"
        catalog = inventory.render_catalog(report)
        self.assertIn("| Table | Judge demo |", catalog)
        self.assertIn("The historical main file was **not inspected**", catalog)
        self.assertIn("Main rows: not inspected.", catalog)
        self.assertIn("#### `ai_conversation_controls`", catalog)

    def test_hard_link_report_alias_cannot_overwrite_database(self):
        alias = self.directory / "database-alias.json"
        os.link(self.database, alias)
        before = self.database.read_bytes()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            inventory.main(["--database", str(self.database), "--json", str(alias)])
        self.assertEqual(self.database.read_bytes(), before)

    def test_phase2_only_replaces_marked_block_and_preserves_original_feedback_bytes(self):
        phase2 = self.directory / "phase_2.md"
        prefix = "# Original feedback\r\nP1: 3.33 / 5\r\n\"Synthetic data is good, but safeguards need more depth.\"\r\n"
        suffix = "\r\nOriginal footer remains exactly the same.\r\n"
        document = prefix + inventory.BEGIN_MARKER + "\r\nold catalog\r\n" + inventory.END_MARKER + suffix
        phase2.write_bytes(document.encode("utf-8"))
        with redirect_stdout(StringIO()):
            inventory.main(["--database", str(self.database), "--json", str(self.directory / "report.json"),
                            "--markdown", str(self.directory / "catalog.md"), "--phase2", str(phase2)])
        result = phase2.read_bytes().decode("utf-8")
        self.assertTrue(result.startswith(prefix + inventory.BEGIN_MARKER))
        self.assertTrue(result.endswith(inventory.END_MARKER + suffix))
        self.assertNotIn("old catalog", result)
        self.assertIn("(app/domain/models.py)", result)
        self.assertIn("(output/qa/database-inventory.json)", result)
        self.assertIn("(docs/DEPLOYMENT.md)", result)
        for invalid in (prefix, document + inventory.BEGIN_MARKER,
                        inventory.END_MARKER + inventory.BEGIN_MARKER):
            with self.assertRaises(ValueError):
                inventory.embed_catalog(invalid, "replacement")


if __name__ == "__main__":
    unittest.main()
