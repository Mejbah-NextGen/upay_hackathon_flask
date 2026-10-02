"""Authenticated, CSRF-protected read-only app assistance."""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from app.auth_helpers import current_user, login_required
from app.services.assistant_service import answer_question, clear_conversation, conversation_history, provider_enabled
from app.services.localization import translate

bp = Blueprint("assistant", __name__, url_prefix="/assistant")


def _ui_error(message):
    return translate(message, session.get("language", "en"))


@bp.app_context_processor
def assistant_ui():
    return {"assistant_hosted": provider_enabled()}


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
    state = current_app.extensions.setdefault("assistant_rate_limit", {"users": defaultdict(deque), "lock": Lock()})
    now = monotonic()
    with state["lock"]:
        entries = state["users"][user_id]
        while entries and entries[0] < now - 60:
            entries.popleft()
        if len(entries) >= 12:
            return False
        entries.append(now)
        # Bound process-local bookkeeping on large demo instances.
        if len(state["users"]) > 1000:
            for key in list(state["users"]):
                if key != user_id and (not state["users"][key] or state["users"][key][-1] < now - 60):
                    del state["users"][key]
        return True


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
