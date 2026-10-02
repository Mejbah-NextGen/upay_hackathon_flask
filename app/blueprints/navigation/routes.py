from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for, Response

from app.auth_helpers import login_required
from app.domain.models import Transaction
from app.services.navigation_service import (
    find_services, mark_notifications_read, matching_transactions, notification_summary,
    paginate_transactions, mark_notification_read,
)
from app.services.preference_service import get_preferences

bp = Blueprint("navigation", __name__)


@bp.post("/notifications/<int:transaction_id>/open")
@login_required
def open_notification(transaction_id):
    if mark_notification_read(session["user_id"], transaction_id) is None:
        abort(404)
    return redirect(url_for("wallet.receipt", transaction_id=transaction_id))


@bp.post("/preferences/display")
def display_preferences():
    from app.domain.preferences import DisplayPreference
    from app.extensions import db
    language = request.form.get("language", session.get("language", "en"))
    theme = request.form.get("theme", session.get("theme", "system"))
    if language not in {"en", "bn"} or theme not in {"light", "dark", "system"}:
        abort(400)
    session["language"], session["theme"] = language, theme
    if session.get("user_id"):
        preferences = db.session.get(DisplayPreference, session["user_id"])
        if preferences is None:
            preferences = DisplayPreference(user_id=session["user_id"])
        preferences.language, preferences.theme = language, theme
        db.session.add(preferences)
        db.session.commit()
    target = request.form.get("next", "/")
    # Only redirects to a relative app path; reject protocol-relative and backslash URLs.
    if not target.startswith("/") or target.startswith("//") or "\\" in target or any(ord(c) < 32 for c in target):
        target = "/"
    return redirect(target)


@bp.get("/qr/image")
@login_required
def qr_image():
    from app.services.qr_service import operation_qr
    from app.services.exceptions import ValidationError
    try:
        svg = operation_qr(session["user_id"], request.args)
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "private, no-store"})


@bp.post("/qr/verify")
@login_required
def verify_qr():
    from app.services.qr_service import read_operation_qr
    from app.services.exceptions import ValidationError
    try:
        payload = read_operation_qr(session["user_id"], (request.get_json(silent=True) or {}).get("code", ""))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(payload)


@bp.post("/qr/read-image")
@login_required
def read_qr_image():
    from app.services.qr_service import read_qr_upload
    from app.services.exceptions import ValidationError
    try:
        payload = read_qr_upload(session["user_id"], request.files.get("image"))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(payload)


@bp.get("/search")
@login_required
def search():
    query = " ".join(request.args.get("q", "").split())[:120]
    services = [
        dict(service, href=url_for(service["endpoint"], **service.get("params", {})))
        for service in find_services(query)
    ]
    transactions = paginate_transactions(
        matching_transactions(session["user_id"], query), request.args.get("page"),
    )
    return render_template(
        "navigation/search.html", query=query, services=services,
        transaction_page=transactions,
    )


@bp.get("/notifications")
@login_required
def notifications():
    summary = notification_summary(session["user_id"])
    transactions = paginate_transactions(
        Transaction.query.filter_by(user_id=session["user_id"]).order_by(
            Transaction.created_at.desc(), Transaction.id.desc()
        ), request.args.get("page"),
    )
    return render_template(
        "navigation/notifications.html", transaction_page=transactions,
        alerts=summary,
        alerts_enabled=get_preferences(session["user_id"]).notifications_enabled,
    )


@bp.post("/notifications/read")
@login_required
def mark_read():
    mark_notifications_read(session["user_id"])
    flash("Transaction notifications marked as read.", "success")
    return redirect(url_for("navigation.notifications"))
