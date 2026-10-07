"""API controls and signed provider outcomes against an independent HTTP ledger."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

from app import create_app
from app.blueprints.api.routes import issue_token
from app.domain.integration import ApiIdempotency, ApiToken, ProviderIntent, ProviderOutbox, ProviderWebhook
from app.domain.models import Transaction, User
from app.domain.operations import ScheduledPayment
from app.extensions import db
from app.services.provider_service import (
    ProviderUnavailable, ReferenceHTTPAdapter, canonical, process_provider_outbox, signature, utc,
)
from app.services.schedule_service import scheduling_window
from scripts.provider_contract_demo import IsolatedDirectory, ReferenceSandbox
from tests.helpers import AppTestCase, TestConfig


class ApiTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.directory = IsolatedDirectory("api-provider-")
        self.provider = ReferenceSandbox(Path(self.directory.name) / "provider.sqlite", "test-signing-" + uuid4().hex).start()
        self.app.config.update(PROVIDER_BASE_URL=self.provider.url, PROVIDER_SIGNING_SECRET=self.provider.secret,
                               PROVIDER_ALLOW_LOOPBACK_HTTP=True, DATA_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                               RATE_LIMITS={"api": (10000, 60)}, WTF_CSRF_ENABLED=True)
        self.other = User(full_name="Other synthetic owner", mobile="01811223344", balance=Decimal("50"), verified=True)
        db.session.add(self.other)
        db.session.commit()
        self.other_id = self.other.id
        self.token, self.secret = issue_token(self.user_id, {"balance:read", "insights:read", "schedules:read", "schedules:write", "provider:read", "provider:write"})
        self.headers = {"Authorization": "Bearer " + self.secret}

    def tearDown(self):
        self.provider.close()
        self.directory.cleanup()
        super().tearDown()

    def post(self, path, data, key="test-request-0001", headers=None):
        return self.client.post(path, json=data, headers={**self.headers, "Idempotency-Key": key, **(headers or {})})

    def intent(self, key="test-provider-0001", amount="25.00"):
        response = self.post("/api/v1/provider-intents", {"amount": amount, "biller_reference": "SYNTHETIC-123", "confirmed": True}, key)
        self.assertEqual(response.status_code, 202, response.json)
        return response.json["data"]["id"]

    def webhook(self, intent_id, *, sequence=2, status="SUCCEEDED", event_id="reference-event-0001", amount="25.00", timestamp=None, extra=None):
        payload = {"event_id": event_id, "external_id": intent_id, "amount": amount, "currency": "BDT",
                   "status": status, "sequence": sequence, "provider_reference": "SANDBOX-confirmed-001"}
        raw = canonical({**payload, **(extra or {})})
        stamp = str(int(utc().timestamp())) if timestamp is None else str(timestamp)
        path = "/api/v1/provider-webhooks/reference"
        headers = {"Content-Type": "application/json", "X-Provider-Timestamp": stamp,
                   "X-Provider-Signature": signature(self.provider.secret, stamp, "POST", path, raw)}
        return self.client.post(path, data=raw, headers=headers)

    def schedule_data(self):
        return {"kind": "SEND_MONEY", "amount": "50.00", "recipient_number": self.other.mobile,
                "due_date": scheduling_window()[0].isoformat(), "frequency": "ONE_TIME", "confirmed": True}

    def test_cookie_is_never_api_authority_and_valid_token_needs_no_csrf(self):
        self.login()
        response = self.client.get("/api/v1/balance")
        self.assertEqual(response.status_code, 401)
        self.assertIn("WWW-Authenticate", response.headers)
        self.assertEqual(self.client.get("/api/v1/balance", headers=self.headers).json["data"]["balance"], "1000.00")
        self.assertEqual(self.post("/api/v1/schedules", self.schedule_data()).status_code, 201)
        self.assertEqual(self.client.post("/schedules", data={}).status_code, 400)

    def test_token_only_digest_scopes_expiration_and_revocation(self):
        self.assertEqual(self.token.secret_hash, hashlib.sha256(self.secret.encode()).hexdigest())
        self.assertNotIn(self.secret, self.token.secret_hash)
        _, limited = issue_token(self.user_id, {"balance:read"})
        self.assertEqual(self.client.get("/api/v1/schedules", headers={"Authorization": "Bearer " + limited}).status_code, 403)
        self.token.expires_at = utc() - timedelta(seconds=1)
        db.session.commit()
        self.assertEqual(self.client.get("/api/v1/balance", headers=self.headers).status_code, 401)
        self.token.expires_at = utc() + timedelta(days=1)
        self.token.revoked_at = utc()
        db.session.commit()
        self.assertEqual(self.client.get("/api/v1/balance", headers=self.headers).status_code, 401)

    def test_revocation_cli_and_token_ttl_bounds(self):
        with self.assertRaises(ValueError):
            issue_token(self.user_id, {"balance:read"}, days=31)
        result = self.app.test_cli_runner().invoke(args=["api-token", "revoke", "--token-id", str(self.token.id)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.client.get("/api/v1/balance", headers=self.headers).status_code, 401)

    def test_api_read_only_even_when_session_is_attached(self):
        self.login()
        row = ScheduledPayment(user_id=self.user_id, kind="SEND_MONEY", amount=Decimal("10"),
            recipient_number=self.other.mobile, due_at=utc() - timedelta(days=1), recurrence_group=uuid4().hex)
        db.session.add(row)
        db.session.commit()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = True
        self.assertEqual(self.client.get("/api/v1/balance", headers=self.headers).status_code, 200)
        self.assertEqual(db.session.get(ScheduledPayment, row.id).status, "SCHEDULED")
        self.assertEqual(Transaction.query.count(), 0)

    def test_schema_bounds_and_duplicate_keys(self):
        tests = [({"amount": 25, "biller_reference": "SYNTHETIC", "confirmed": True}, 422),
                 ({"amount": "NaN", "biller_reference": "SYNTHETIC", "confirmed": True}, 422),
                 ({"amount": "25.001", "biller_reference": "SYNTHETIC", "confirmed": True}, 422),
                 ({"amount": "25.00", "biller_reference": "SYNTHETIC", "confirmed": False}, 422),
                 ({"amount": "25.00", "biller_reference": "SYNTHETIC", "confirmed": True, "user_id": self.other_id}, 422)]
        for data, status in tests:
            self.assertEqual(self.post("/api/v1/provider-intents", data).status_code, status)
        response = self.client.post("/api/v1/provider-intents", data='{"amount":"25.00","amount":"26.00"}',
                                    headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/v1/provider-intents", data="x" * 32769,
                                    headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.client.get("/api/v1/schedules?limit=101", headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/schedules?after=-1", headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/schedules?limit=1&limit=2", headers=self.headers).status_code, 400)

    def test_schedule_idempotency_is_payload_bound_and_encrypted(self):
        data = self.schedule_data()
        previous_count = ScheduledPayment.query.filter_by(user_id=self.user_id).count()
        first = self.post("/api/v1/schedules", data)
        second = self.post("/api/v1/schedules", data)
        self.assertEqual(first.status_code, 201, first.json)
        self.assertEqual(second.json["data"], first.json["data"])
        self.assertEqual(ScheduledPayment.query.filter_by(user_id=self.user_id).count(), previous_count + 1)
        self.assertEqual(self.post("/api/v1/schedules", {**data, "amount": "60.00"}).status_code, 409)
        record = ApiIdempotency.query.filter_by(token_id=self.token.id).one()
        self.assertTrue(record.response_json.startswith("enc:v1:"))
        self.assertNotIn(self.other.mobile, record.response_json)

    def test_validation_rolls_back_idempotency_claim(self):
        bad = self.post("/api/v1/schedules", {**self.schedule_data(), "recipient_number": "invalid"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(ApiIdempotency.query.count(), 0)
        self.assertEqual(self.post("/api/v1/schedules", self.schedule_data()).status_code, 201)

    def test_owner_scoped_schedules_provider_intents_and_cursor(self):
        intent_id = self.intent()
        created = self.post("/api/v1/schedules", self.schedule_data()).json["data"]["items"][0]
        _, other_secret = issue_token(self.other_id, {"provider:read", "schedules:read", "schedules:write"})
        other_headers = {"Authorization": "Bearer " + other_secret}
        self.assertEqual(self.client.get("/api/v1/provider-intents/" + intent_id, headers=other_headers).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/schedules", headers=other_headers).json["data"]["items"], [])
        self.assertEqual(self.client.post(f"/api/v1/schedules/{created['id']}/cancel", json={}, headers={**other_headers, "Idempotency-Key": "other-cancel-0001"}).status_code, 404)
        for number in range(2):
            self.post("/api/v1/schedules", self.schedule_data(), key="schedule-page-" + str(number))
        page = self.client.get("/api/v1/schedules?limit=1", headers=self.headers).json["data"]
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["next_cursor"], page["items"][0]["id"])
        next_page = self.client.get(f"/api/v1/schedules?limit=1&after={page['next_cursor']}", headers=self.headers).json["data"]
        self.assertGreater(next_page["items"][0]["id"], page["items"][0]["id"])

    def test_provider_disabled_live_and_missing_configuration(self):
        self.assertEqual(self.post("/api/v1/provider-intents", {"provider": "upay", "amount": "25.00", "biller_reference": "SYNTHETIC", "confirmed": True}).status_code, 422)
        self.app.config["PROVIDER_BASE_URL"] = ""
        self.assertEqual(self.post("/api/v1/provider-intents", {"amount": "25.00", "biller_reference": "SYNTHETIC", "confirmed": True}).status_code, 503)
        self.assertEqual(ProviderIntent.query.count(), 0)
        self.assertEqual(ApiIdempotency.query.count(), 0)

    def test_signed_http_provider_independent_ledger_and_encryption(self):
        intent_id = self.intent()
        intent = db.session.get(ProviderIntent, intent_id)
        self.assertTrue(intent.biller_reference.startswith("enc:v1:"))
        self.assertEqual(process_provider_outbox()["completed"], 1)
        self.assertEqual(self.provider.charge_count(), 1)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "SUCCEEDED")
        self.assertEqual(db.session.get(User, self.user_id).balance, Decimal("1000"))
        self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(process_provider_outbox()["claimed"], 0)

    def test_network_uncertainty_reconciles_without_double_charge(self):
        self.provider.drop_after_commit_once = True
        intent_id = self.intent()
        first = process_provider_outbox()
        self.assertEqual(first["retrying"], 1)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "UNCERTAIN")
        self.assertEqual(self.provider.charge_count(), 1)
        second = process_provider_outbox(now=utc() + timedelta(seconds=10))
        self.assertEqual(second["completed"], 1)
        self.assertEqual(self.provider.charge_count(), 1)

    def test_crashed_dispatch_lease_is_recovered(self):
        intent_id = self.intent()
        intent = db.session.get(ProviderIntent, intent_id)
        ReferenceHTTPAdapter().submit(intent)  # Remote commit happened before the worker died.
        job = ProviderOutbox.query.filter_by(intent_id=intent_id).one()
        job.status, job.attempts, job.lease_token = "PROCESSING", 1, uuid4().hex
        job.lease_until = utc() - timedelta(seconds=1)
        db.session.commit()
        self.assertEqual(process_provider_outbox()["completed"], 1)
        self.assertEqual(self.provider.charge_count(), 1)

    def test_exhausted_network_retries_require_review_no_false_failure(self):
        intent_id = self.intent()
        self.app.config["PROVIDER_MAX_ATTEMPTS"] = 1
        with patch.object(ReferenceHTTPAdapter, "submit", side_effect=ProviderUnavailable("transport_uncertain")):
            self.assertEqual(process_provider_outbox()["review_required"], 1)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "REVIEW_REQUIRED")
        self.assertEqual(ProviderOutbox.query.filter_by(intent_id=intent_id).one().status, "REVIEW_REQUIRED")
        self.assertEqual(Transaction.query.count(), 0)
        result = self.app.test_cli_runner().invoke(args=["provider-reconcile", "--intent-id", intent_id])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(process_provider_outbox()["completed"], 1)
        self.assertEqual(self.provider.charge_count(), 1)

    def test_bad_signed_response_cannot_create_success(self):
        intent_id = self.intent()
        # Simulate a compromised/incorrect response while retaining the real HTTP request.
        with patch("app.services.provider_service.verify_signature", return_value=False):
            outcome = process_provider_outbox()
        self.assertEqual(outcome["retrying"], 1)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "UNCERTAIN")
        self.assertEqual(Transaction.query.count(), 0)
        self.assertEqual(process_provider_outbox(now=utc() + timedelta(seconds=10))["completed"], 1)
        self.assertEqual(self.provider.charge_count(), 1)

    def test_unexpected_adapter_fault_is_bounded_and_redacted(self):
        intent_id = self.intent()
        with patch.object(ReferenceHTTPAdapter, "submit", side_effect=RuntimeError("sensitive-upstream-payload")):
            self.assertEqual(process_provider_outbox()["retrying"], 1)
        self.assertEqual(ProviderOutbox.query.filter_by(intent_id=intent_id).one().last_error, "worker_error")
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "UNCERTAIN")

    def test_financial_health_is_local_advisory_and_token_scoped(self):
        before = Transaction.query.count()
        response = self.client.get("/api/v1/financial-health", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["data"]["advisory_only"])
        self.assertEqual(response.json["data"]["balance"], "1000.00")
        self.assertEqual(Transaction.query.count(), before)

    def test_webhook_signature_freshness_and_field_binding(self):
        intent_id = self.intent()
        self.assertEqual(self.client.post("/api/v1/provider-webhooks/reference", json={}).status_code, 401)
        self.assertEqual(self.webhook(intent_id, timestamp=int(utc().timestamp()) - 301).status_code, 401)
        self.assertEqual(self.webhook(intent_id, amount="25.01").status_code, 409)
        self.assertEqual(ProviderWebhook.query.count(), 0)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "QUEUED")

    def test_signed_webhook_rejects_array_or_object_scalar_fields(self):
        intent_id = self.intent()
        for field in ("external_id", "status", "amount", "currency", "sequence", "provider_reference"):
            for bad in ([], {}):
                with self.subTest(field=field, bad=bad):
                    response = self.webhook(intent_id, event_id="malformed-scalar-" + field, extra={field: bad})
                    self.assertIn(response.status_code, {409, 422}, response.json)
                    self.assertEqual(ProviderWebhook.query.count(), 0)
                    self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "QUEUED")

    def test_duplicate_webhook_and_out_of_order_event_are_harmless(self):
        intent_id = self.intent()
        self.assertEqual(self.webhook(intent_id).status_code, 200)
        duplicate = self.webhook(intent_id)
        self.assertTrue(duplicate.json["data"]["duplicate"])
        stale = self.webhook(intent_id, status="PENDING", sequence=1, event_id="reference-event-stale")
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "SUCCEEDED")
        self.assertEqual(self.webhook(intent_id, status="FAILED", sequence=3, event_id="reference-event-conflict").status_code, 409)
        self.assertEqual(self.webhook(intent_id, status="FAILED").status_code, 409)
        self.assertEqual(ProviderWebhook.query.count(), 2)

    def test_equal_sequence_changed_result_cannot_finish_pending_outbox(self):
        intent_id = self.intent()
        self.assertEqual(self.webhook(intent_id, status="PENDING", sequence=2).status_code, 200)
        conflict = self.webhook(intent_id, status="SUCCEEDED", sequence=2, event_id="same-sequence-terminal-conflict")
        self.assertEqual(conflict.status_code, 409)
        changed_reference = self.webhook(intent_id, status="PENDING", sequence=2, event_id="same-sequence-reference-conflict",
                                        extra={"provider_reference": "SANDBOX-changed-reference"})
        self.assertEqual(changed_reference.status_code, 409)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "PENDING")
        self.assertEqual(ProviderOutbox.query.filter_by(intent_id=intent_id).one().status, "PENDING")
        self.assertEqual(ProviderWebhook.query.count(), 1)
        self.assertEqual(self.webhook(intent_id, status="SUCCEEDED", sequence=3, event_id="new-sequence-success").status_code, 200)
        self.assertEqual(db.session.get(ProviderIntent, intent_id).status, "SUCCEEDED")
        self.assertEqual(ProviderOutbox.query.filter_by(intent_id=intent_id).one().status, "DONE")

    def test_uniform_errors_rate_limit_and_request_ids(self):
        response = self.client.get("/api/v1/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["X-Request-ID"], response.json["request_id"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("private", response.headers["Cache-Control"])
        with patch("app.services.security_service.rate_limit", return_value=False):
            response = self.client.get("/api/v1/balance", headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertIn("request_id", response.json)


class ApiConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = IsolatedDirectory("api-races-")
        root = Path(self.directory.name)
        self.provider = ReferenceSandbox(root / "provider.sqlite", "test-race-secret-" + uuid4().hex).start()
        provider = self.provider
        class RaceConfig(TestConfig):
            SEED_DEMO_DATA = False
            SCHEDULE_AUTO_RUN_ON_REQUEST = False
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + (root / "app.sqlite").as_posix()
            SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15, "check_same_thread": False}}
            PROVIDER_BASE_URL = provider.url
            PROVIDER_SIGNING_SECRET = provider.secret
            PROVIDER_ALLOW_LOOPBACK_HTTP = True
            RATE_LIMITS = {"api": (10000, 60)}
        self.app = create_app(RaceConfig)
        with self.app.app_context():
            owner = User(full_name="Synthetic concurrent owner", mobile="01700000002", balance=Decimal("1000"))
            db.session.add(owner)
            db.session.commit()
            self.owner_id = owner.id
            _, self.secret = issue_token(owner.id, {"provider:read", "provider:write"})

    def tearDown(self):
        self.provider.close()
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def test_concurrent_same_key_creates_one_intent_and_one_outbox(self):
        barrier = Barrier(2)
        def submit():
            with self.app.test_client() as client:
                barrier.wait(timeout=10)
                response = client.post("/api/v1/provider-intents", json={"amount": "25.00", "biller_reference": "SYNTHETIC-RACE", "confirmed": True},
                    headers={"Authorization": "Bearer " + self.secret, "Idempotency-Key": "concurrent-intent-001"})
                return response.status_code, response.json
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual([item[0] for item in results], [202, 202], results)
        self.assertEqual(results[0][1]["data"]["id"], results[1][1]["data"]["id"])
        with self.app.app_context():
            self.assertEqual(ProviderIntent.query.count(), 1)
            self.assertEqual(ProviderOutbox.query.count(), 1)

    def test_concurrent_workers_cannot_dispatch_one_job_twice(self):
        with self.app.test_client() as client:
            response = client.post("/api/v1/provider-intents", json={"amount": "25.00", "biller_reference": "SYNTHETIC-RACE", "confirmed": True},
                headers={"Authorization": "Bearer " + self.secret, "Idempotency-Key": "concurrent-worker-001"})
            self.assertEqual(response.status_code, 202, response.json)
        barrier = Barrier(2)
        def worker():
            with self.app.app_context():
                barrier.wait(timeout=10)
                return process_provider_outbox()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(row["claimed"] for row in results), 1)
        self.assertEqual(self.provider.charge_count(), 1)
