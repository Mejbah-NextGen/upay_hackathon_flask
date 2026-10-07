import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

import click
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from app.domain.integration import ApiIdempotency, ApiToken, ProviderIntent
from app.domain.models import User
from app.domain.operations import ScheduledPayment
from app.extensions import csrf, db
from app.services.exceptions import ValidationError
from app.services.encryption_service import decrypt_text, encrypt_text
from app.services.provider_service import (
    ProviderProtocolError, ProviderUnavailable, accept_webhook, create_intent,
    intent_json, process_provider_outbox, utc, verify_signature,
)


bp = Blueprint("api", __name__, url_prefix="/api/v1")
csrf.exempt(bp)
SCOPES = {"balance:read", "insights:read", "schedules:read", "schedules:write", "provider:read", "provider:write"}
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
AMOUNT_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,2})?$")


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


def reply(data, status=200):
    return jsonify(data=data, request_id=g.request_id), status


def error(code, message, status):
    return jsonify(error={"code": code, "message": message}, request_id=g.request_id), status


@bp.before_request
def prepare_api():
    g.request_id = getattr(g, "request_id", uuid4().hex)
    if request.content_length is not None and request.content_length > 32768:
        raise ApiError("body_too_large", "API bodies must be 32 KiB or smaller.", 413)


@bp.after_request
def private_api_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Request-ID"] = g.request_id
    if response.status_code == 401:
        response.headers["WWW-Authenticate"] = 'Bearer realm="upayx-api"'
    return response


@bp.errorhandler(ApiError)
def api_error(exc):
    db.session.rollback()
    return error(exc.code, exc.message, exc.status)


@bp.errorhandler(ValidationError)
def validation_error(exc):
    db.session.rollback()
    return error("validation_error", str(exc), 422)


@bp.errorhandler(ProviderUnavailable)
def unavailable_error(exc):
    db.session.rollback()
    return error("provider_unavailable", "Reference sandbox is unavailable or not configured. Live upay rails are disabled.", 503)


@bp.errorhandler(ProviderProtocolError)
def protocol_error(exc):
    db.session.rollback()
    return error("provider_protocol_conflict", "Provider result could not be safely accepted.", 409)


@bp.errorhandler(HTTPException)
def http_error(exc):
    db.session.rollback()
    return error("http_error", exc.name, exc.code)


@bp.errorhandler(Exception)
def internal_error(exc):
    db.session.rollback()
    current_app.logger.error("API request %s failed (%s)", g.request_id, type(exc).__name__)
    return error("internal_error", "The request could not be completed.", 500)


def require_scope(scope):
    def decorator(function):
        @wraps(function)
        def authenticated(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not re.fullmatch(r"Bearer upx_[A-Za-z0-9_-]{43}", header):
                raise ApiError("unauthorized", "A valid scoped bearer token is required.", 401)
            digest = hashlib.sha256(header[7:].encode()).hexdigest()
            token = ApiToken.query.filter_by(secret_hash=digest).first()
            if token is None or token.revoked_at is not None or utc(token.expires_at) <= utc():
                raise ApiError("unauthorized", "A valid scoped bearer token is required.", 401)
            owner = db.session.get(User, token.user_id)
            if owner is None or not owner.verified:
                raise ApiError("unauthorized", "A valid scoped bearer token is required.", 401)
            if scope not in json.loads(token.scopes):
                raise ApiError("insufficient_scope", "This token does not grant the required scope.", 403)
            from app.services.security_service import rate_limit
            if not rate_limit("api-token:" + digest, "api"):
                raise ApiError("rate_limited", "API rate limit exceeded. Try again later.", 429)
            g.api_token, g.api_user_id = token, token.user_id
            return function(*args, **kwargs)
        return authenticated
    return decorator


def json_body(allowed, required=()):
    if request.mimetype != "application/json":
        raise ApiError("unsupported_media_type", "Use application/json.", 415)
    raw = request.get_data(cache=True)
    if len(raw) > 32768:
        raise ApiError("body_too_large", "API bodies must be 32 KiB or smaller.", 413)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("non_finite_number")
    try:
        data = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError):
        raise ApiError("invalid_json", "Provide valid JSON with unique keys and finite values.")
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise ApiError("invalid_schema", "Request fields do not match the endpoint schema.", 422)
    return data


def idempotent(data, action, *, status=201):
    key = request.headers.get("Idempotency-Key", "")
    if not KEY_PATTERN.fullmatch(key):
        raise ApiError("idempotency_key_required", "Supply an 8-128 character Idempotency-Key using letters, digits, underscores or hyphens.")
    digest = hashlib.sha256(json.dumps({"method": request.method, "path": request.path, "body": data},
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    previous = ApiIdempotency.query.filter_by(token_id=g.api_token.id, key=key).first()
    def replay(row):
        if not hmac.compare_digest(row.request_hash, digest):
            raise ApiError("idempotency_conflict", "This key was already used for a different request.", 409)
        if not row.response_json:
            raise ApiError("request_in_progress", "Retry this request with the same key.", 409)
        return reply(json.loads(decrypt_text(row.response_json)), row.status_code)
    if previous:
        return replay(previous)
    record = ApiIdempotency(token_id=g.api_token.id, key=key, request_hash=digest, status_code=status)
    db.session.add(record)
    try:
        # Unique insert obtains the claim before the side effect. Both commit together.
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return replay(ApiIdempotency.query.filter_by(token_id=g.api_token.id, key=key).one())
    output = action()
    record.response_json = encrypt_text(json.dumps(output, sort_keys=True, separators=(",", ":")))
    from app.services.security_service import audit_event
    audit_event("api_mutation", "success", user_id=g.api_user_id,
                metadata={"category": request.endpoint, "status_code": status})
    db.session.commit()
    return reply(output, status)


def pagination():
    if set(request.args) - {"limit", "after"} or any(len(request.args.getlist(k)) != 1 for k in request.args):
        raise ApiError("invalid_query", "Use only one limit and one after parameter.")
    try:
        limit = int(request.args.get("limit", "20"))
        after = int(request.args.get("after", "0"))
    except ValueError:
        raise ApiError("invalid_query", "limit and after must be integers.")
    if not 1 <= limit <= 100 or not 0 <= after <= 2147483647:
        raise ApiError("invalid_query", "limit must be 1-100 and after must be a nonnegative cursor.")
    return limit, after


def schedule_json(row):
    return {"id": row.id, "kind": row.kind, "amount": format(row.amount, ".2f"), "currency": "BDT",
            "recipient_number": row.recipient_number, "provider": row.provider, "category": row.category,
            "frequency": row.frequency, "auto_pay": row.auto_pay, "due_at": utc(row.due_at).isoformat(),
            "status": row.status, "transaction_id": row.transaction_id}


@bp.get("/balance")
@require_scope("balance:read")
def balance():
    user = db.session.get(User, g.api_user_id)
    return reply({"balance": format(user.balance, ".2f"), "currency": "BDT", "environment": "demo_wallet"})


@bp.get("/financial-health")
@require_scope("insights:read")
def financial_health():
    from app.services.cashflow_model import forecast_for_user
    from app.services.financial_health_service import health_for_user
    from app.services.pilot_service import pilot_context
    report = health_for_user(g.api_user_id)
    money_fields = ("balance", "reserved", "scheduled_reserve", "pay_later_reserve", "safe_to_spend", "shortfall")
    output = {key: format(report[key], ".2f") for key in money_fields}
    output.update(currency="BDT", horizon_end=report["horizon_end"].isoformat(), advisory_only=True,
                  overdue_count=report["overdue_count"], signal_count=report["signal_count"])
    if pilot_context(g.api_user_id)["forecast_enabled"]:
        forecast = forecast_for_user(g.api_user_id)
        output["forecast"] = {k: str(v) if hasattr(v, "as_tuple") else v.isoformat() if isinstance(v, datetime) else v
                              for k, v in forecast.items() if k in {"available", "reason", "model_version", "predicted_outflow", "lower_bound", "upper_bound", "horizon_days"}}
    else:
        output["forecast"] = {"available": False, "reason": "pilot_control_group"}
    return reply(output)


@bp.get("/schedules")
@require_scope("schedules:read")
def schedules():
    limit, after = pagination()
    rows = ScheduledPayment.query.filter(ScheduledPayment.user_id == g.api_user_id,
        ScheduledPayment.id > after).order_by(ScheduledPayment.id).limit(limit + 1).all()
    return reply({"items": [schedule_json(row) for row in rows[:limit]],
                  "next_cursor": rows[limit - 1].id if len(rows) > limit else None})


@bp.post("/schedules")
@require_scope("schedules:write")
def new_schedule():
    data = json_body({"kind", "amount", "recipient_number", "provider", "category", "frequency", "auto_pay", "due_date", "note", "confirmed"},
                     {"kind", "amount", "recipient_number", "due_date", "confirmed"})
    for key, value in data.items():
        if key in {"auto_pay", "confirmed"}:
            if not isinstance(value, bool):
                raise ApiError("invalid_schema", key + " must be a boolean.", 422)
        elif not isinstance(value, str) or len(value) > (255 if key == "note" else 120):
            raise ApiError("invalid_schema", "Invalid string field: " + key, 422)
    if data["confirmed"] is not True or not AMOUNT_PATTERN.fullmatch(data["amount"]):
        raise ApiError("confirmation_or_amount_required", "Confirm the schedule and provide a decimal amount string.", 422)
    from app.services.schedule_service import create_schedule
    values = {**data, "auto_pay": "1" if data.get("auto_pay", True) else "0"}
    return idempotent(data, lambda: {"items": [schedule_json(row) for row in create_schedule(g.api_user_id, values, commit=False)]})


@bp.post("/schedules/<int:schedule_id>/cancel")
@require_scope("schedules:write")
def cancel(schedule_id):
    data = json_body(set())
    if ScheduledPayment.query.filter_by(id=schedule_id, user_id=g.api_user_id).first() is None:
        raise ApiError("not_found", "Schedule not found.", 404)
    from app.services.schedule_service import cancel_schedule
    return idempotent(data, lambda: schedule_json(cancel_schedule(g.api_user_id, schedule_id, commit=False)), status=200)


@bp.post("/provider-intents")
@require_scope("provider:write")
def provider_intents():
    data = json_body({"provider", "amount", "biller_reference", "confirmed"}, {"amount", "biller_reference", "confirmed"})
    return idempotent(data, lambda: intent_json(create_intent(g.api_user_id, data)), status=202)


@bp.get("/provider-intents/<string:intent_id>")
@require_scope("provider:read")
def provider_intent_status(intent_id):
    intent = ProviderIntent.query.filter_by(id=intent_id, user_id=g.api_user_id).first()
    if intent is None:
        raise ApiError("not_found", "Provider intent not found.", 404)
    return reply(intent_json(intent))


@bp.post("/provider-webhooks/reference")
def provider_webhook():
    raw = request.get_data(cache=True)
    if not verify_signature(current_app.config.get("PROVIDER_SIGNING_SECRET", ""),
            request.headers.get("X-Provider-Timestamp"), request.headers.get("X-Provider-Signature"),
            "POST", request.path, raw):
        raise ApiError("invalid_signature", "A valid, fresh provider signature is required.", 401)
    data = json_body({"event_id", "external_id", "amount", "currency", "status", "sequence", "provider_reference"},
                     {"event_id", "external_id", "amount", "currency", "status", "sequence", "provider_reference"})
    return reply(accept_webhook(data, raw))


@bp.route("/<path:unknown>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def missing(unknown):
    raise ApiError("not_found", "API endpoint not found.", 404)


def issue_token(user_id, scopes, *, name="integration", days=7):
    user = db.session.get(User, user_id)
    if user is None or not user.verified:
        raise ValueError("A verified user is required.")
    scopes = set(scopes)
    if not scopes or scopes - SCOPES:
        raise ValueError("Choose only supported, explicit scopes.")
    if not 1 <= int(days) <= int(current_app.config.get("API_TOKEN_MAX_TTL_DAYS", 30)):
        raise ValueError("Token lifetime is outside the configured limit.")
    if not 1 <= len(name) <= 80:
        raise ValueError("Token name must contain 1-80 characters.")
    secret = "upx_" + secrets.token_urlsafe(32)
    token = ApiToken(user_id=user_id, name=name, secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
                     prefix=secret[:12], scopes=json.dumps(sorted(scopes)), expires_at=utc() + timedelta(days=int(days)))
    db.session.add(token)
    db.session.flush()
    from app.services.security_service import audit_event
    audit_event("api.token", "issued", user_id=user_id, metadata={"reference": str(token.id)})
    db.session.commit()
    return token, secret


def register_api_cli(app):
    @app.cli.group("api-token")
    def api_token():
        """Manage scoped integration credentials locally."""

    @api_token.command("issue")
    @click.option("--user-id", type=int, required=True)
    @click.option("--scope", "scopes", multiple=True, required=True, type=click.Choice(sorted(SCOPES)))
    @click.option("--name", default="integration")
    @click.option("--days", type=int, default=7)
    def issue(user_id, scopes, name, days):
        try:
            token, secret = issue_token(user_id, scopes, name=name, days=days)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        click.echo(json.dumps({"id": token.id, "token": secret, "expires_at": utc(token.expires_at).isoformat()}))

    @api_token.command("revoke")
    @click.option("--token-id", type=int, required=True)
    def revoke(token_id):
        token = db.session.get(ApiToken, token_id)
        if token is None:
            raise click.ClickException("Token not found.")
        token.revoked_at = utc()
        from app.services.security_service import audit_event
        audit_event("api.token", "revoked", user_id=token.user_id, metadata={"reference": str(token.id)})
        db.session.commit()
        click.echo("Token revoked.")

    @app.cli.command("provider-worker")
    @click.option("--limit", type=click.IntRange(1, 100), default=20)
    @click.option("--watch", is_flag=True, help="Continuously process bounded batches under a supervisor.")
    @click.option("--interval", type=click.IntRange(1, 60), default=5)
    def worker(limit, watch, interval):
        """Dispatch one bounded batch, or watch under an external supervisor."""
        while True:
            try:
                click.echo(json.dumps(process_provider_outbox(limit=limit), sort_keys=True))
            except Exception as exc:
                db.session.rollback()
                current_app.logger.error("Provider worker batch interrupted (%s)", type(exc).__name__)
                if not watch:
                    raise click.ClickException("Provider worker batch interrupted; persisted leases are recoverable.")
                click.echo(json.dumps({"status": "interrupted", "recovery": "persisted_leases"}))
            finally:
                db.session.remove()
            if not watch:
                break
            time.sleep(interval)

    @app.cli.command("provider-reconcile")
    @click.option("--intent-id", required=True)
    def reconcile(intent_id):
        """Requeue an uncertain intent for signed status reconciliation with its original external key."""
        from app.domain.integration import ProviderOutbox
        from sqlalchemy import update
        intent = db.session.get(ProviderIntent, intent_id)
        if intent is None:
            raise click.ClickException("Provider intent not found.")
        job = ProviderOutbox.query.filter_by(intent_id=intent_id).one()
        if job.status != "REVIEW_REQUIRED":
            raise click.ClickException("Only intents requiring review can be manually reconciled.")
        claim = db.session.execute(update(ProviderOutbox).where(ProviderOutbox.id == job.id,
            ProviderOutbox.status == "REVIEW_REQUIRED").values(status="PENDING", attempts=1,
                available_at=utc(), lease_token=None, lease_until=None))
        if claim.rowcount != 1:
            db.session.rollback()
            raise click.ClickException("Intent review state changed; refresh before reconciling.")
        db.session.execute(update(ProviderIntent).where(ProviderIntent.id == intent_id,
            ProviderIntent.status.notin_({"SUCCEEDED", "FAILED"})).values(status="UNCERTAIN"))
        from app.services.security_service import audit_event
        audit_event("provider.reconciliation", "requeued", user_id=intent.user_id,
                    metadata={"reference": intent_id, "job_id": job.id})
        db.session.commit()
        click.echo("Intent queued for signed provider status reconciliation; no wallet movement was authorized.")
