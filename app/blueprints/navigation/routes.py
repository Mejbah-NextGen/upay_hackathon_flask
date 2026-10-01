from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import login_required
from app.domain.models import Transaction
from app.services.navigation_service import (
    find_services, mark_notifications_read, matching_transactions, notification_summary,
    paginate_transactions,
)
from app.services.preference_service import get_preferences

bp = Blueprint("navigation", __name__)


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
