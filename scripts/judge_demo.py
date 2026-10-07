"""Create or reuse an isolated, reconciled synthetic judge demonstration.

python scripts/judge_demo.py --check
python scripts/judge_demo.py --port 5000
python -m flask --app scripts.judge_demo:create_judge_app durable-worker --watch --interval 5 --batch-size 20

This entrypoint never targets the project's ordinary wallet database and never
resets an existing fixture. A new filename is required for a new sample period.
"""

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet
from sqlalchemy import inspect

from app import create_app
from app.domain.demo import DemoDataset
from app.domain.models import User
from app.extensions import db
from app.services.cashflow_model import forecast_for_user, load_artifact
from app.services.demo_seed import DEMO_GENERATOR_VERSION, DEMO_MAIN_MOBILE, seed_reconciled_demo_dataset
from app.services.financial_health_service import health_for_user
from app.services.reporting_service import local_datetime
from config import DevelopmentConfig


FORMAT = "isolated-judge-demo-v1"
DEFAULT_DATABASE = "instance/judge-demo.db"


def completed_demo_date():
    return local_datetime(datetime.now(timezone.utc)).date() - timedelta(days=1)


def validated_judge_path(candidate):
    raw = Path(candidate)
    path = raw if raw.is_absolute() else ROOT / raw
    instance = ROOT / "instance"
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT):
        raise ValueError("Judge fixtures cannot use symbolic links.")
    path, instance = path.resolve(), instance.resolve()
    if not instance.is_relative_to(ROOT.resolve()):
        raise ValueError("The instance directory must resolve inside the project workspace.")
    if not path.is_relative_to(instance) or path.parent == path:
        raise ValueError("Judge fixtures must stay inside the project's instance directory.")
    if not re.fullmatch(r"judge-[A-Za-z0-9_-]+\.db", path.name, re.I):
        raise ValueError("Use a dedicated judge-*.db filename; the ordinary wallet database is forbidden.")
    primary = (ROOT / "instance" / "upay_hackathon.db").resolve()
    if path == primary or (path.exists() and primary.exists() and path.samefile(primary)):
        raise ValueError("The ordinary wallet database cannot be used for the judge demo.")
    if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        raise ValueError("Judge fixtures must be ordinary files without hard-link aliases.")
    return path


def _read_existing_provenance(path):
    """Read-only evidence before initializing an application against an existing file."""
    try:
        uri = "file:" + quote(path.as_posix(), safe=":/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            dataset = connection.execute("SELECT generator_version, synthetic, starts_on, ends_on FROM demo_datasets").fetchall()
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
    except (sqlite3.Error, OSError) as exc:
        raise ValueError("Existing file is not a recognized judge fixture; choose a new dedicated filename.") from exc
    try:
        valid = (len(dataset) == 1 and dataset[0][0] == DEMO_GENERATOR_VERSION and dataset[0][1] == 1
                 and integrity == "ok"
                 and (date.fromisoformat(dataset[0][3]) - date.fromisoformat(dataset[0][2])).days == 119)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Existing fixture provenance or integrity does not match the approved 120-day synthetic generator.")


def _runtime_settings(path, *, fresh):
    sidecar = path.with_name(path.name + ".runtime.json")
    if sidecar.is_symlink() or (sidecar.exists() and (not sidecar.is_file() or sidecar.stat().st_nlink > 1)):
        raise ValueError("Judge runtime settings cannot use links or non-file paths.")
    if fresh:
        values = {"format": FORMAT, "database": path.name, "secret_key": secrets.token_urlsafe(48),
                  "audit_signing_key": secrets.token_urlsafe(48), "security_hash_key": secrets.token_urlsafe(48),
                  "data_encryption_key": Fernet.generate_key().decode()}
        try:
            descriptor = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(values, stream)
                stream.write("\n")
        except FileExistsError as exc:
            raise ValueError("A runtime sidecar already exists without its fixture; choose a new judge filename.") from exc
    else:
        try:
            values = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("This judge fixture is missing its runtime settings; preserve it and choose a new filename.") from exc
    if (not isinstance(values, dict) or values.get("format") != FORMAT or values.get("database") != path.name
            or any(not isinstance(values.get(key), str) or len(values[key]) < 32
                   for key in ("secret_key", "audit_signing_key", "security_hash_key", "data_encryption_key"))):
        raise ValueError("Judge runtime settings do not match this fixture.")
    Fernet(values["data_encryption_key"].encode())
    return values


def _configuration(path, values, *, fresh):
    cookie_suffix = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    class JudgeConfig(DevelopmentConfig):
        DEBUG = False
        TESTING = False
        APP_NAME = "UpayX"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + path.as_posix()
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15, "check_same_thread": False}}
        AUTO_CREATE_SCHEMA = fresh
        SEED_DEMO_DATA = False
        SECRET_KEY = values["secret_key"]
        SECURITY_HASH_KEY = values["security_hash_key"]
        AUDIT_SIGNING_KEY = values["audit_signing_key"]
        SECURITY_PRODUCTION = False
        REQUIRE_TRUSTED_SESSIONS = True
        SESSION_COOKIE_SECURE = False
        SESSION_COOKIE_HTTPONLY = True
        SESSION_COOKIE_SAMESITE = "Lax"
        SESSION_COOKIE_NAME = "judge_session_" + cookie_suffix
        DEVICE_COOKIE_NAME = "judge_device_" + cookie_suffix
        DEMO_OTP_ALLOWED = True
        DEMO_OTP = "123456"
        DEMO_BALANCES_ALLOWED = True
        DATA_ENCRYPTION_KEY = values["data_encryption_key"]
        DATA_ENCRYPTION_KEYS = ""
        REQUIRE_DATA_ENCRYPTION = False  # Approved seed includes explicitly synthetic legacy fields.
        OPENAI_API_KEY = ""
        ASSISTANT_API_ENABLED = False
        PROVIDER_BASE_URL = ""
        PROVIDER_SIGNING_SECRET = ""
        PROVIDER_ALLOW_LOOPBACK_HTTP = False
        OBSERVABILITY_TOKEN = ""
        TRUST_PROXY = False
        SCHEDULE_AUTO_RUN_ON_REQUEST = False
        MONITOR_LARGE_AMOUNT_BDT = "50000"
        MONITOR_BURST_COUNT = 5
        MONITOR_BURST_SECONDS = 60
        WORKER_BATCH_SIZE = 50
        WORKER_MAX_ATTEMPTS = 5
        WORKER_RETRY_SECONDS = 30
        JUDGE_DEMO_MODE = True
    return JudgeConfig


def readiness_report(app, path, *, fresh):
    with app.app_context():
        known = set(inspect(db.engine).get_table_names())
        missing = set(db.metadata.tables) - known
        if missing:
            raise ValueError("The existing fixture needs explicit schema migration before reuse; no schema was changed.")
        dataset = DemoDataset.query.one()
        owner = User.query.filter_by(mobile=DEMO_MAIN_MOBILE).one()
        health = health_for_user(owner.id)
        model = load_artifact()
        forecast = forecast_for_user(owner.id)
        counts = {table.name: db.session.execute(db.select(db.func.count()).select_from(table)).scalar_one()
                  for table in db.metadata.sorted_tables}
        return {"ready": True, "environment": "isolated_synthetic_judge_demo", "real_provider_connected": False,
                "database": str(path), "created": fresh, "reused_without_reset": not fresh,
                "dataset": {"synthetic": dataset.synthetic, "generator": dataset.generator_version,
                    "start_date": dataset.starts_on.isoformat(), "end_date": dataset.ends_on.isoformat(),
                    "days": (dataset.ends_on - dataset.starts_on).days + 1,
                    "frozen_on_restart": True, "age_days": (completed_demo_date() - dataset.ends_on).days},
                "table_counts": counts, "wallet_balance": str(owner.balance),
                "ledger_reconciled": health["reconciliation"]["matched"], "safe_to_spend": str(health["safe_to_spend"]),
                "model": {"artifact_approved": True, "algorithm": model["algorithm"], "version": model["model_version"],
                    "forecast_available": forecast["available"], "forecast_unavailable_reason": forecast.get("reason")},
                "demo_sign_in": {"mobile": DEMO_MAIN_MOBILE, "shared_synthetic_only_otp": "123456"},
                "read_only_visits": True, "csrf_enabled": True, "debug": False,
                "hosted_ai_disabled": True, "money_movement": "local demo ledger only"}


def prepare_judge_demo(database=DEFAULT_DATABASE, *, as_of=None):
    path = validated_judge_path(database)
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    if as_of is not None and (not isinstance(as_of, date) or isinstance(as_of, datetime)):
        raise ValueError("as_of must be an ISO calendar date.")
    if as_of is not None and as_of > local_datetime(datetime.now(timezone.utc)).date():
        raise ValueError("Choose a current or earlier synthetic review date.")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".init.lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("Judge fixture initialization is already locked; inspect the dedicated lock before retrying.") from exc
    app = None
    try:
        fresh = not path.exists()
        if not fresh:
            _read_existing_provenance(path)
        values = _runtime_settings(path, fresh=fresh)
        if fresh:
            path.touch(exist_ok=False)
        app = create_app(_configuration(path, values, fresh=fresh))
        if fresh:
            with app.app_context():
                seed_reconciled_demo_dataset(as_of=as_of or completed_demo_date())
        report = readiness_report(app, path, fresh=fresh)
        app.extensions["judge_demo_report"] = report
        return app, report
    except Exception:
        if app is not None:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        raise
    finally:
        lock.rmdir()  # Only the exact empty lock created by this invocation is removed.


def create_judge_app(database=DEFAULT_DATABASE, as_of=None):
    """Flask CLI factory; the durable worker uses exactly the same isolated fixture."""
    return prepare_judge_demo(database, as_of=as_of)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--as-of", type=date.fromisoformat, help="First creation only; reused fixtures keep their original 120-day period.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--check", action="store_true", help="Create/reuse and print readiness evidence without starting a server.")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    try:
        app, report = prepare_judge_demo(args.database, as_of=args.as_of)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.check:
        print(json.dumps(report, indent=2))
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        return report
    print("SYNTHETIC JUDGE DEMO — local wallet only; no live upay provider or hosted AI.")
    print(f"Open http://127.0.0.1:{args.port}/?days=30")
    print(f"Demo sign-in: {DEMO_MAIN_MOBILE}; shared synthetic-only OTP: 123456")
    print(f"Frozen sample period: {report['dataset']['start_date']} through {report['dataset']['end_date']}")
    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
