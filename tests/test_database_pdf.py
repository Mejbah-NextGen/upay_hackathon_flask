"""Verify complete admin snapshots without touching the application database."""

import hashlib
import json
from contextlib import closing
import shutil
import sqlite3
import unittest
import uuid
from pathlib import Path

from pypdf import PdfReader

from scripts.export_database_pdf import export_pdf, read_snapshot


class CompleteDatabasePdfTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / ".tmp" / "database-pdf-tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.root = temporary_root / uuid.uuid4().hex
        self.root.mkdir()
        self.database = self.root / "sample.db"
        with closing(sqlite3.connect(self.database)) as source:
            source.executescript("""
                CREATE TABLE audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER,
                    state TEXT, note TEXT, amount NUMERIC, nullable TEXT,
                    empty TEXT, binary BLOB, last_column TEXT
                );
                CREATE TABLE empty_table (user_id INTEGER PRIMARY KEY, label TEXT);
            """)
            source.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?,?,?)", (
                1, 20, "FAILED", "Visible <test> & note", 12.34, None, "", b"\x00\xff", "Final-column-evidence",
            ))
            source.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?,?,?)", (
                2, 30, "SUCCESS", "Other account retained", 56.78, None, "", b"", "SECOND-ROW",
            ))
            source.commit()
        self.original = hashlib.sha256(self.database.read_bytes()).hexdigest()

    def tearDown(self):
        allowed_root = Path(__file__).resolve().parents[1] / ".tmp" / "database-pdf-tests"
        if not self.root.resolve().is_relative_to(allowed_root.resolve()):
            raise ValueError("Test cleanup escaped its workspace.")
        shutil.rmtree(self.root)

    def test_snapshot_covers_internal_empty_and_wide_tables_without_writes(self):
        snapshot = read_snapshot(self.database)
        tables = {item["name"]: item for item in snapshot["tables"]}
        self.assertEqual(set(tables), {"audit", "empty_table", "sqlite_sequence"})
        self.assertEqual(tables["empty_table"]["rows"], [])
        self.assertEqual(tables["audit"]["rows"][0][5:9], [None, "", {"encoding": "base64", "data": "AP8="}, "Final-column-evidence"])
        self.assertEqual(snapshot["integrity_check"], "ok")
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), self.original)

    def test_pdf_contains_all_column_groups_and_exact_attachment(self):
        result = export_pdf(self.database, self.root / "report.pdf")
        pdf = PdfReader(result["pdf"])
        payload = pdf.attachments["database_snapshot.json"][0]
        self.assertEqual(hashlib.sha256(payload).hexdigest(), result["snapshot_sha256"])
        attached = {item["name"]: item for item in json.loads(payload)["tables"]}
        self.assertEqual(attached["audit"]["rows"], read_snapshot(self.database)["tables"][0]["rows"])
        text = "\n".join(page.extract_text() for page in pdf.pages)
        for value in ("audit", "empty_table", "sqlite_sequence", "last_column", "Final-column-evidence", "Other account retained", "Visible <test> & note", "BASE64:AP8=", "NULL"):
            self.assertIn(value, text)
        self.assertEqual(result["tables"], 3)
        self.assertEqual(result["rows"], 3)
        self.assertGreater(len(pdf.pages), 3)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), self.original)


if __name__ == "__main__":
    unittest.main()
