"""Backup and replace local demonstration records with a reconciled 120-day seed.

Usage: python scripts/reset_demo_data.py --confirm --as-of 2026-10-02
Never targets remote databases, paths outside instance/, or backup files.
"""

import argparse
from contextlib import closing
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData
from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db
from app.services.demo_seed import seed_reconciled_demo_dataset
from app.services.reporting_service import local_datetime
from config import DevelopmentConfig


def validated_database_path(candidate):
    """Resolve both scope and target before any backup or database mutation."""
    instance = (ROOT / "instance").resolve()
    path = Path(candidate)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_relative_to(instance) or path == instance:
        raise ValueError("Reset is restricted to a local database inside this project's instance directory.")
    if "backups" in (part.lower() for part in path.relative_to(instance).parts):
        raise ValueError("Backups are never valid reset targets.")
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("The reset target must have a .db, .sqlite or .sqlite3 extension.")
    if path.exists() and not path.is_file():
        raise ValueError("The reset target must be a regular database file.")
    return path


def configured_database_path():
    url = make_url(DevelopmentConfig.SQLALCHEMY_DATABASE_URI)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Only a local SQLite database can be reset. Use --database instance/upay_hackathon.db if appropriate.")
    return validated_database_path(url.database)


def backup_database(path):
    if not path.exists():
        return None
    backup_dir = (ROOT / "instance" / "backups").resolve()
    if not backup_dir.is_relative_to((ROOT / "instance").resolve()):
        raise ValueError("The backup directory resolves outside instance/.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"{path.stem}-before-demo-reset-{stamp}.db"
    # SQLite's backup API includes committed WAL pages, unlike a file copy.
    with closing(sqlite3.connect(str(path), timeout=30)) as source:
        with closing(sqlite3.connect(str(backup))) as destination:
            source.backup(destination)
            result = destination.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"SQLite backup integrity check failed: {result}")
    return backup


def reset_demo_database(candidate, *, as_of):
    path = validated_database_path(candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_database(path)

    class ResetConfig(DevelopmentConfig):
        DEBUG = False
        SEED_DEMO_DATA = False
        SCHEDULE_AUTO_RUN_ON_REQUEST = False
        ASSISTANT_API_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path.as_posix()}"

    app = create_app(ResetConfig)
    try:
        with app.app_context():
            try:
                # Reflection covers any old or third-party table too. Keep table
                # definitions, remove all records, then seed and commit together.
                metadata = MetaData()
                metadata.reflect(bind=db.engine)
                for table in reversed(metadata.sorted_tables):
                    db.session.execute(table.delete())
                result = seed_reconciled_demo_dataset(as_of=as_of)
            except Exception:
                db.session.rollback()
                raise
            result["database"] = str(path)
            result["backup"] = str(backup) if backup else None
            result["label"] = "SYNTHETIC DEMO DATA - NO REAL CUSTOMER RECORDS"
            db.session.remove()
            db.engine.dispose()
            return result
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Explicitly approve replacing all records after a SQLite backup.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=local_datetime(datetime.now(timezone.utc)).date(), help="Last Bangladesh calendar date, YYYY-MM-DD (default: today).")
    parser.add_argument("--database", help="Local SQLite path within this project's instance/ (default: configured DATABASE_URL).")
    args = parser.parse_args(argv)
    if not args.confirm:
        parser.error("Reset requires --confirm. This replaces every database record; an existing database is backed up first.")
    try:
        target = validated_database_path(args.database) if args.database else configured_database_path()
        result = reset_demo_database(target, as_of=args.as_of)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Reset refused or failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
