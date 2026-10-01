from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import login_required
from app.container import get_container
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.reporting_service import (
    filter_transactions, local_datetime, parse_days, period_dates, transaction_totals,
)

bp = Blueprint("wallet", __name__, url_prefix="/wallet")


def _handle(action, success_message, template_name):
    try:
        action()
        flash(success_message, "success")
        return redirect(url_for("dashboard.index"))
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
@login_required
def history():
    all_txs = list(get_container().transactions.all_for_user(session["user_id"]))
    days = parse_days(request.args.get("days"), default=None)
    direction = request.args.get("direction", "")
    if direction not in {"IN", "OUT"}:
        direction = ""
    kinds = sorted({tx.kind for tx in all_txs})
    kind = request.args.get("kind", "")
    if kind not in {*kinds, "payments"}:
        kind = ""
    query = request.args.get("q", "").strip()[:100]
    txs = filter_transactions(all_txs, days=days, direction=direction, kind=kind, query=query)
    dates = period_dates(days) if days is not None else None
    return render_template(
        "wallet/history.html", transactions=txs, totals=transaction_totals(txs), days=days,
        direction=direction, kind=kind, kinds=kinds, query=query, dates=dates,
        local_time=local_datetime,
    )
