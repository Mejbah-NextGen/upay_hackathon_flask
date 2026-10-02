from flask import Blueprint, render_template, request, session

from app.auth_helpers import login_required
from app.container import get_container
from app.services.reporting_service import local_datetime, parse_days
from app.services.service_catalog import get_service

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@login_required
def index():
    user_id = session["user_id"]
    days = parse_days(request.args.get("days"))
    stats = get_container().wallet.dashboard_stats(user_id, days=days)
    services = [get_service(service_id) for service_id in (
        "send-money", "recharge", "cash-out", "pay-bill", "add-money", "savings",
        "auto-pay", "request-money", "traffic-fine", "toll", "government",
        "education", "insurance", "donation", "ticket", "hotel",
    )]
    quick_payments = [get_service(service_id) for service_id in (
        "electricity", "gas", "internet", "water", "tv", "education",
    )]
    return render_template(
        "dashboard/index.html", stats=stats, recent=stats["recent"], services=services,
        quick_payments=quick_payments, days=days, local_time=local_datetime,
    )
