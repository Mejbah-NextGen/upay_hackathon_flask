"""Evidence ZIP excludes runtime secrets/data and stays reproducible."""

import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

from scripts.build_submission import REQUIRED_FILES, build_submission


class SubmissionBundleTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(__file__).resolve().parents[1] / "tmp" / "submission-bundle-tests"
        self.parent.mkdir(parents=True, exist_ok=True)
        self.root = self.parent / uuid4().hex
        self.root.mkdir()  # Inherit workspace ACLs on Windows instead of tempfile's mode 0700.
        for relative in REQUIRED_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n" if target.suffix == ".json" else "synthetic source\n", encoding="utf-8")

    def tearDown(self):
        if self.root.resolve().parent != self.parent.resolve() or self.root.is_symlink():
            raise ValueError("Unsafe submission-test cleanup target.")
        shutil.rmtree(self.root)

    def put(self, relative, data="private fixture"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")

    def test_bundle_excludes_credentials_databases_logs_and_private_sidecars(self):
        private = [".env", ".env.local", "instance/wallet.db", "instance/wallet.db-wal", ".git/config",
                   "tmp/report.log", ".venv/example.py", "app/uploads/private.svg", "docs/customer.csv",
                   "output/qa/submission/access-token.txt", "output/qa/submission/raw.log",
                   "output/qa/submission/access-token.json", "output/qa/submission/private/manifest.json",
                   "output/qa/submission/wallet.db", "output/submission/previous.zip", "tests/token.json"]
        for relative in private:
            self.put(relative)
        self.put(".env.example", "SECRET_KEY=replace-me\n")
        self.put("output/pdf/UPAYX_DATABASE_REPORT.pdf", "historical synthetic PDF")
        result = build_submission(Path("output/submission/review.zip"), root=self.root)
        with zipfile.ZipFile(self.root / result["archive"]) as archive:
            self.assertEqual(archive.testzip(), None)
            names = set(archive.namelist())
            self.assertTrue(set(private).isdisjoint(names))
            self.assertIn(".env.example", names)
            self.assertIn("output/pdf/UPAYX_DATABASE_REPORT.pdf", names)
            manifest = json.loads(archive.read("SUBMISSION_MANIFEST.json"))
            for name, record in manifest["files"].items():
                payload = archive.read(name)
                self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(record["bytes"], len(payload))

    def test_same_sources_produce_same_zip_bytes_and_guard_overwrite(self):
        first = build_submission(Path("output/submission/one.zip"), root=self.root)
        second = build_submission(Path("output/submission/two.zip"), root=self.root)
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual((self.root / first["archive"]).read_bytes(), (self.root / second["archive"]).read_bytes())
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_submission(Path(first["archive"]), root=self.root)
        rebuilt = build_submission(Path(first["archive"]), root=self.root, overwrite=True)
        self.assertEqual(first["archive_sha256"], rebuilt["archive_sha256"])

    def test_rejects_outside_output_and_incomplete_source(self):
        with self.assertRaisesRegex(ValueError, "inside the project"):
            build_submission(self.root.parent / "escaped-submission.zip", root=self.root)
        (self.root / "requirements.txt").unlink()
        with self.assertRaisesRegex(ValueError, "Required submission files"):
            build_submission(Path("output/submission/review.zip"), root=self.root)

    def test_rejects_source_reported_as_symlink(self):
        candidate = self.root / "app" / "linked.py"
        candidate.write_text("source", encoding="utf-8")
        # The OS boundary is mocked so Windows does not require Developer Mode.
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path == candidate or original(path)):
            with self.assertRaisesRegex(ValueError, "Symlink source"):
                build_submission(Path("output/submission/review.zip"), root=self.root)


if __name__ == "__main__":
    unittest.main()
