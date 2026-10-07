"""Database-backed rate limits, bounded OTPs, device-bound sessions and safe audit.

Device binding proves possession of a second random HTTP-only cookie. It is not
hardware attestation or phishing-resistant MFA. No submitted message, OTP,
mobile, authorization header or IP address is retained in the audit records.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
import uuid

import click
from flask import current_app, g, has_request_context, jsonify, request, session
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.domain.security import OtpChallenge, RateLimitBucket, SecurityAuditEvent, TrustedSession
from app.extensions import db
from app.services.exceptions import AuthenticationError


DEFAULT_RATE_LIMITS = {"auth": (12, 60), "payments": (30, 60), "assistant": (20, 60), "api": (60, 60)}
AUDIT_DETAIL_KEYS = frozenset({"reference", "provider", "event_id", "category", "status_code", "job_id", "reason", "endpoint", "amount_band"})


def security_production():
    return bool(current_app.config.get("SECURITY_PRODUCTION", False))


def _now():
    return int(time.time())


def _digest(value, purpose="security"):
    key = str(current_app.config.get("SECURITY_HASH_KEY") or current_app.config["SECRET_KEY"]).encode()
    return hmac.new(key, (purpose + ":" + str(value)).encode(), hashlib.sha256).hexdigest()


def rate_limit(key, category, limit=None, window_seconds=None):
    """Atomically consume a fixed-window quota in PostgreSQL or SQLite.

    Uses a separate transaction so rejected requests still consume quota and
    rollback of a wallet operation cannot reset the rate limit. Do not invoke
    while a wallet write transaction is already open (SQLite single writer).
    """
    category = str(category)[:32]
    configured = current_app.config.get("RATE_LIMITS", DEFAULT_RATE_LIMITS).get(category, (60, 60))
    limit = int(configured[0] if limit is None else limit)
    window_seconds = int(configured[1] if window_seconds is None else window_seconds)
    if limit < 1 or window_seconds < 1:
        return False
    now = _now()
    values = {"key_hash": _digest(key, "rate"), "category": category,
              "window_start": now - now % window_seconds, "hits": 1,
              "expires_at": now - now % window_seconds + window_seconds}
    table = RateLimitBucket.__table__
    dialect = db.engine.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise RuntimeError("Shared rate limiting requires SQLite or PostgreSQL.")
    statement = (postgres_insert if dialect == "postgresql" else sqlite_insert)(table).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key_hash, table.c.category, table.c.window_start],
        set_={"hits": table.c.hits + 1}, where=table.c.hits < limit,
    ).returning(table.c.hits)
    with db.engine.begin() as connection:
        hits = connection.execute(statement).scalar_one_or_none()
    return hits is not None


def _audit_values(action, result, user_id=None, metadata=None):
    # Only internal operation identifiers and allowlisted bounded details belong
    # in logs. Request contents and credential-shaped values never enter here.
    if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", str(action)):
        raise ValueError("Audit action must be an internal identifier.")
    if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,40}", str(result)):
        raise ValueError("Audit result must be an internal identifier.")
    details = {}
    for key, value in (metadata or {}).items():
        if key in AUDIT_DETAIL_KEYS and isinstance(value, (str, int, bool)):
            if isinstance(value, str):
                value = re.sub(r"[^a-zA-Z0-9_.:/-]", "_", value[:120])
            details[key] = value
    values = {"id": uuid.uuid4().hex, "created_at": _now(),
              "request_id": getattr(g, "request_id", "") if has_request_context() else "",
              "user_id": user_id if isinstance(user_id, int) else None,
              "action": action, "result": result,
              "details": json.dumps(details, sort_keys=True, separators=(",", ":"))}
    values["signature"] = _sign_audit(values)
    return values


def _sign_audit(values):
    fields = {key: values[key] for key in ("id", "created_at", "request_id", "user_id", "action", "result", "details")}
    key = str(current_app.config.get("AUDIT_SIGNING_KEY") or current_app.config["SECRET_KEY"]).encode()
    return hmac.new(key, json.dumps(fields, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()


def audit_event(action, result, user_id=None, metadata=None):
    """Append to the caller transaction; money movement and audit commit together."""
    event = SecurityAuditEvent(**_audit_values(action, result, user_id, metadata))
    db.session.add(event)
    return event


def verify_audit_event(event):
    values = {key: getattr(event, key) for key in ("id", "created_at", "request_id", "user_id", "action", "result", "details")}
    return hmac.compare_digest(event.signature, _sign_audit(values))


def require_otp_delivery():
    if security_production() and (current_app.config.get("DEMO_OTP_ALLOWED", False)
                                  or not callable(current_app.config.get("OTP_DELIVERY_ADAPTER"))):
        raise AuthenticationError("Secure verification is unavailable. Please try again later.")


def issue_otp_challenge(user):
    require_otp_delivery()
    now = _now()
    challenge_id = secrets.token_urlsafe(32)
    demo = bool(current_app.config.get("DEMO_OTP_ALLOWED", True)) and not security_production()
    code = str(current_app.config["DEMO_OTP"]) if demo else f"{secrets.randbelow(1_000_000):06d}"
    from app.domain.models import User
    # Serialize issuance on an existing account row, including when there are
    # no old challenges to lock. PostgreSQL's UPDATE of zero matching challenge
    # rows alone does not prevent two concurrent first challenges being active.
    locked = db.session.execute(update(User).where(User.id == user.id)
        .values(verified=User.verified), execution_options={"synchronize_session": False}).rowcount
    if locked != 1:
        db.session.rollback()
        raise AuthenticationError("Unable to start verification. Please sign in again.")
    # Replacing a challenge invalidates older challenges for the account.
    db.session.execute(update(OtpChallenge).where(OtpChallenge.user_id == user.id,
        OtpChallenge.consumed_at.is_(None)).values(consumed_at=now))
    challenge = OtpChallenge(id=challenge_id, user_id=user.id,
        code_hash=_digest(challenge_id + ":" + code, "otp"),
        expires_at=now + int(current_app.config.get("OTP_TTL_SECONDS", 300)), delivered=demo)
    db.session.add(challenge)
    db.session.commit()
    if not demo:
        adapter = current_app.config.get("OTP_DELIVERY_ADAPTER")
        try:
            delivered = callable(adapter) and adapter(user.mobile, code, challenge_id) is True
        except Exception:
            delivered = False
        if not delivered:
            challenge.consumed_at = now
            audit_event("auth.otp_delivery", "failed", user.id)
            db.session.commit()
            raise AuthenticationError("Secure verification is unavailable. Please try again later.")
        challenge.delivered = True
    audit_event("auth.otp_delivery", "demo" if demo else "sent", user.id)
    db.session.commit()
    return challenge_id


def verify_otp_challenge(challenge_id, user_id, submitted_code):
    now = _now()
    maximum = int(current_app.config.get("OTP_MAX_ATTEMPTS", 5))
    with db.engine.begin() as connection:
        # Count attempts before checking the code, atomically across workers.
        statement = update(OtpChallenge).where(
            OtpChallenge.id == challenge_id, OtpChallenge.user_id == user_id,
            OtpChallenge.delivered.is_(True), OtpChallenge.consumed_at.is_(None),
            OtpChallenge.expires_at > now, OtpChallenge.attempts < maximum,
        ).values(attempts=OtpChallenge.attempts + 1).returning(OtpChallenge.code_hash)
        expected = connection.execute(statement).scalar_one_or_none()
        actual = _digest(str(challenge_id) + ":" + str(submitted_code or "").strip(), "otp")
        valid = expected is not None and hmac.compare_digest(expected, actual)
        if valid:
            consumed = connection.execute(update(OtpChallenge).where(
                OtpChallenge.id == challenge_id, OtpChallenge.consumed_at.is_(None)
            ).values(consumed_at=now)).rowcount
            valid = consumed == 1
    if not valid:
        raise AuthenticationError("Invalid or expired verification code. Please sign in again after repeated failures.")
    return True


def create_trusted_session(user_id):
    token, device = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = _now()
    ttl = int(current_app.config.get("AUTH_SESSION_TTL_SECONDS", 3600))
    db.session.add(TrustedSession(token_hash=_digest(token, "session"), user_id=user_id,
        device_hash=_digest(device, "device"), agent_hash=_digest(request.user_agent.string, "agent"),
        created_at=now, expires_at=now + ttl))
    audit_event("auth.session", "created", user_id)
    db.session.commit()
    session["auth_session"] = token
    g.security_device_cookie = device


def validate_trusted_session(user_id):
    token = session.get("auth_session")
    if not token:
        required = current_app.config.get("REQUIRE_TRUSTED_SESSIONS", security_production())
        if required:
            session.pop("user_id", None)
            g.security_auth_failure = "untrusted_session"
        return not required
    device = request.cookies.get(current_app.config.get("DEVICE_COOKIE_NAME", "upay_device"), "")
    trusted = db.session.get(TrustedSession, _digest(token, "session"))
    valid = bool(trusted and trusted.user_id == user_id and trusted.revoked_at is None
        and trusted.expires_at > _now() and device
        and hmac.compare_digest(trusted.device_hash, _digest(device, "device"))
        and hmac.compare_digest(trusted.agent_hash, _digest(request.user_agent.string, "agent")))
    if not valid:
        session.pop("user_id", None)
        session.pop("auth_session", None)
        g.security_delete_device_cookie = True
        g.security_auth_failure = "untrusted_session"
    return valid


def revoke_trusted_session(token_hash, user_id):
    changed = db.session.execute(update(TrustedSession).where(
        TrustedSession.token_hash == token_hash, TrustedSession.user_id == user_id,
        TrustedSession.revoked_at.is_(None)).values(revoked_at=_now())).rowcount
    if changed:
        audit_event("auth.session", "revoked", user_id)
    db.session.commit()
    return bool(changed)


def revoke_current_session():
    token, user_id = session.get("auth_session"), session.get("user_id")
    if token and user_id:
        revoke_trusted_session(_digest(token, "session"), user_id)
    g.security_delete_device_cookie = True


def prune_expired_security(now=None):
    """Delete expired operational state in a separate transaction, never audit."""
    expires_before = _now() if now is None else int(now.timestamp() if hasattr(now, "timestamp") else now)
    models = {"rate_buckets": RateLimitBucket, "otp_challenges": OtpChallenge, "trusted_sessions": TrustedSession}
    with db.engine.begin() as connection:
        counts = {key: connection.execute(delete(model).where(model.expires_at <= expires_before)).rowcount
                  for key, model in models.items()}
    return counts


def install_security(app):
    app.config.setdefault("DEMO_OTP_ALLOWED", not app.config.get("SECURITY_PRODUCTION", False))
    app.config.setdefault("REQUIRE_TRUSTED_SESSIONS", bool(app.config.get("SECURITY_PRODUCTION", False)))
    app.config.setdefault("RATE_LIMITS", DEFAULT_RATE_LIMITS.copy())
    app.config.setdefault("AUTH_SESSION_TTL_SECONDS", 3600)
    app.config.setdefault("OTP_TTL_SECONDS", 300)
    app.config.setdefault("OTP_MAX_ATTEMPTS", 5)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if app.config.get("SECURITY_PRODUCTION", False):
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.before_request
    def security_boundary():
        g.request_id = uuid.uuid4().hex  # never trust caller-provided IDs in logs
        g.request_started = time.monotonic()
        g.security_device_cookie = None
        g.security_delete_device_cookie = False
        g.security_auth_failure = None
        if request.endpoint == "static":
            return None
        user_id = session.get("user_id")
        if user_id is not None and (not isinstance(user_id, int) or isinstance(user_id, bool) or user_id < 1):
            # Run before display-preference queries and other middleware; an
            # invalid typed identity must not reach a PostgreSQL integer bind.
            session.pop("user_id", None)
            session.pop("auth_session", None)
            g.security_delete_device_cookie = True
            g.security_auth_failure = "invalid_identity"
        category = None
        if request.path.startswith("/api/"):
            category = "api"
        elif request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.endpoint in {"auth.login_post", "auth.signup", "auth.otp"}:
                category = "auth"
            elif request.blueprint == "assistant":
                category = "assistant"
            elif request.blueprint in {"wallet", "payments", "operations"}:
                category = "payments"
        if category:
            key = "ip:" + (request.remote_addr or "unknown")
            if not rate_limit(key, category):
                error = {"code": "rate_limited", "message": "Too many requests. Please try again shortly."}
                response = jsonify({"error": error, "request_id": g.request_id})
                response.status_code = 429
                response.headers["Retry-After"] = str(app.config["RATE_LIMITS"].get(category, (60, 60))[1])
                return response
            if category == "auth" and request.form.get("mobile"):
                # Normalize obvious spelling changes while never retaining PII.
                digits = re.sub(r"\D", "", request.form["mobile"])[-11:]
                if not rate_limit("account:" + digits, "auth"):
                    response = jsonify({"error": {"code": "rate_limited", "message": "Too many verification requests."}, "request_id": g.request_id})
                    response.status_code = 429
                    response.headers["Retry-After"] = "60"
                    return response
        return None

    @app.after_request
    def secure_response(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if app.config.get("SECURITY_PRODUCTION", False):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
        cookie_name = app.config.get("DEVICE_COOKIE_NAME", "upay_device")
        cookie_options = {"secure": bool(app.config.get("SESSION_COOKIE_SECURE")), "httponly": True, "samesite": "Strict", "path": "/"}
        if getattr(g, "security_device_cookie", None):
            response.set_cookie(cookie_name, g.security_device_cookie,
                max_age=app.config["AUTH_SESSION_TTL_SECONDS"], **cookie_options)
        elif getattr(g, "security_delete_device_cookie", False):
            response.delete_cookie(cookie_name, **cookie_options)
        if request.endpoint != "static":
            outcome = getattr(g, "security_auth_failure", None) or (
                "denied" if response.status_code in {401, 403, 429} else "failed" if response.status_code >= 400 else "success")
            actor = getattr(g, "api_user_id", None) if request.path.startswith("/api/") else session.get("user_id")
            values = _audit_values("http.request", outcome, actor,
                {"status_code": response.status_code, "endpoint": request.endpoint or "unmatched"})
            # No application session commit: a failed wallet transaction remains
            # rolled back. Request audit persists independently, including denials.
            try:
                with db.engine.begin() as connection:
                    connection.execute(SecurityAuditEvent.__table__.insert().values(**values))
            except SQLAlchemyError:
                # Preserve readiness/error responses during database outages.
                # Ledger audit still fails closed in the money transaction.
                app.logger.error(json.dumps({"event": "audit.unavailable", "request_id": values["request_id"]}))
            app.logger.info(json.dumps({"event": "http.request", "request_id": values["request_id"],
                "endpoint": request.endpoint or "unmatched", "status": response.status_code,
                "duration_ms": round((time.monotonic() - getattr(g, "request_started", time.monotonic())) * 1000)}))
        return response

    @app.cli.command("security-prune")
    def prune_security_state():
        """Remove expired quota/challenge/session state; audit history is preserved."""
        click.echo(json.dumps(prune_expired_security(), sort_keys=True))
