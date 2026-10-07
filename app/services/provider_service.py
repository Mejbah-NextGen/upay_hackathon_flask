"""Signed reference-provider boundary with durable, recoverable dispatch.

This is a sandbox protocol, not an official upay API. Intent completion never
debits the demo wallet. Unknown network outcomes are reconciled with the same
external key, and are not converted into successful wallet transactions.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from http.client import HTTPException
import hmac
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from flask import current_app
from sqlalchemy import and_, or_, update
from sqlalchemy.exc import IntegrityError

from app.domain.integration import ProviderIntent, ProviderOutbox, ProviderWebhook
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.encryption_service import decrypt_text, encrypt_text


TERMINAL = {"SUCCEEDED", "FAILED"}


class ProviderUnavailable(Exception):
    pass


class ProviderProtocolError(Exception):
    pass


def utc(value=None):
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def signature(secret, timestamp, method, path, body):
    message = str(timestamp).encode() + b"." + method.encode() + b"." + path.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(secret, timestamp, supplied, method, path, body, *, now=None):
    if not isinstance(secret, str) or len(secret) < 32 or len(str(supplied)) != 64:
        return False
    try:
        stamp = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(utc(now).timestamp()) - stamp) > 300:
        return False
    return hmac.compare_digest(signature(secret, str(stamp), method, path, body), str(supplied))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class UpayAdapter:
    """Activation requires the Bangladesh provider's official contract and keys."""

    def __init__(self, *args, **kwargs):
        raise ProviderUnavailable("Official Bangladesh upay integration is not configured; live rails are disabled.")


class ReferenceHTTPAdapter:
    def __init__(self):
        self.base_url = current_app.config.get("PROVIDER_BASE_URL", "").rstrip("/")
        self.secret = current_app.config.get("PROVIDER_SIGNING_SECRET", "")
        parsed = urlsplit(self.base_url)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        insecure_local = (parsed.scheme == "http" and loopback
                          and current_app.config.get("PROVIDER_ALLOW_LOOPBACK_HTTP", False)
                          and not current_app.config.get("SECURITY_PRODUCTION", False))
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or (parsed.scheme != "https" and not insecure_local)
                or len(self.secret) < 32):
            raise ProviderUnavailable("Configure the signed reference sandbox URL and a 32-character signing secret.")
        self.timeout = max(0.1, min(15, float(current_app.config.get("PROVIDER_HTTP_TIMEOUT", 5))))
        self.opener = build_opener(_NoRedirect())

    def _request(self, method, path, data=None):
        body = canonical(data) if data is not None else b""
        timestamp = str(int(utc().timestamp()))
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "X-Provider-Timestamp": timestamp,
                   "X-Provider-Signature": signature(self.secret, timestamp, method, path, body)}
        try:
            response = self.opener.open(Request(self.base_url + path, data=body if method == "POST" else None,
                                                headers=headers, method=method), timeout=self.timeout)
        except HTTPError as exc:
            # An unauthenticated 404 must not make us resubmit an uncertain debit.
            response = exc
        except (URLError, TimeoutError, socket.timeout, OSError, HTTPException) as exc:
            raise ProviderUnavailable("transport_uncertain") from exc
        with response:
            raw = response.read(32769)
            if len(raw) > 32768 or not verify_signature(
                    self.secret, response.headers.get("X-Provider-Timestamp"),
                    response.headers.get("X-Provider-Signature"), "RESPONSE", path, raw):
                raise ProviderProtocolError("invalid_provider_response_signature")
            if response.status == 404 and method == "GET":
                return None
            if response.status not in {200, 201}:
                raise ProviderUnavailable("provider_rejected_or_unavailable")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise ProviderProtocolError("invalid_provider_json") from exc
            if not isinstance(result, dict):
                raise ProviderProtocolError("invalid_provider_schema")
            return result

    def status(self, external_id):
        return self._request("GET", "/v1/payment-intents/" + external_id)

    def submit(self, intent):
        return self._request("POST", "/v1/payment-intents", {
            "external_id": intent.id, "amount": format(intent.amount, ".2f"),
            "currency": "BDT", "biller_reference": decrypt_text(intent.biller_reference),
            "authorization": "explicit_confirmed_intent",
        })


def create_intent(user_id, data):
    if data.get("confirmed") is not True:
        raise ValidationError("Explicit confirmation is required for a provider intent.")
    if data.get("provider", "reference_sandbox") != "reference_sandbox":
        raise ValidationError("Only the reference sandbox is available; live upay rails are disabled.")
    if not isinstance(data.get("amount"), str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,2})?", data["amount"]):
        raise ValidationError("Amount must be a decimal string.")
    try:
        amount = Decimal(data["amount"])
    except InvalidOperation:
        raise ValidationError("Amount must be a valid decimal string.")
    if not amount.is_finite() or amount <= 0 or amount > 100000 or amount.as_tuple().exponent < -2:
        raise ValidationError("Amount must be between 0.01 and 100000.00 with at most two decimal places.")
    reference = data.get("biller_reference")
    if not isinstance(reference, str) or not 1 <= len(reference) <= 80 or not reference.isascii() or not all(
            c.isalnum() or c in "-_" for c in reference):
        raise ValidationError("Biller reference must contain 1-80 ASCII letters, digits, hyphens or underscores.")
    # Validate configuration before persisting an intent that cannot dispatch.
    ReferenceHTTPAdapter()
    intent = ProviderIntent(id=uuid4().hex, user_id=user_id, amount=amount, biller_reference=encrypt_text(reference))
    db.session.add(intent)
    db.session.flush()
    db.session.add(ProviderOutbox(intent_id=intent.id))
    return intent


def intent_json(intent):
    return {"id": intent.id, "provider": intent.provider, "environment": "sandbox",
            "amount": format(intent.amount, ".2f"), "currency": intent.currency,
            "status": intent.status, "provider_reference": intent.provider_reference,
            "created_at": utc(intent.created_at).isoformat(), "wallet_debited": False}


def apply_provider_result(intent_id, data):
    if not isinstance(intent_id, str) or not re.fullmatch(r"[0-9a-f]{32}", intent_id) or not isinstance(data, dict):
        raise ProviderProtocolError("invalid_provider_schema")
    intent = db.session.get(ProviderIntent, intent_id)
    if intent is None:
        raise ValidationError("Provider intent not found.")
    if (data.get("external_id") != intent.id or data.get("currency") != "BDT"
            or data.get("amount") != format(intent.amount, ".2f")
            or not isinstance(data.get("status"), str) or data["status"] not in {"PENDING", "SUCCEEDED", "FAILED"}
            or isinstance(data.get("sequence"), bool) or not isinstance(data.get("sequence"), int)
            or not 1 <= data["sequence"] <= 2147483647
            or not isinstance(data.get("provider_reference"), str)
            or not 1 <= len(data["provider_reference"]) <= 80):
        raise ProviderProtocolError("provider_result_binding_mismatch")
    if data["sequence"] < intent.provider_sequence:
        return intent  # A delayed signed event is harmless and acknowledged.
    if intent.provider_reference and data["provider_reference"] != intent.provider_reference:
        raise ProviderProtocolError("provider_reference_conflict")
    if data["sequence"] == intent.provider_sequence:
        # UNCERTAIN/REVIEW_REQUIRED describe delivery failure after the last
        # nonterminal PENDING result; they never permit a same-sequence terminal
        # transition. A provider must advance its sequence to change outcome.
        expected = "PENDING" if intent.status in {"UNCERTAIN", "REVIEW_REQUIRED"} else intent.status
        if data["status"] != expected:
            raise ProviderProtocolError("provider_sequence_payload_conflict")
        return intent
    # A terminal result cannot be reversed by a later callback.
    if intent.status in TERMINAL and data["status"] != intent.status:
        raise ProviderProtocolError("conflicting_terminal_result")
    changed = db.session.execute(update(ProviderIntent).where(
        ProviderIntent.id == intent_id, ProviderIntent.provider_sequence < data["sequence"],
        ProviderIntent.status.notin_(TERMINAL),
        or_(ProviderIntent.provider_reference.is_(None), ProviderIntent.provider_reference == data["provider_reference"]),
    ).values(status=data["status"], provider_reference=data["provider_reference"],
             provider_sequence=data["sequence"], updated_at=utc()),
        execution_options={"synchronize_session": "fetch"})
    if changed.rowcount == 1:
        from app.services.security_service import audit_event
        audit_event("provider.result", data["status"].lower(), user_id=intent.user_id,
                    metadata={"reference": intent_id, "provider": "reference_sandbox"})
    # Concurrent response/callback conflicts are re-read rather than overwritten.
    if changed.rowcount != 1:
        db.session.expire(intent)
        if data["sequence"] >= intent.provider_sequence and intent.provider_reference != data["provider_reference"]:
            raise ProviderProtocolError("provider_reference_conflict")
        if data["sequence"] == intent.provider_sequence:
            expected = "PENDING" if intent.status in {"UNCERTAIN", "REVIEW_REQUIRED"} else intent.status
            if data["status"] != expected or data["provider_reference"] != intent.provider_reference:
                raise ProviderProtocolError("provider_sequence_payload_conflict")
        if data["sequence"] >= intent.provider_sequence and intent.status in TERMINAL and intent.status != data["status"]:
            raise ProviderProtocolError("conflicting_terminal_result")
    if intent.status in TERMINAL:
        db.session.execute(update(ProviderOutbox).where(ProviderOutbox.intent_id == intent_id)
                           .values(status="DONE", lease_until=None, lease_token=None))
    return intent


def accept_webhook(data, raw):
    event_id = data.get("event_id")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 80 or not event_id.isascii():
        raise ValidationError("Invalid event identifier.")
    external_id = data.get("external_id")
    if not isinstance(external_id, str) or not re.fullmatch(r"[0-9a-f]{32}", external_id):
        raise ValidationError("Invalid provider intent identifier.")
    digest = hashlib.sha256(raw).hexdigest()
    previous = ProviderWebhook.query.filter_by(event_id=event_id).first()
    if previous:
        if not hmac.compare_digest(previous.payload_hash, digest):
            raise ProviderProtocolError("webhook_event_payload_conflict")
        return {"accepted": True, "duplicate": True}
    intent = db.session.get(ProviderIntent, external_id)
    if intent is None:
        raise ValidationError("Provider intent not found.")
    try:
        db.session.add(ProviderWebhook(event_id=event_id, payload_hash=digest, intent_id=intent.id))
        db.session.flush()
        apply_provider_result(intent.id, data)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        previous = ProviderWebhook.query.filter_by(event_id=event_id).first()
        if not previous or not hmac.compare_digest(previous.payload_hash, digest):
            raise ProviderProtocolError("webhook_event_payload_conflict")
        return {"accepted": True, "duplicate": True}
    return {"accepted": True, "duplicate": False}


def process_provider_outbox(*, limit=20, now=None):
    from app.services.security_service import audit_event
    now = utc(now)
    limit = max(1, min(100, int(limit)))
    lease_seconds = max(30, int(current_app.config.get("PROVIDER_LEASE_SECONDS", 60)))
    max_attempts = max(1, min(20, int(current_app.config.get("PROVIDER_MAX_ATTEMPTS", 8))))
    query = ProviderOutbox.query.filter(or_(
        and_(ProviderOutbox.status == "PENDING", ProviderOutbox.available_at <= now),
        and_(ProviderOutbox.status == "PROCESSING", ProviderOutbox.lease_until <= now)))
    ids = [row.id for row in query.order_by(ProviderOutbox.available_at, ProviderOutbox.id).limit(limit).all()]
    result = {"claimed": 0, "completed": 0, "retrying": 0, "review_required": 0}
    for job_id in ids:
        lease_token = uuid4().hex
        claim = db.session.execute(update(ProviderOutbox).where(ProviderOutbox.id == job_id, or_(
            and_(ProviderOutbox.status == "PENDING", ProviderOutbox.available_at <= now),
            and_(ProviderOutbox.status == "PROCESSING", ProviderOutbox.lease_until <= now)))
            .values(status="PROCESSING", lease_token=lease_token, lease_until=now + timedelta(seconds=lease_seconds),
                    attempts=ProviderOutbox.attempts + 1), execution_options={"synchronize_session": "fetch"})
        db.session.commit()
        if claim.rowcount != 1:
            continue
        result["claimed"] += 1
        job = db.session.get(ProviderOutbox, job_id)
        intent = db.session.get(ProviderIntent, job.intent_id)
        attempt = job.attempts
        try:
            if intent.status in TERMINAL:
                db.session.execute(update(ProviderOutbox).where(ProviderOutbox.id == job_id,
                    ProviderOutbox.lease_token == lease_token).values(status="DONE", lease_token=None, lease_until=None))
                db.session.commit()
                result["completed"] += 1
                continue
            adapter = ReferenceHTTPAdapter()
            # Reconcile all retries, including recovery after crash between submit and commit.
            response = adapter.status(intent.id) if attempt > 1 else None
            if response is None:
                response = adapter.submit(intent)
            apply_provider_result(intent.id, response)
            db.session.commit()
            intent = db.session.get(ProviderIntent, intent.id)
            if intent.status in TERMINAL:
                result["completed"] += 1
                continue
            error = "provider_pending"
        except (ProviderUnavailable, ProviderProtocolError) as exc:
            db.session.rollback()
            error = str(exc) if str(exc) in {"transport_uncertain", "provider_pending"} else "provider_unavailable_or_invalid"
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Provider job %s interrupted (%s)", job_id, type(exc).__name__)
            error = "worker_error"
        # A concurrent signed callback may have already completed the lease.
        job = db.session.get(ProviderOutbox, job_id)
        if job.status == "DONE" or job.lease_token != lease_token:
            continue
        review = attempt >= max_attempts
        db.session.execute(update(ProviderOutbox).where(ProviderOutbox.id == job_id,
            ProviderOutbox.lease_token == lease_token).values(
            status="REVIEW_REQUIRED" if review else "PENDING", lease_token=None, lease_until=None,
            available_at=now + timedelta(seconds=min(300, 2 ** attempt)), last_error=error))
        db.session.execute(update(ProviderIntent).where(ProviderIntent.id == job.intent_id,
            ProviderIntent.status.notin_(TERMINAL)).values(status="REVIEW_REQUIRED" if review else "UNCERTAIN", updated_at=now))
        audit_event("provider.dispatch", "review_required" if review else "retrying", user_id=intent.user_id,
                    metadata={"job_id": job_id, "category": error, "provider": "reference_sandbox"})
        db.session.commit()
        result["review_required" if review else "retrying"] += 1
    return result
