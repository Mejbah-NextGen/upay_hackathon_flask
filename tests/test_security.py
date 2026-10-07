import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app import create_app
from app.domain.models import User
from app.domain.security import OtpChallenge, RateLimitBucket, SecurityAuditEvent, TrustedSession
from app.extensions import db
from app.services.exceptions import AuthenticationError
from app.services.security_service import (audit_event, create_trusted_session, issue_otp_challenge,
    prune_expired_security, rate_limit, verify_audit_event, verify_otp_challenge)
from tests.helpers import AppTestCase, TestConfig


class SecurityTests(AppTestCase):
    def sign_in(self, code="123456"):
        self.assertEqual(self.client.post("/auth/login", data={"mobile": self.user.mobile}).status_code, 302)
        return self.client.post("/auth/otp", data={"otp": code})

    def test_headers_cache_request_ids_and_no_pii_in_audit(self):
        response = self.client.get("/auth/login", headers={"X-Request-ID": "injected-id"})
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn("script-src 'self' 'unsafe-inline'", response.headers["Content-Security-Policy"])
        request_id = response.headers["X-Request-ID"]
        self.assertRegex(request_id, r"^[a-f0-9]{32}$")
        event = SecurityAuditEvent.query.filter_by(request_id=request_id).one()
        self.assertTrue(verify_audit_event(event))
        self.assertNotIn("injected-id", event.details)
        self.assertNotIn(self.user.mobile, event.details)

    def test_csrf_failure_is_audited_and_does_not_move_money(self):
        self.login()
        self.app.config["WTF_CSRF_ENABLED"] = True
        original = self.user.balance
        response = self.client.post("/wallet/send-money", data={"amount": "10"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.balance, original)
        event = SecurityAuditEvent.query.filter_by(request_id=response.headers["X-Request-ID"]).one()
        self.assertEqual(event.result, "failed")

    def test_login_cookie_is_device_bound_and_server_revoked_on_logout(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 302)
        device_cookie = self.client.get_cookie("upay_device")
        self.assertIsNotNone(device_cookie)
        self.assertTrue(device_cookie.http_only)
        self.assertEqual(device_cookie.same_site, "Strict")
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(TrustedSession.query.count(), 1)
        session_cookie = self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"]).value
        device_value = device_cookie.value
        self.client.post("/auth/logout")
        db.session.expire_all()
        self.assertIsNotNone(TrustedSession.query.one().revoked_at)
        self.assertIsNone(self.client.get_cookie("upay_device"))
        replay = self.app.test_client()
        replay.set_cookie(self.app.config["SESSION_COOKIE_NAME"], session_cookie)
        replay.set_cookie("upay_device", device_value)
        self.assertEqual(replay.get("/").status_code, 302)

    def test_stolen_session_cookie_without_device_cookie_rejected(self):
        self.assertEqual(self.sign_in().status_code, 302)
        stolen = self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"]).value
        another = self.app.test_client()
        another.set_cookie(self.app.config["SESSION_COOKIE_NAME"], stolen)
        self.assertEqual(another.get("/").status_code, 302)
        with another.session_transaction() as data:
            self.assertNotIn("user_id", data)

    def test_device_tamper_expiry_and_user_binding(self):
        self.assertEqual(self.sign_in().status_code, 302)
        self.client.set_cookie("upay_device", "tampered")
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.sign_in().status_code, 302)
        # Expire every active browser session, avoiding equal-second ordering.
        TrustedSession.query.update({"expires_at": int(time.time()) - 1})
        db.session.commit()
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.sign_in().status_code, 302)
        peer = User(full_name="Peer", mobile="01799999123", balance=0)
        db.session.add(peer)
        db.session.commit()
        with self.client.session_transaction() as data:
            data["user_id"] = peer.id
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_production_requires_server_registry_and_real_delivery(self):
        self.app.config.update(SECURITY_PRODUCTION=True, REQUIRE_TRUSTED_SESSIONS=True,
            DEMO_OTP_ALLOWED=False, DEMO_BALANCES_ALLOWED=False, OTP_DELIVERY_ADAPTER=None)
        self.login()
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.client.post("/auth/login", data={"mobile": self.user.mobile})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(OtpChallenge.query.count(), 0)
        initial = User.query.count()
        response = self.client.post("/auth/signup", data={"full_name": "Secure Person", "mobile": "01788888999"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), initial)

    def test_malformed_identity_cleared_before_preference_queries(self):
        with self.client.session_transaction() as data:
            data["user_id"] = "not-an-integer"
            data.pop("language", None)
            data.pop("theme", None)
        with patch("app.extensions.db.session.get", wraps=db.session.get) as lookup:
            self.assertEqual(self.client.get("/").status_code, 302)
            self.assertFalse(any(len(call.args) > 1 and call.args[1] == "not-an-integer"
                for call in lookup.call_args_list))
        with self.client.session_transaction() as data:
            self.assertNotIn("user_id", data)

    def test_real_delivery_random_hash_expiry_and_one_use(self):
        delivered = []
        self.app.config.update(SECURITY_PRODUCTION=True, DEMO_OTP_ALLOWED=False,
            OTP_DELIVERY_ADAPTER=lambda mobile, code, challenge: delivered.append((mobile, code, challenge)) or True)
        challenge_id = issue_otp_challenge(self.user)
        _, code, recorded_id = delivered[-1]
        self.assertEqual(recorded_id, challenge_id)
        self.assertRegex(code, r"^\d{6}$")
        challenge = db.session.get(OtpChallenge, challenge_id)
        self.assertNotEqual(challenge.code_hash, code)
        self.assertTrue(verify_otp_challenge(challenge_id, self.user_id, code))
        with self.assertRaises(AuthenticationError):
            verify_otp_challenge(challenge_id, self.user_id, code)
        new_id = issue_otp_challenge(self.user)
        db.session.get(OtpChallenge, new_id).expires_at = int(time.time()) - 1
        db.session.commit()
        with self.assertRaises(AuthenticationError):
            verify_otp_challenge(new_id, self.user_id, delivered[-1][1])

    def test_attempt_bound_and_old_challenge_invalidated(self):
        self.app.config["OTP_MAX_ATTEMPTS"] = 2
        challenge_id = issue_otp_challenge(self.user)
        for _ in range(2):
            with self.assertRaises(AuthenticationError):
                verify_otp_challenge(challenge_id, self.user_id, "000000")
        with self.assertRaises(AuthenticationError):
            verify_otp_challenge(challenge_id, self.user_id, "123456")
        old = issue_otp_challenge(self.user)
        new = issue_otp_challenge(self.user)
        with self.assertRaises(AuthenticationError):
            verify_otp_challenge(old, self.user_id, "123456")
        self.assertTrue(verify_otp_challenge(new, self.user_id, "123456"))

    def test_delivery_failure_consumes_challenge_without_otp_disclosure(self):
        self.app.config.update(SECURITY_PRODUCTION=True, DEMO_OTP_ALLOWED=False,
            OTP_DELIVERY_ADAPTER=lambda *args: False)
        with self.assertRaises(AuthenticationError):
            issue_otp_challenge(self.user)
        challenge = OtpChallenge.query.one()
        self.assertFalse(challenge.delivered)
        self.assertIsNotNone(challenge.consumed_at)

    def test_production_signup_no_demo_credit_and_hidden_demo_code(self):
        delivered = []
        self.app.config.update(SECURITY_PRODUCTION=True, DEMO_OTP_ALLOWED=False,
            DEMO_BALANCES_ALLOWED=False,
            OTP_DELIVERY_ADAPTER=lambda mobile, code, challenge: delivered.append(code) or True)
        response = self.client.post("/auth/signup", data={"full_name": "Verified User", "mobile": "01788888999"})
        self.assertEqual(response.status_code, 302)
        user = User.query.filter_by(mobile="01788888999").one()
        self.assertEqual(user.balance, 0)
        self.assertFalse(user.verified)
        page = self.client.get("/auth/otp")
        self.assertNotIn(b"Demo OTP:", page.data)
        with self.client.session_transaction() as data:
            self.assertNotEqual(data.get("pending_mobile"), user.mobile)
        self.assertEqual(self.client.post("/auth/otp", data={"otp": delivered[-1]}).status_code, 302)
        db.session.refresh(user)
        self.assertTrue(user.verified)

    def test_auth_rate_limit_and_db_contains_only_hashed_identity(self):
        self.app.config["RATE_LIMITS"] = {"auth": (2, 60)}
        for _ in range(2):
            self.assertEqual(self.client.post("/auth/login", data={"mobile": self.user.mobile}).status_code, 302)
        response = self.client.post("/auth/login", data={"mobile": self.user.mobile})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        for bucket in RateLimitBucket.query.all():
            self.assertRegex(bucket.key_hash, r"^[a-f0-9]{64}$")
            self.assertNotIn(self.user.mobile, bucket.key_hash)

    def test_audit_is_transactional_allowlisted_signed_and_immutable(self):
        event = audit_event("wallet.debit", "success", self.user_id,
            {"reference": "TEST-1", "otp": "123456", "question": "private", "authorization": "secret"})
        db.session.commit()
        self.assertNotIn("private", event.details)
        self.assertNotIn("secret", event.details)
        self.assertNotIn("123456", event.details)
        self.assertTrue(verify_audit_event(event))
        event.result = "changed"
        with self.assertRaises(ValueError):
            db.session.commit()
        db.session.rollback()
        event = db.session.get(SecurityAuditEvent, event.id)
        db.session.delete(event)
        with self.assertRaises(ValueError):
            db.session.commit()
        db.session.rollback()
        rolled_back = audit_event("wallet.debit", "success", self.user_id)
        event_id = rolled_back.id
        db.session.rollback()
        self.assertIsNone(db.session.get(SecurityAuditEvent, event_id))

    def test_device_revocation_requires_owner(self):
        self.assertEqual(self.sign_in().status_code, 302)
        owner_session = TrustedSession.query.one()
        peer = User(full_name="Peer", mobile="01799999123", balance=0)
        db.session.add(peer)
        db.session.commit()
        with self.app.test_request_context():
            create_trusted_session(peer.id)
        peer_session = TrustedSession.query.filter_by(user_id=peer.id).one()
        self.assertEqual(self.client.post(f"/auth/devices/{peer_session.token_hash}/revoke").status_code, 302)
        db.session.refresh(peer_session)
        self.assertIsNone(peer_session.revoked_at)
        self.assertEqual(self.client.post(f"/auth/devices/{owner_session.token_hash}/revoke").status_code, 302)
        db.session.refresh(owner_session)
        self.assertIsNotNone(owner_session.revoked_at)

    def test_expired_security_cleanup_keeps_active_state_and_audit(self):
        now = int(time.time())
        self.assertTrue(rate_limit("expired-client", "api", limit=2))
        self.assertTrue(rate_limit("active-client", "api", limit=2))
        old_bucket = RateLimitBucket.query.first()
        old_bucket.expires_at = now
        challenge = issue_otp_challenge(self.user)
        db.session.get(OtpChallenge, challenge).expires_at = now
        with self.app.test_request_context():
            create_trusted_session(self.user_id)
        trusted = TrustedSession.query.one()
        trusted.expires_at = now
        audit_event("security.cleanup", "test", self.user_id)
        db.session.commit()
        audits_before = SecurityAuditEvent.query.count()
        self.assertEqual(prune_expired_security(now), {
            "rate_buckets": 1, "otp_challenges": 1, "trusted_sessions": 1})
        db.session.expire_all()
        self.assertEqual(RateLimitBucket.query.count(), 1)
        self.assertEqual(OtpChallenge.query.count(), 0)
        self.assertEqual(TrustedSession.query.count(), 0)
        self.assertEqual(SecurityAuditEvent.query.count(), audits_before)


class SharedRateLimitTests(AppTestCase):
    def test_quota_persists_across_app_instances_and_rollbacks(self):
        directory = Path.cwd() / "tmp" / "security-qa"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("limits-" + uuid.uuid4().hex + ".db")
        try:
            class FileConfig(TestConfig):
                SQLALCHEMY_DATABASE_URI = "sqlite:///" + path.as_posix()
                SEED_DEMO_DATA = False
            first, second = create_app(FileConfig), create_app(FileConfig)
            try:
                with first.app_context():
                    self.assertTrue(rate_limit("same-client", "api", limit=2))
                    db.session.rollback()
                with second.app_context():
                    self.assertTrue(rate_limit("same-client", "api", limit=2))
                    self.assertFalse(rate_limit("same-client", "api", limit=2))
                    with patch("app.services.security_service._now", return_value=int(time.time()) + 120):
                        self.assertTrue(rate_limit("same-client", "api", limit=2))
                def attempt(index):
                    app = first if index % 2 else second
                    with app.app_context():
                        return rate_limit("parallel-client", "api", limit=3, window_seconds=3600)
                with ThreadPoolExecutor(max_workers=8) as executor:
                    self.assertEqual(sum(executor.map(attempt, range(20))), 3)
                with first.app_context():
                    user = User(full_name="Concurrent OTP", mobile="01777777111", balance=0)
                    db.session.add(user)
                    db.session.commit()
                    otp_user_id = user.id
                def issue(index):
                    app = first if index % 2 else second
                    with app.app_context():
                        return issue_otp_challenge(db.session.get(User, otp_user_id))
                with ThreadPoolExecutor(max_workers=8) as executor:
                    challenge_ids = list(executor.map(issue, range(8)))
                with first.app_context():
                    self.assertEqual(len(set(challenge_ids)), 8)
                    self.assertEqual(OtpChallenge.query.filter_by(user_id=otp_user_id, consumed_at=None).count(), 1)
            finally:
                for app in (first, second):
                    with app.app_context():
                        db.session.remove()
                        db.engine.dispose()
        finally:
            path.unlink(missing_ok=True)
