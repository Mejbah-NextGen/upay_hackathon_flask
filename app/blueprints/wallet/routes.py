from datetime import date
import hashlib
import hmac
from io import BytesIO
import json
import re
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy.exc import IntegrityError

from app.auth_helpers import login_required
from app.container import get_container
from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.domain.wallet_submissions import WalletSubmission
from app.extensions import db
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.export_service import (
    receipt_jpg, receipt_pdf, receipt_summary, report_pdf, report_xlsx,
    schedule_receipt_jpg, schedule_receipt_pdf, schedule_receipt_summary,
)
from app.services.reporting_service import (
    bill_category, chart_selection_description, filter_chart_transactions, filter_schedules,
    filter_transactions, local_datetime, parse_chart_selection, parse_days, period_dates,
    report_visualization, schedule_totals, transaction_totals, wallet_change,
)
from app.services.wallet_catalog import DEMO_ATMS, DEMO_BANKS

bp = Blueprint("wallet", __name__, url_prefix="/wallet")


def _handle(action, success_message, template_name, **context):
    token = request.form.get("operation_token", "")
    try:
        submission = None
        if token:
            if not re.fullmatch(r"[a-f0-9]{32}", token):
                raise ValidationError("Refresh this form before submitting again.")
            fields = {key: request.form.getlist(key) for key in request.form if key not in {"csrf_token", "operation_token"}}
            payload = json.dumps([request.endpoint, fields], sort_keys=True, ensure_ascii=False).encode("utf-8")
            fingerprint = hmac.new(str(current_app.config["SECRET_KEY"]).encode("utf-8"), payload, hashlib.sha256).hexdigest()
            existing = WalletSubmission.query.filter_by(user_id=session["user_id"], token=token).first()
            if existing:
                return _repeat_submission(existing, fingerprint)
            submission = WalletSubmission(user_id=session["user_id"], token=token, fingerprint=fingerprint)
            db.session.add(submission)
            try:
                db.session.flush()
            except IntegrityError:
                # A concurrent identical request may have committed while this
                # request waited for the unique claim. It owns the same receipt.
                db.session.rollback()
                existing = WalletSubmission.query.filter_by(user_id=session["user_id"], token=token).first()
                if existing is None:
                    raise ValidationError("Refresh this form before submitting again.")
                return _repeat_submission(existing, fingerprint)
        transaction = action()
        if submission is not None:
            submission.transaction_id = transaction.id
        db.session.commit()
        flash(success_message, "success")
        return redirect(url_for("wallet.receipt", transaction_id=transaction.id))
    except (ValidationError, InsufficientBalanceError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        context["operation_token"] = token if re.fullmatch(r"[a-f0-9]{32}", token) else uuid4().hex
        return render_template(template_name, **context), 400


def _repeat_submission(submission, fingerprint):
    if not hmac.compare_digest(submission.fingerprint, fingerprint) or submission.transaction_id is None:
        raise ValidationError("This form was already submitted. Open a new form to change the details.")
    flash("This transaction was already completed. Showing the original receipt.", "success")
    return redirect(url_for("wallet.receipt", transaction_id=submission.transaction_id))


@bp.route("/send-money", methods=["GET", "POST"])
@login_required
def send_money():
    if request.method == "GET":
        return render_template("wallet/send_money.html", operation_token=uuid4().hex)
    return _handle(
        lambda: get_container().wallet.send_money(
            session["user_id"],
            request.form.get("recipient_mobile", ""),
            request.form.get("amount", ""),
            request.form.get("note", ""),
            commit=False,
        ),
        "Money sent successfully.",
        "wallet/send_money.html",
    )


@bp.route("/add-money", methods=["GET", "POST"])
@login_required
def add_money():
    if request.method == "GET":
        return render_template("wallet/add_money.html", operation_token=uuid4().hex, banks=DEMO_BANKS)
    if request.form.get("action") == "choose-source":
        return render_template("wallet/add_money.html", operation_token=uuid4().hex, banks=DEMO_BANKS)
    return _handle(
        lambda: get_container().wallet.add_money(
            session["user_id"], request.form.get("source", ""), request.form.get("amount", ""),
            bank=request.form.get("bank", ""), account_number=request.form.get("account_number", ""),
            card_number=request.form.get("card_number", ""), holder_name=request.form.get("holder_name", ""),
            agent_number=request.form.get("agent_number", ""), commit=False,
        ),
        "Money added successfully.",
        "wallet/add_money.html",
        banks=DEMO_BANKS,
    )


@bp.route("/cash-out", methods=["GET", "POST"])
@login_required
def cash_out():
    channel = str(request.form.get("channel", request.args.get("channel", "AGENT"))).upper()
    context = {"channel": channel if channel in {"AGENT", "ATM"} else "AGENT", "atm_locations": DEMO_ATMS, "operation_token": uuid4().hex}
    if request.method == "GET":
        return render_template("wallet/cash_out.html", **context)
    return _handle(
        lambda: get_container().wallet.cash_out(
            session["user_id"], request.form.get("agent_number", ""), request.form.get("amount", ""),
            channel=channel, atm_location=request.form.get("atm_location", ""),
            commit=False,
        ),
        "Cash-out completed successfully.",
        "wallet/cash_out.html",
        **context,
    )


@bp.route("/transfer-money", methods=["GET", "POST"])
@login_required
def transfer_money():
    channel = str(request.form.get("channel", request.args.get("channel", "BANK"))).upper()
    context = {"channel": channel if channel in {"BANK", "VISA"} else "BANK", "banks": DEMO_BANKS, "operation_token": uuid4().hex}
    if request.method == "GET":
        return render_template("wallet/transfer_money.html", **context)
    return _handle(
        lambda: get_container().wallet.transfer_money(
            session["user_id"], channel, request.form.get("amount", ""),
            bank=request.form.get("bank", ""), account_number=request.form.get("account_number", ""),
            card_number=request.form.get("card_number", ""), holder_name=request.form.get("holder_name", ""),
            rail=request.form.get("rail", "NPSB"), note=request.form.get("note", ""),
            commit=False,
        ),
        "Demo transfer recorded. No funds were sent to an external bank or card.",
        "wallet/transfer_money.html", **context,
    )


@bp.get("/quote")
@login_required
def quote():
    try:
        result = get_container().wallet.quote(
            session["user_id"], request.args.get("operation", ""), request.args.get("amount", ""),
            channel=request.args.get("channel", "AGENT"), rail=request.args.get("rail", "NPSB"),
        )
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    response = jsonify({key: value if isinstance(value, bool) else str(value) for key, value in result.items()})
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
    from app.domain.payment_plans import PaymentInvoice
    from app.services.service_catalog import BILL_CATEGORIES

    invoice_categories = {item.transaction_id: item.category for item in PaymentInvoice.query.filter_by(user_id=session["user_id"]).all()}
    plan_mode = request.args.get("plan_mode", "")
    if plan_mode not in {"auto_pay", "manual"}:
        plan_mode = ""
    if plan_mode:
        all_schedules = [item for item in all_schedules if bool(item.auto_pay) == (plan_mode == "auto_pay")]
        planned_ids = {item.transaction_id for item in all_schedules if item.transaction_id is not None}
        all_txs = [tx for tx in all_txs if tx.id in planned_ids]
    category = request.args.get("category", "")
    if category not in BILL_CATEGORIES:
        category = ""
    if category:
        category_matches = lambda value: value.startswith("education") if category == "education" else value == category
        all_txs = [tx for tx in all_txs if category_matches(bill_category(tx, invoice_categories))]
        all_schedules = [item for item in all_schedules if item.kind == "BILL_PAYMENT" and category_matches(item.category)]
    try:
        chart_selection = parse_chart_selection(request.args.get("chart_selection", ""))
    except ValueError as exc:
        abort(400, description=str(exc))
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
    if status not in {"SUCCESS", "PENDING", "FAILED", "CANCELLED", "SCHEDULED", "COMPLETED", "DEFERRED"}:
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
    if chart_selection:
        txs = filter_chart_transactions(txs, chart_selection, invoice_categories)
        schedules = []
        scope = "transactions"
    dates = period_dates(days) if days is not None else None
    filter_description = "; ".join([
        f"Historical period: last {days} calendar days" if days else "Historical period: all stored activity",
        f"Date range: {start_date or 'any'} to {end_date or 'any'}",
        f"Records: {scope}", f"Direction: {direction or 'all'}", f"Type: {kind or 'all'}",
        f"Bill category: {'Education (all levels)' if category == 'education' else BILL_CATEGORIES[category]['label'] if category else 'all'}",
        f"Payment plans: {plan_mode.replace('_', ' ') if plan_mode else 'all activity'}",
        f"Status: {status or 'all'}", f"Search: {query or 'none'}",
        f"Chart segment: {chart_selection_description(chart_selection)}",
        "Schedules use due dates; the historical period preset applies to recorded transactions only",
    ])
    export_args = {"days": days or "", "start_date": start_date.isoformat() if start_date else "", "end_date": end_date.isoformat() if end_date else "", "direction": direction, "kind": kind, "category": category, "plan_mode": plan_mode, "status": status, "q": query, "scope": scope, "chart_selection": json.dumps(chart_selection, separators=(",", ":")) if chart_selection else ""}
    return dict(
        transactions=txs, schedules=schedules, totals=transaction_totals(txs), schedule_totals=schedule_totals(schedules), days=days,
        direction=direction, kind=kind, kinds=kinds, query=query, dates=dates, status=status,
        start_date=start_date, end_date=end_date, scope=scope, export_args=export_args,
        category=category, bill_categories=BILL_CATEGORIES, plan_mode=plan_mode,
        local_time=local_datetime, wallet_change=wallet_change, filter_description=filter_description,
        analytics=report_visualization(txs, invoice_categories),
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
    from app.services.navigation_service import mark_notification_read
    mark_notification_read(session["user_id"], transaction.id)
    from app.domain.payment_plans import PaymentInvoice
    invoice = PaymentInvoice.query.filter_by(transaction_id=transaction.id, user_id=session["user_id"]).first()
    return render_template("wallet/receipt.html", tx=transaction, summary=receipt_summary(transaction), wallet_change=wallet_change(transaction), local_time=local_datetime, payment_invoice=invoice)


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
