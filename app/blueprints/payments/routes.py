from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import login_required
from app.container import get_container
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS, SERVICE_GROUPS, services_for_group

bp = Blueprint("payments", __name__, url_prefix="/payments")


def _hub(group):
    return render_template(
        "payments/index.html", group=SERVICE_GROUPS[group], services=services_for_group(group),
        active_service_group=group,
    )


@bp.get("")
@login_required
def index():
    return _hub("payment")


@bp.get("/financial-services")
@login_required
def financial_services():
    return _hub("financial")


@bp.get("/other-services")
@login_required
def other_services():
    return _hub("other")


@bp.route("/recharge", methods=["GET", "POST"])
@login_required
def recharge():
    values = request.form.to_dict() if request.method == "POST" else {"operator": MOBILE_OPERATORS[0]}
    status = 200
    if request.method == "POST":
        try:
            get_container().payments.mobile_recharge(
                session["user_id"], values.get("operator", ""), values.get("mobile", ""), values.get("amount", ""),
            )
            flash("Demo mobile recharge completed and recorded in history.", "success")
            return redirect(url_for("wallet.history"))
        except (ValidationError, InsufficientBalanceError) as exc:
            flash(str(exc), "danger")
            status = 400
    return render_template("payments/recharge.html", values=values, operators=MOBILE_OPERATORS, active_service_group="payment"), status


@bp.route("/pay-bill", methods=["GET", "POST"])
@login_required
def pay_bill():
    values = request.form.to_dict() if request.method == "POST" else {"category": request.args.get("category", "electricity")}
    category = values.get("category", "")
    details = BILL_CATEGORIES.get(category)
    status = 200
    if request.method == "GET" and details:
        values["provider"] = details["providers"][0]
    if not details:
        flash("Choose a valid bill category.", "danger")
        status = 400
    elif request.method == "POST" and values.get("action") != "choose-category":
        try:
            get_container().payments.pay_bill(
                session["user_id"], values.get("provider", ""), values.get("account_no", ""),
                values.get("amount", ""), category=category,
            )
            flash(f"Demo {details['label'].lower()} payment completed and recorded in history.", "success")
            return redirect(url_for("wallet.history"))
        except (ValidationError, InsufficientBalanceError) as exc:
            flash(str(exc), "danger")
            status = 400
    elif request.method == "POST":
        # A no-JavaScript category preview must never move money.
        values["provider"] = details["providers"][0]
    return render_template(
        "payments/pay_bill.html", categories=BILL_CATEGORIES, values=values, details=details,
        active_service_group=details["group"] if details else "payment",
    ), status


@bp.route("/savings", methods=["GET", "POST"])
@login_required
def savings():
    values = request.form.to_dict() if request.method == "POST" else {"months": "12"}
    plan, status = None, 200
    if request.method == "POST":
        try:
            plan = get_container().payments.savings_plan(values.get("amount", ""), values.get("months", ""))
        except ValidationError as exc:
            flash(str(exc), "danger")
            status = 400
    return render_template("payments/savings.html", values=values, plan=plan, active_service_group="financial"), status


@bp.route("/request-money", methods=["GET", "POST"])
@login_required
def request_money():
    values = request.form.to_dict() if request.method == "POST" else {}
    status = 200
    if request.method == "POST":
        try:
            prepared = get_container().payments.money_request(
                session["user_id"], values.get("recipient_mobile", ""), values.get("amount", ""), values.get("note", ""),
            )
            session["prepared_money_request"] = prepared
            flash("Request message prepared. Share it with the recipient to ask for a demo transfer.", "success")
            return redirect(url_for("payments.request_money"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            status = 400
    return render_template(
        "payments/request_money.html", values=values, prepared=session.get("prepared_money_request"),
        active_service_group="financial",
    ), status
