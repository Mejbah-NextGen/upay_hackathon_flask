"""Bounded HTTP load on disposable synthetic data; no existing wallet is used.

Run: python scripts/load_test.py --output tmp/infrastructure-qa/load-sqlite.json
QA_DATABASE_URL can select a loopback PostgreSQL QA cluster made by postgres_qa.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import platform
import re
import secrets
import sys
from threading import Thread
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from werkzeug.serving import WSGIRequestHandler, make_server

from app import create_app
from app.blueprints.api.routes import issue_token
from app.domain.integration import ApiIdempotency
from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.extensions import db
from app.services.reporting_service import local_datetime
from config import DevelopmentConfig


def verify_disposable_postgres(url):
    """Name, host and an out-of-metadata marker guard destructive QA setup."""
    parsed = make_url(url)
    if (parsed.get_backend_name() != "postgresql" or parsed.host not in {"127.0.0.1", "localhost"}
            or not re.fullmatch(r"upay_qa_[a-f0-9]{32}", parsed.database or "") or not parsed.port):
        raise ValueError("PostgreSQL QA must use the runner's disposable loopback database.")
    import psycopg
    with psycopg.connect(host=parsed.host, port=parsed.port, dbname=parsed.database,
                         user=parsed.username, password=parsed.password, connect_timeout=5) as connection:
        guard = connection.execute("SELECT purpose FROM _qa_cluster_guard").fetchone()
        if guard != ("upayx-isolated-qa-v1",):
            raise ValueError("The database is not an isolated QA fixture.")


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 2)


def run_load(*, requests=240, concurrency=8):
    if not 12 <= requests <= 5000 or requests % 4 or not 1 <= concurrency <= 32:
        raise ValueError("Use 12–5000 requests divisible by four and 1–32 concurrent clients.")
    folder = PROJECT_ROOT / "tmp" / "infrastructure-qa"
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / ("load-" + uuid4().hex + ".sqlite")
    database_url = os.environ.get("QA_DATABASE_URL") or "sqlite:///" + database.as_posix()
    parsed = make_url(database_url)
    if parsed.get_backend_name() == "postgresql":
        verify_disposable_postgres(database_url)
    elif parsed.get_backend_name() != "sqlite" or Path(parsed.database).resolve() != database.resolve():
        raise ValueError("SQLite load tests create their own unique workspace database.")

    class LoadConfig(DevelopmentConfig):
        TESTING = False
        DEBUG = False
        SECRET_KEY = secrets.token_urlsafe(40)
        SQLALCHEMY_DATABASE_URI = database_url
        SQLALCHEMY_ENGINE_OPTIONS = ({"pool_size": concurrency, "max_overflow": concurrency,
                                     "connect_args": {"timeout": 30, "check_same_thread": False}}
                                    if parsed.get_backend_name() == "sqlite" else
                                    {"pool_size": concurrency, "max_overflow": concurrency, "pool_pre_ping": True})
        SEED_DEMO_DATA = False
        AUTO_CREATE_SCHEMA = parsed.get_backend_name() == "sqlite"
        SCHEDULE_AUTO_RUN_ON_REQUEST = False
        ASSISTANT_API_ENABLED = False
        SECURITY_PRODUCTION = False
        REQUIRE_TRUSTED_SESSIONS = False
        DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
        DATA_ENCRYPTION_KEYS = ""
        REQUIRE_DATA_ENCRYPTION = True
        RATE_LIMITS = {"api": (10000, 60)}

    app = create_app(LoadConfig)
    server = None
    thread = None
    try:
        with app.app_context():
            if parsed.get_backend_name() == "sqlite":
                db.drop_all()
                db.create_all()
            else:
                with db.engine.begin() as connection:
                    for table in reversed(db.metadata.sorted_tables):
                        connection.execute(table.delete())
            now = datetime.now(timezone.utc)
            user = User(full_name="Synthetic Load User", mobile="01777000001", balance=Decimal("10000.00"), verified=True,
                        created_at=now-timedelta(days=30))
            recipient = User(full_name="Synthetic Load Recipient", mobile="01877000002", balance=Decimal("0.00"), verified=True)
            db.session.add_all([user, recipient])
            db.session.commit()
            user_id, recipient_id = user.id, recipient.id
            for day in range(1, 29):
                db.session.add(Transaction(user_id=user_id, kind="BILL_PAYMENT", direction="OUT", title="Synthetic historical spending",
                                           amount=Decimal(100 + day % 7 * 10), status="SUCCESS", created_at=now-timedelta(days=day)))
            db.session.commit()
            baseline_transactions = Transaction.query.count()
            token, bearer = issue_token(user_id, {"balance:read", "insights:read", "schedules:read", "schedules:write"}, name="isolated-load-fixture", days=1)
            token_id = token.id
            db.session.remove()
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        due_date = (local_datetime(datetime.now(timezone.utc)).date() + timedelta(days=1)).isoformat()
        payload = {"kind": "SEND_MONEY", "amount": "10.00", "recipient_number": "01877000002",
                   "frequency": "ONE_TIME", "due_date": due_date, "auto_pay": True, "confirmed": True}
        raw = json.dumps(payload).encode()
        def request_one(index):
            variant = index % 4
            path = "/api/v1/balance" if variant == 0 else "/api/v1/financial-health" if variant == 1 else "/api/v1/schedules"
            method = "GET" if variant < 2 else "POST"
            headers = {"Authorization": "Bearer " + bearer}
            if method == "POST":
                headers.update({"Content-Type": "application/json", "Idempotency-Key": "shared-load-key-0001" if variant == 2 else f"fresh-load-key-{index:06d}"})
            started = perf_counter()
            try:
                with urlopen(Request(base + path, data=raw if method == "POST" else None,
                                     method=method, headers=headers), timeout=30) as response:
                    status, output = response.status, json.loads(response.read())
            except HTTPError as exc:
                status, output = exc.code, json.loads(exc.read())
            except Exception as exc:
                return {"status": 0, "milliseconds": (perf_counter() - started) * 1000,
                        "kind": variant, "error_category": type(exc).__name__}
            ids = [row["id"] for row in output.get("data", {}).get("items", [])] if method == "POST" else []
            return {"status": status, "milliseconds": (perf_counter() - started) * 1000,
                    "kind": variant, "schedule_ids": ids,
                    "forecast_available": output.get("data", {}).get("forecast", {}).get("available") if variant == 1 else None}
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            outcomes = list(pool.map(request_one, range(requests)))
        elapsed = perf_counter() - started
        counts = {}
        for row in outcomes:
            key = str(row["status"])
            counts[key] = counts.get(key, 0) + 1
        shared = {schedule_id for row in outcomes if row["kind"] == 2 for schedule_id in row.get("schedule_ids", [])}
        expected_plans = requests // 4 + 1
        with app.app_context():
            invariants = {
                "no_http_5xx_or_transport_errors": all(200 <= row["status"] < 500 for row in outcomes),
                "all_requests_succeeded": all(row["status"] in {200, 201} for row in outcomes),
                "shared_key_created_one_schedule": len(shared) == 1,
                "one_plan_per_unique_key": ScheduledPayment.query.count() == expected_plans,
                "one_idempotency_record_per_unique_key": ApiIdempotency.query.filter_by(token_id=token_id).count() == expected_plans,
                "sender_not_debited_before_due_date": db.session.get(User, user_id).balance == Decimal("10000.00"),
                "recipient_not_credited_before_due_date": db.session.get(User, recipient_id).balance == Decimal("0.00"),
                "no_new_early_ledger_transactions": Transaction.query.count() == baseline_transactions,
                "all_future_plans_pending": ScheduledPayment.query.filter_by(status="SCHEDULED").count() == expected_plans,
                "all_financial_health_reads_run_available_forecast": all(row.get("forecast_available") is True for row in outcomes if row["kind"] == 1),
            }
            observed_plans = ScheduledPayment.query.count()
            db.session.remove()
        latencies = [row["milliseconds"] for row in outcomes]
        return {"schema_version": 1, "database": parsed.get_backend_name(), "workload": "real loopback threaded HTTP: 25% balance GET, 25% financial-health GET, 25% duplicate-key future-plan POST, 25% fresh-key future-plan POST",
                "request_count": requests, "concurrency": concurrency, "duration_seconds": round(elapsed, 3),
                "throughput_requests_per_second": round(requests / elapsed, 2),
                "latency_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95), "p99": percentile(latencies, .99)},
                "status_counts": counts, "expected_plans": expected_plans, "observed_plans": observed_plans,
                "baseline_synthetic_history_receipts": baseline_transactions,
                "forecast_inference_reads": sum(row.get("forecast_available") is True for row in outcomes),
                "invariants": invariants, "all_invariants_passed": all(invariants.values()),
                "rate_limit": {"api_token_requests": 10000, "window_seconds": 60, "purpose": "isolated measurement workload; production defaults unchanged"},
                "platform": {"os": platform.system(), "python": platform.python_version(), "machine": platform.machine(), "cpu_count": os.cpu_count()},
                "scope": "one local app instance, one synthetic user, simulated future plans; not production capacity certification"}
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=10)
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        if parsed.get_backend_name() == "sqlite":
            if database.resolve().parent != folder.resolve() or database.is_symlink():
                raise ValueError("Refusing cleanup outside the QA workspace.")
            for suffix in ("", "-wal", "-shm", "-journal"):
                candidate = Path(str(database) + suffix)
                if candidate.is_symlink() or candidate.resolve().parent != folder.resolve():
                    raise ValueError("Invalid QA database cleanup target.")
                candidate.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "tmp" / "infrastructure-qa" / "load-sqlite.json")
    parser.add_argument("--requests", type=int, default=240)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    result = run_load(requests=args.requests, concurrency=args.concurrency)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["all_invariants_passed"] else 1)
