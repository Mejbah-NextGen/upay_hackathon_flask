import json

import click
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import login_required
from app.domain.pilot import PilotFeedback
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.pilot_service import (
    CONSENT_VERSION, enrol_participant, participant_for_user, pilot_context,
    pilot_metrics, record_task_completion, submit_feedback, withdraw_participant,
)


bp = Blueprint("pilot", __name__, url_prefix="/pilot")


@bp.get("")
@login_required
def index():
    user_id = session["user_id"]
    participant = participant_for_user(user_id)
    metrics = pilot_metrics(data_source=participant.data_source if participant else "DEMO", user_id=user_id)
    responses = PilotFeedback.query.filter_by(user_id=user_id).order_by(PilotFeedback.created_at.desc()).limit(10).all()
    return render_template("pilot/index.html", participant=participant, pilot=pilot_context(user_id),
                           metrics=metrics, responses=responses, consent_version=CONSENT_VERSION)


@bp.post("/enrol")
@login_required
def enrol():
    try:
        participant = enrol_participant(session["user_id"], consent=request.form.get("consent") == "1",
                                        data_source=request.form.get("data_source", "DEMO"),
                                        real_attestation=request.form.get("real_attestation") == "1")
        db.session.commit()
        flash(f"You joined the planning pilot ({participant.variant}). Your study experience is fixed for this pilot.", "success")
    except ValidationError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("pilot.index")), 303
    return redirect(url_for("pilot.index")), 303


@bp.post("/withdraw")
@login_required
def withdraw():
    withdraw_participant(session["user_id"])
    db.session.commit()
    flash("Pilot collection stopped. Your existing study observations are retained under the consent you accepted.", "success")
    return redirect(url_for("pilot.index")), 303


@bp.post("/plan-reviewed")
@login_required
def plan_reviewed():
    if request.form.get("acknowledge") != "1":
        flash("Confirm that you reviewed the recorded commitments before completing the planning task.", "warning")
        return redirect(url_for("insights.index")), 303
    completed = record_task_completion(session["user_id"], "financial_health")
    if completed is None:
        flash("Open Financial Health as an enrolled participant before completing the planning task.", "warning")
    else:
        db.session.commit()
        flash("Planning review recorded. This acknowledgement measures task completion, not financial improvement.", "success")
    return redirect(url_for("insights.index")), 303


@bp.post("/feedback")
@login_required
def feedback():
    try:
        submit_feedback(session["user_id"], request.form, support=request.form.get("kind") == "SUPPORT")
        db.session.commit()
        flash("Your research response was recorded. Thank you for describing your experience.", "success")
    except ValidationError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("pilot.index")), 303


def register_pilot_cli(app):
    @app.cli.command("pilot-report")
    @click.option("--source", type=click.Choice(["REAL", "DEMO"], case_sensitive=False), default="REAL", show_default=True)
    def pilot_report(source):
        """Print aggregate study evidence; never participant names or free text."""
        click.echo(json.dumps(pilot_metrics(data_source=source), indent=2))

    @app.cli.command("pilot-verify-real")
    @click.option("--user-id", required=True, type=click.IntRange(1))
    @click.option("--confirm-researched", is_flag=True, help="Confirm the operator verified this is a genuine consenting research participant.")
    def pilot_verify_real(user_id, confirm_researched):
        """Verify research provenance locally after checking recruitment records."""
        participant = participant_for_user(user_id)
        if not confirm_researched:
            raise click.ClickException("Verification requires --confirm-researched after checking participant recruitment records.")
        if participant is None or participant.data_source != "REAL":
            raise click.ClickException("This account is not enrolled as a real research participant.")
        participant.verified_real = True
        db.session.commit()
        click.echo("Research provenance verified. Wallet outcomes remain simulated prototype outcomes.")
