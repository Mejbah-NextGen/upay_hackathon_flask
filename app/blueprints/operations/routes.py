import click
from decimal import Decimal

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.auth_helpers import current_user, login_required
from app.services.exceptions import ValidationError
from app.services.recipient_service import lookup_recipient
from app.services.schedule_service import (
    SCHEDULE_KINDS, cancel_schedule, create_schedule, execute_schedule,
    run_due_payments, scheduled_for_user, scheduling_window,
)
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS


bp = Blueprint("operations", __name__)


@bp.get("/operations/recipient")
@login_required
def recipient():
    try:
        return jsonify(lookup_recipient(request.args.get("kind", ""), request.args.get("number", ""), provider=request.args.get("provider", ""), category=request.args.get("category", "")))
    except ValidationError as exc:
        return jsonify(status="invalid", name=None, authorization_name=None, number=request.args.get("number", ""), message=str(exc), can_transact=False), 400


@bp.before_app_request
def process_due_auto_payments():
    """Process automatic payments on owner visits except read-only insights.

    The CLI can also be called by a scheduler while the app is not being visited.
    It uses the same atomic due-only executor; requests never create future debits.
    """
    from flask import current_app
    if request.method != "GET" or request.endpoint == "static" or request.blueprint in {"insights", "pilot"} or not session.get("user_id"):
        return
    if not current_app.config.get("SCHEDULE_AUTO_RUN_ON_REQUEST", True):
        return
    user = current_user()
    if user:
        result = run_due_payments(user_id=user.id)
        completed = sum(payment.status == "COMPLETED" for payment in result)
        failed = sum(payment.status == "FAILED" for payment in result)
        if completed:
            flash(f"Auto Pay completed {completed} due payment(s). Review their summaries and downloads in Report.", "success")
        if failed:
            flash(f"{failed} due Auto Pay payment(s) failed. Review the reasons in Auto Pay & Plans.", "warning")


@bp.route("/schedules", methods=["GET", "POST"])
@login_required
def schedules():
    first_date, last_date = scheduling_window()
    values = request.form.to_dict() if request.method == "POST" else {"kind": "BILL_PAYMENT", "frequency": "ONE_TIME", "auto_pay": "1", "due_date": first_date.isoformat(), "category": "electricity", "provider": "DESCO Electricity"}
    status = 200
    if request.method == "POST":
        try:
            installments = create_schedule(session["user_id"], values)
            flash(f"{len(installments)} payment(s) planned. Balance is deducted only when a payment is due and successfully processed.", "success")
            return redirect(url_for("operations.schedules"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            status = 400
    payments = scheduled_for_user(session["user_id"])
    response = render_template("operations/schedules.html", schedules=payments, values=values, schedule_kinds=SCHEDULE_KINDS, categories=BILL_CATEGORIES, operators=MOBILE_OPERATORS, first_date=first_date, last_date=last_date, pending_total=sum((payment.amount for payment in payments if payment.status == "SCHEDULED"), Decimal("0.00")), active_service_group="financial")
    if request.method == "GET":
        from app.extensions import db
        from app.services.pilot_service import record_task_start
        record_task_start(session["user_id"], "recurring_payment")
        db.session.commit()
    return response, status


@bp.post("/schedules/<int:schedule_id>/cancel")
@login_required
def cancel(schedule_id):
    try:
        cancel_schedule(session["user_id"], schedule_id)
        flash("Scheduled payment cancelled. No balance was deducted.", "success")
    except ValidationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("operations.schedules")), 303
    return redirect(url_for("operations.schedules")), 303


@bp.post("/schedules/<int:schedule_id>/pay")
@login_required
def pay(schedule_id):
    try:
        schedule = execute_schedule(session["user_id"], schedule_id)
        if schedule.status == "COMPLETED":
            flash("Scheduled payment completed. Its transaction summary is available in Report.", "success")
            return redirect(url_for("wallet.receipt", transaction_id=schedule.transaction_id)), 303
        else:
            flash(schedule.last_error or "Payment could not be completed.", "danger")
    except ValidationError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("operations.schedules")), 303


@bp.post("/schedules/run-due")
@login_required
def run_due():
    result = run_due_payments(user_id=session["user_id"])
    completed = sum(payment.status == "COMPLETED" for payment in result)
    failed = sum(payment.status == "FAILED" for payment in result)
    flash(f"Due automatic payments processed: {completed} completed, {failed} failed. Future payments remain planned.", "info")
    return redirect(url_for("operations.schedules")), 303


def register_operations_cli(app):
    @app.cli.command("run-due-payments")
    @click.option("--watch", is_flag=True, help="Keep processing due payments until stopped (for a local demo worker).")
    @click.option("--interval", default=30, type=click.IntRange(1, 60), show_default=True, help="Seconds between checks when --watch is enabled.")
    def run_due_payments_command(watch, interval):
        """Execute due local demo auto-pay installments once; no real payment rails."""
        from time import sleep
        from app.extensions import db
        while True:
            result = run_due_payments()
            if result or not watch:
                click.echo(f"Processed {len(result)} due payments: {sum(p.status == 'COMPLETED' for p in result)} completed, {sum(p.status == 'FAILED' for p in result)} failed.")
            db.session.remove()
            if not watch:
                break
            sleep(interval)

    @app.cli.command("seed-demo-operations")
    def seed_demo_operations_command():
        """Add missing 120-day history and upcoming demo installments safely."""
        from app.domain.models import User
        from app.services.demo_seed import seed_demo_operations
        user = User.query.filter_by(mobile="01329097775").first()
        if not user:
            raise click.ClickException("The primary demo account was not found.")
        seed_demo_operations(user)
        click.echo("Demo history, recipients and future payment plans are ready. Existing balances and records were preserved.")
