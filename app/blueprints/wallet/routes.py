from datetime import date
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for

from app.auth_helpers import login_required
from app.container import get_container
from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.export_service import (
    receipt_jpg, receipt_pdf, receipt_summary, report_pdf, report_xlsx,
    schedule_receipt_jpg, schedule_receipt_pdf, schedule_receipt_summary,
)
from app.services.reporting_service import (
    filter_schedules, filter_transactions, local_datetime, parse_days, period_dates,
    schedule_totals, transaction_totals, wallet_change,
)

bp = Blueprint("wallet", __name__, url_prefix="/wallet")


def _handle(action, success_message, template_name):
    try:
        transaction = action()
        flash(success_message, "success")
        return redirect(url_for("wallet.receipt", transaction_id=transaction.id))
    except (ValidationError, InsufficientBalanceError) as exc:
        flash(str(exc), "danger")
        return render_template(template_name), 400


@bp.route("/send-money", methods=["GET", "POST"])
@login_required
def send_money():
    if request.method == "GET":
        return render_template("wallet/send_money.html")
    return _handle(
        lambda: get_container().wallet.send_money(
            session["user_id"],
            request.form.get("recipient_mobile", ""),
            request.form.get("amount", ""),
            request.form.get("note", ""),
        ),
        "Money sent successfully.",
        "wallet/send_money.html",
    )


@bp.route("/add-money", methods=["GET", "POST"])
@login_required
def add_money():
    if request.method == "GET":
        return render_template("wallet/add_money.html")
    return _handle(
        lambda: get_container().wallet.add_money(
            session["user_id"], request.form.get("source", ""), request.form.get("amount", "")
        ),
        "Money added successfully.",
        "wallet/add_money.html",
    )


@bp.route("/cash-out", methods=["GET", "POST"])
@login_required
def cash_out():
    if request.method == "GET":
        return render_template("wallet/cash_out.html")
    return _handle(
        lambda: get_container().wallet.cash_out(
            session["user_id"], request.form.get("agent_number", ""), request.form.get("amount", "")
        ),
        "Cash-out completed successfully.",
        "wallet/cash_out.html",
    )


@bp.get("/history")
@bp.get("/report")
@login_required
def history():
    return render_template("wallet/history.html", **_report_context())


def _date_filter(name):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        abort(400, description=f"Enter a valid {name.replace('_', ' ')} in YYYY-MM-DD format.")


def _report_context():
    all_txs = list(get_container().transactions.all_for_user(session["user_id"]))
    all_schedules = ScheduledPayment.query.filter_by(user_id=session["user_id"]).all()
    days = parse_days(request.args.get("days"), default=None)
    start_date, end_date = _date_filter("start_date"), _date_filter("end_date")
    if start_date and end_date and start_date > end_date:
        abort(400, description="The start date must be on or before the end date.")
    if start_date or end_date:
        days = None
    direction = request.args.get("direction", "")
    if direction not in {"IN", "OUT"}:
        direction = ""
    kinds = sorted({tx.kind for tx in all_txs} | {item.kind for item in all_schedules})
    kind = request.args.get("kind", "")
    if kind not in {*kinds, "payments"}:
        kind = ""
    query = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "")
    if status not in {"SUCCESS", "PENDING", "FAILED", "CANCELLED", "SCHEDULED", "COMPLETED"}:
        status = ""
    scope = request.args.get("scope", "all")
    if scope not in {"all", "transactions", "scheduled"}:
        scope = "all"
    txs = filter_transactions(all_txs, days=days, direction=direction, kind=kind, query=query, status=status, start_date=start_date, end_date=end_date)
    schedules = filter_schedules(all_schedules, direction=direction, kind=kind, query=query, status=status, start_date=start_date, end_date=end_date)
    if scope == "transactions":
        schedules = []
    elif scope == "scheduled":
        txs = []
    dates = period_dates(days) if days is not None else None
    filter_description = "; ".join([
        f"Historical period: last {days} calendar days" if days else "Historical period: all stored activity",
        f"Date range: {start_date or 'any'} to {end_date or 'any'}",
        f"Records: {scope}", f"Direction: {direction or 'all'}", f"Type: {kind or 'all'}",
        f"Status: {status or 'all'}", f"Search: {query or 'none'}",
        "Schedules use due dates; the historical period preset applies to recorded transactions only",
    ])
    export_args = {"days": days or "", "start_date": start_date.isoformat() if start_date else "", "end_date": end_date.isoformat() if end_date else "", "direction": direction, "kind": kind, "status": status, "q": query, "scope": scope}
    return dict(
        transactions=txs, schedules=schedules, totals=transaction_totals(txs), schedule_totals=schedule_totals(schedules), days=days,
        direction=direction, kind=kind, kinds=kinds, query=query, dates=dates, status=status,
        start_date=start_date, end_date=end_date, scope=scope, export_args=export_args,
        local_time=local_datetime, wallet_change=wallet_change, filter_description=filter_description,
    )


def _private_download(content, filename, mimetype):
    response = send_file(BytesIO(content), as_attachment=True, download_name=filename, mimetype=mimetype, max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.get("/report/export")
@login_required
def export_report():
    selected_format = request.args.get("format", "pdf").lower()
    if selected_format not in {"pdf", "xlsx"}:
        abort(400, description="Choose PDF or Excel (.xlsx).")
    context = _report_context()
    user = get_container().users.get_by_id(session["user_id"])
    arguments = (user, context["transactions"], context["schedules"], context["filter_description"], current_app.config["APP_NAME"])
    if selected_format == "pdf":
        return _private_download(report_pdf(*arguments), "wallet-report.pdf", "application/pdf")
    return _private_download(report_xlsx(*arguments), "wallet-report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _owned_transaction(transaction_id):
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=session["user_id"]).first()
    if transaction is None:
        abort(404)
    return transaction


@bp.get("/transaction/<int:transaction_id>")
@login_required
def receipt(transaction_id):
    transaction = _owned_transaction(transaction_id)
    return render_template("wallet/receipt.html", tx=transaction, summary=receipt_summary(transaction), wallet_change=wallet_change(transaction), local_time=local_datetime)


@bp.get("/transaction/<int:transaction_id>/download")
@login_required
def download_receipt(transaction_id):
    transaction = _owned_transaction(transaction_id)
    selected_format = request.args.get("format", "pdf").lower()
    if selected_format not in {"pdf", "jpg"}:
        abort(400, description="Choose PDF or JPG.")
    user = get_container().users.get_by_id(session["user_id"])
    generator = receipt_pdf if selected_format == "pdf" else receipt_jpg
    return _private_download(generator(user, transaction, current_app.config["APP_NAME"]), f"transaction-{transaction.id}.{selected_format}", "application/pdf" if selected_format == "pdf" else "image/jpeg")


def _owned_schedule(schedule_id):
    item = ScheduledPayment.query.filter_by(id=schedule_id, user_id=session["user_id"]).first()
    if item is None:
        abort(404)
    return item


@bp.get("/schedule/<int:schedule_id>/receipt")
@login_required
def schedule_receipt(schedule_id):
    item = _owned_schedule(schedule_id)
    return render_template("wallet/schedule_receipt.html", item=item, summary=schedule_receipt_summary(item), local_time=local_datetime)


@bp.get("/schedule/<int:schedule_id>/download")
@login_required
def download_schedule_receipt(schedule_id):
    item = _owned_schedule(schedule_id)
    selected_format = request.args.get("format", "pdf").lower()
    if selected_format not in {"pdf", "jpg"}:
        abort(400, description="Choose PDF or JPG.")
    user = get_container().users.get_by_id(session["user_id"])
    generator = schedule_receipt_pdf if selected_format == "pdf" else schedule_receipt_jpg
    return _private_download(generator(user, item, current_app.config["APP_NAME"]), f"scheduled-payment-{item.id}.{selected_format}", "application/pdf" if selected_format == "pdf" else "image/jpeg")
