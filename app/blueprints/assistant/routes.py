"""Authenticated, CSRF-protected read-only app assistance."""

import json

import click

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from app.auth_helpers import current_user, login_required
from app.services.assistant_service import answer_question, clear_conversation, conversation_history, provider_enabled
from app.services.localization import translate
from app.services.ai_governance_service import (
    erase_ai_data, governed_research_export, has_consent, privacy_state,
    prune_expired, revoke_consent, set_consent,
)

bp = Blueprint("assistant", __name__, url_prefix="/assistant")


def _ui_error(message):
    return translate(message, session.get("language", "en"))


@bp.app_context_processor
def assistant_ui():
    user = current_user()
    return {"assistant_hosted": bool(user and provider_enabled() and has_consent(user.id)),
            "assistant_provider_available": provider_enabled()}


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Send a question as an object.")
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter a question about the app.")
    question = question.strip()
    if len(question) > 1200:
        raise ValueError("Keep your question within 1,200 characters.")
    history = payload.get("history", [])
    if not isinstance(history, list) or len(history) > 8:
        raise ValueError("The conversation is too long. Start a new chat.")
    clean_history = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError("Invalid conversation history.")
        content = item.get("content")
        if not isinstance(content, str) or len(content) > 6000:
            raise ValueError("Invalid conversation message.")
        clean_history.append({"role": item["role"], "content": content})
    return question, clean_history


def _within_rate_limit(user_id):
    # Shared across web processes and client IPs; consume quota before writes.
    from app.services.security_service import rate_limit
    return rate_limit("assistant-user:" + str(user_id), "assistant", limit=12, window_seconds=60)


@bp.route("", methods=["GET", "POST"])
@login_required
def index():
    result, error, status = None, None, 200
    question = request.form.get("question", "")
    if request.method == "POST":
        try:
            question, history = _validate_payload({"question": question})
            if not _within_rate_limit(current_user().id):
                error, status = _ui_error("Please wait a minute before asking more questions."), 429
            else:
                result = answer_question(current_user(), question, history)
        except ValueError as exc:
            error, status = _ui_error(str(exc)), 400
    return render_template("assistant/index.html", result=result, question=question, error=error, conversation=conversation_history(current_user().id)), status


@bp.post("/ask")
def ask():
    user = current_user()
    if user is None:
        return jsonify(error=_ui_error("Your session expired. Sign in again to use the assistant.")), 401
    try:
        question, history = _validate_payload(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify(error=_ui_error(str(exc))), 400
    if not _within_rate_limit(user.id):
        return jsonify(error=_ui_error("Please wait a minute before asking more questions.")), 429, {"Retry-After": "60"}
    return jsonify(answer_question(user, question, history))


@bp.get("/history")
def history():
    user = current_user()
    if user is None:
        return jsonify(error=_ui_error("Your session expired. Sign in again to use the assistant.")), 401
    return jsonify(messages=conversation_history(user.id)), 200, {"Cache-Control": "private, no-store"}


@bp.post("/clear")
def clear():
    user = current_user()
    if user is None:
        return jsonify(error=_ui_error("Your session expired. Sign in again to use the assistant.")), 401
    clear_conversation(user.id)
    if request.is_json:
        return jsonify(cleared=True)
    return redirect(url_for("assistant.index"))


@bp.get("/privacy")
@login_required
def privacy():
    prune_expired(current_user().id)
    return render_template("assistant/privacy.html", privacy=privacy_state(current_user().id)), 200, {"Cache-Control": "private, no-store"}


@bp.post("/privacy/consent")
@login_required
def privacy_consent():
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload if isinstance(payload, dict) or request.form else {}
    accepted = payload.get("accept") is True if request.is_json else payload.get("accept") == "yes"
    try:
        set_consent(current_user().id, str(payload.get("purpose", "")), accept=accepted)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if request.is_json:
        return jsonify(privacy_state(current_user().id)), 200, {"Cache-Control": "private, no-store"}
    return redirect(url_for("assistant.privacy"))


@bp.post("/privacy/revoke")
@login_required
def privacy_revoke():
    payload = request.get_json(silent=True) if request.is_json else request.form
    if not isinstance(payload, dict) and not request.form:
        return jsonify(error="Choose a consent purpose."), 400
    try:
        receipt = revoke_consent(current_user().id, str(payload.get("purpose", "")))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if request.is_json:
        return jsonify(receipt), 200, {"Cache-Control": "private, no-store"}
    return render_template("assistant/privacy.html", privacy=privacy_state(current_user().id), receipt=receipt), 200, {"Cache-Control": "private, no-store"}


@bp.post("/privacy/erase")
@login_required
def privacy_erase():
    receipt = erase_ai_data(current_user().id)
    if request.is_json:
        return jsonify(receipt), 200, {"Cache-Control": "private, no-store"}
    return render_template("assistant/privacy.html", privacy=privacy_state(current_user().id), receipt=receipt), 200, {"Cache-Control": "private, no-store"}


def _private_download(data, filename):
    response = current_app.response_class(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json")
    response.headers.update({"Cache-Control": "private, no-store", "Content-Disposition": f'attachment; filename="{filename}"'})
    return response


@bp.get("/privacy/export")
@login_required
def privacy_export():
    from app.domain.ai_governance import AIGovernanceEvent
    from app.domain.models import Transaction
    user = current_user()
    data = {"scope": "Your account wallet ledger and AI data", "account": {"name": user.full_name, "mobile": user.mobile,
            "email": user.email, "wallet_balance": str(user.balance)}, "ai_privacy": privacy_state(user.id),
            "conversation": conversation_history(user.id),
            "transactions": [{"id": tx.id, "kind": tx.kind, "direction": tx.direction, "amount": str(tx.amount),
                              "fee": str(tx.fee), "status": tx.status, "title": tx.title,
                              "counterparty": tx.counterparty, "reference": tx.reference,
                              "note": tx.note, "created_at": tx.created_at.isoformat()}
                             for tx in Transaction.query.filter_by(user_id=user.id).order_by(Transaction.id).all()],
            "ai_events": [{"kind": row.kind, "reason": row.reason, "created_at": row.created_at.isoformat()}
                          for row in AIGovernanceEvent.query.filter_by(user_id=user.id).all()]}
    return _private_download(data, "upayx-account-and-ai-data.json")


@bp.get("/privacy/research-export")
@login_required
def privacy_research_export():
    try:
        data = governed_research_export(current_user())
    except ValueError as exc:
        return jsonify(error=str(exc)), 403
    return _private_download(data, "upayx-research-aggregates.json")


@bp.cli.command("prune-ai-data")
def prune_ai_data_cli():
    """Purge expired chats and content-free events. Run daily from the worker."""
    click.echo(json.dumps(prune_expired(), sort_keys=True))
