"""Executable reference sandbox, isolated ledger and real HTTP contract demo.

Run: python scripts/provider_contract_demo.py --output instance/provider-contract.json
Serve: python scripts/provider_contract_demo.py --serve --port 8091 --database instance/reference-provider.sqlite
Set PROVIDER_SIGNING_SECRET for serve mode; never pass a secret on the command line.
"""

import argparse
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.provider_service import canonical, signature, utc, verify_signature


class IsolatedDirectory:
    """Use inherited Windows ACLs; Python tempfile's mode 0700 is incompatible with some sandboxes."""

    def __init__(self, prefix):
        self.parent = Path(__file__).resolve().parents[1] / "instance"
        self.parent.mkdir(exist_ok=True)
        self.path = self.parent / (prefix + uuid4().hex)
        self.path.mkdir()
        self.name = str(self.path)

    def __enter__(self):
        return self.name

    def cleanup(self):
        if self.path.resolve().parent != self.parent.resolve() or self.path.is_symlink():
            raise ValueError("Temporary directory escaped the isolated workspace.")
        for path in self.path.iterdir():
            if not path.is_file() or path.is_symlink():
                raise ValueError("Unexpected entry in isolated database directory.")
            path.unlink()
        self.path.rmdir()

    def __exit__(self, *args):
        self.cleanup()


class ReferenceSandbox:
    """Independent sandbox biller ledger, authenticated and idempotent on disk."""

    def __init__(self, database, secret, *, drop_after_commit_once=False):
        if len(secret) < 32:
            raise ValueError("A signing secret of at least 32 characters is required.")
        self.database, self.secret = str(database), secret
        self.drop_after_commit_once = drop_after_commit_once
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS sandbox_charges (external_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, amount TEXT NOT NULL, provider_reference TEXT NOT NULL)")
        sandbox = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Tokens, signatures and biller payloads never enter access logs.

            def response(self, code, payload):
                body = canonical(payload)
                timestamp = str(int(utc().timestamp()))
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Provider-Timestamp", timestamp)
                self.send_header("X-Provider-Signature", signature(sandbox.secret, timestamp, "RESPONSE", self.path, body))
                self.end_headers()
                self.wfile.write(body)

            def authorized(self, body):
                return verify_signature(sandbox.secret, self.headers.get("X-Provider-Timestamp"),
                    self.headers.get("X-Provider-Signature"), self.command, self.path, body)

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self.response(400, {"error": "invalid_length"})
                if not 0 < length <= 32768:
                    return self.response(413, {"error": "body_too_large"})
                body = self.rfile.read(length)
                if self.path != "/v1/payment-intents" or not self.authorized(body):
                    return self.response(401, {"error": "invalid_signature"})
                try:
                    data = json.loads(body)
                    if (set(data) != {"external_id", "amount", "currency", "biller_reference", "authorization"}
                            or not re.fullmatch(r"[0-9a-f]{32}", data["external_id"])
                            or not isinstance(data["amount"], str) or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{2}", data["amount"])
                            or not Decimal("0") < Decimal(data["amount"]) <= Decimal("100000")
                            or data["currency"] != "BDT" or data["authorization"] != "explicit_confirmed_intent"
                            or not isinstance(data["biller_reference"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", data["biller_reference"])):
                        raise ValueError("invalid_schema")
                except (ValueError, TypeError, KeyError):
                    return self.response(422, {"error": "invalid_schema"})
                digest = hashlib.sha256(canonical(data)).hexdigest()
                with closing(sqlite3.connect(sandbox.database, timeout=10)) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    previous = connection.execute("SELECT payload_hash, amount, provider_reference FROM sandbox_charges WHERE external_id = ?", (data["external_id"],)).fetchone()
                    if previous and previous[0] != digest:
                        connection.rollback()
                        return self.response(409, {"error": "idempotency_conflict"})
                    reference = previous[2] if previous else "SANDBOX-" + uuid4().hex
                    if not previous:
                        connection.execute("INSERT INTO sandbox_charges VALUES (?, ?, ?, ?)", (data["external_id"], digest, data["amount"], reference))
                    connection.commit()
                if not previous and sandbox.drop_after_commit_once:
                    sandbox.drop_after_commit_once = False
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                return self.response(200 if previous else 201, sandbox.result(data["external_id"], data["amount"], reference))

            def do_GET(self):
                if not self.authorized(b""):
                    return self.response(401, {"error": "invalid_signature"})
                match = re.fullmatch(r"/v1/payment-intents/([0-9a-f]{32})", self.path)
                if not match:
                    return self.response(404, {"error": "not_found"})
                with closing(sqlite3.connect(sandbox.database)) as connection:
                    row = connection.execute("SELECT amount, provider_reference FROM sandbox_charges WHERE external_id = ?", (match[1],)).fetchone()
                return self.response(200, sandbox.result(match[1], *row)) if row else self.response(404, {"error": "not_found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = None

    @staticmethod
    def result(external_id, amount, reference):
        return {"external_id": external_id, "amount": amount, "currency": "BDT", "status": "SUCCEEDED",
                "sequence": 2, "provider_reference": reference}

    @property
    def url(self):
        return "http://127.0.0.1:" + str(self.server.server_port)

    def start(self):
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def close(self):
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()

    def charge_count(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT COUNT(*) FROM sandbox_charges").fetchone()[0]


def contract_demo(output=None):
    from cryptography.fernet import Fernet
    from werkzeug.serving import make_server
    from app import create_app
    from app.blueprints.api.routes import issue_token
    from app.domain.integration import ProviderIntent
    from app.domain.models import Transaction, User
    from app.extensions import db
    from app.services.provider_service import process_provider_outbox
    from config import DevelopmentConfig

    workspace = Path(__file__).resolve().parents[1]
    (workspace / "instance").mkdir(exist_ok=True)
    with IsolatedDirectory("provider-contract-") as directory:
        root = Path(directory)
        provider = ReferenceSandbox(root / "provider.sqlite", "reference-demo-" + uuid4().hex, drop_after_commit_once=True).start()
        class DemoConfig(DevelopmentConfig):
            DEBUG = False
            TESTING = True
            SEED_DEMO_DATA = False
            SCHEDULE_AUTO_RUN_ON_REQUEST = False
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + (root / "app.sqlite").as_posix()
            SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 10, "check_same_thread": False}}
            DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
            PROVIDER_BASE_URL = provider.url
            PROVIDER_SIGNING_SECRET = provider.secret
            PROVIDER_ALLOW_LOOPBACK_HTTP = True
            SECRET_KEY = uuid4().hex + uuid4().hex
        app = create_app(DemoConfig)
        with app.app_context():
            owner = User(full_name="Synthetic contract account", mobile="01700000001", verified=True, balance=Decimal("1000"))
            db.session.add(owner)
            db.session.commit()
            owner_id = owner.id
            _, token = issue_token(owner.id, {"provider:read", "provider:write"})
        api_server = make_server("127.0.0.1", 0, app, threaded=True)
        api_thread = Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        base = "http://127.0.0.1:" + str(api_server.server_port)
        def api(method, path, payload=None, extra=None):
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", **(extra or {})}
            raw = canonical(payload) if payload is not None else None
            try:
                response = urlopen(Request(base + path, data=raw, headers=headers, method=method), timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())
        try:
            payload = {"amount": "75.00", "biller_reference": "SYNTHETIC-DESCO-001", "confirmed": True}
            created_status, created = api("POST", "/api/v1/provider-intents", payload, {"Idempotency-Key": "contract-intent-001"})
            if created_status != 202:
                raise RuntimeError("Contract intent creation failed: " + json.dumps(created))
            intent_id = created["data"]["id"]
            replay_status, replay = api("POST", "/api/v1/provider-intents", payload, {"Idempotency-Key": "contract-intent-001"})
            conflict_status, _ = api("POST", "/api/v1/provider-intents", {**payload, "amount": "76.00"}, {"Idempotency-Key": "contract-intent-001"})
            with app.app_context():
                first_worker = process_provider_outbox()
                uncertain = db.session.get(ProviderIntent, intent_id).status
                second_worker = process_provider_outbox(now=utc() + timedelta(seconds=10))
                wallet_unchanged = db.session.get(User, owner_id).balance == Decimal("1000") and Transaction.query.count() == 0
            status_code, completed = api("GET", "/api/v1/provider-intents/" + intent_id)
            report = {"environment": "independent_reference_sandbox", "real_upay_connected": False,
                      "transport": "actual_loopback_HTTP", "submit_status": created_status,
                      "idempotent_replay": replay_status == 202 and replay["data"]["id"] == intent_id,
                      "payload_conflict_status": conflict_status, "first_worker": first_worker,
                      "dropped_response_outcome": uncertain, "recovery_worker": second_worker,
                      "final_status": completed["data"]["status"], "independent_provider_charges": provider.charge_count(),
                      "demo_wallet_unchanged": wallet_unchanged, "observed_at": utc().isoformat()}
            assert report["idempotent_replay"] and conflict_status == 409 and uncertain == "UNCERTAIN"
            assert report["final_status"] == "SUCCEEDED" and report["independent_provider_charges"] == 1 and wallet_unchanged
            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return report
        finally:
            api_server.shutdown()
            api_thread.join(timeout=5)
            api_server.server_close()
            provider.close()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--database", default="instance/reference-provider.sqlite")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.serve:
        sandbox = ReferenceSandbox(args.database, os.getenv("PROVIDER_SIGNING_SECRET", ""))
        # Rebind explicitly named loopback port; reference server never exposes a public listener.
        handler = sandbox.server.RequestHandlerClass
        sandbox.server.server_close()
        sandbox.server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
        print("Reference sandbox listening on " + sandbox.url)
        try:
            sandbox.server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            sandbox.server.server_close()
    else:
        print(json.dumps(contract_demo(args.output), indent=2))


if __name__ == "__main__":
    main()
