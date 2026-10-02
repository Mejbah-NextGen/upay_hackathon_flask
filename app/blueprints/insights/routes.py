from flask import Blueprint, render_template, session

from app.auth_helpers import login_required
from app.services.financial_health_service import health_for_user


bp = Blueprint("insights", __name__)


@bp.get("/insights")
@login_required
def index():
    return render_template("insights/index.html", health=health_for_user(session["user_id"]))
