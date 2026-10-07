from flask import Blueprint, jsonify, render_template, session

from app.auth_helpers import login_required
from app.services.financial_health_service import health_for_user
from app.services.cashflow_model import forecast_for_user, model_evaluation
from app.services.pilot_service import pilot_context, record_exposure, record_forecast_exposure, record_task_start
from app.extensions import db


bp = Blueprint("insights", __name__)


@bp.get("/insights")
@login_required
def index():
    user_id = session["user_id"]
    pilot = pilot_context(user_id)
    forecast = forecast_for_user(user_id) if pilot["forecast_enabled"] else None
    response = render_template("insights/index.html", health=health_for_user(user_id),
                               forecast=forecast, pilot=pilot)
    record_task_start(user_id, "financial_health")
    record_exposure(user_id, "financial_health")
    if forecast and forecast["available"]:
        record_forecast_exposure(user_id)
    db.session.commit()
    return response


@bp.get("/insights/model-evaluation")
@login_required
def model_evaluation_download():
    try:
        evaluation = model_evaluation()
    except (OSError, ValueError, KeyError, TypeError):
        response = jsonify(status="unavailable", message="Model evaluation is temporarily unavailable.")
        response.status_code = 503
    else:
        response = jsonify(evaluation)
    response.headers["Content-Disposition"] = 'attachment; filename="upayx-model-evaluation.json"'
    response.headers["Cache-Control"] = "private, no-store"
    return response
