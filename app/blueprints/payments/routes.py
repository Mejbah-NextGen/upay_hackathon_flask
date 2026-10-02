from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from uuid import uuid4

from app.auth_helpers import login_required
from app.container import get_container
from app.domain.payment_plans import SavingsPlan
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.payment_plans_service import (
    PAY_LATER_MERCHANTS, PAY_LATER_TENURES, archive_savings_plan, create_pay_later,
    pay_later_summary, repay_pay_later, save_savings_plan,
)
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS, RECHARGE_AMOUNTS, SERVICE_GROUPS, services_for_group
from app.services.validation import MOBILE_OPERATOR_PREFIXES

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
            transaction = get_container().payments.mobile_recharge(
                session["user_id"], values.get("operator", ""), values.get("mobile", ""), values.get("amount", ""),
            )
            flash("Demo mobile recharge completed and recorded in Report.", "success")
            return redirect(url_for("wallet.receipt", transaction_id=transaction.id))
        except (ValidationError, InsufficientBalanceError) as exc:
            flash(str(exc), "danger")
            status = 400
    return render_template("payments/recharge.html", values=values, operators=MOBILE_OPERATORS, amounts=RECHARGE_AMOUNTS, operator_prefixes=MOBILE_OPERATOR_PREFIXES, active_service_group="payment"), status


@bp.route("/pay-bill", methods=["GET", "POST"])
@login_required
def pay_bill():
    locked_category = request.args.get("category", "").strip() if "category" in request.args else None
    values = request.form.to_dict() if request.method == "POST" else {"category": request.args.get("category", "electricity")}
    values.setdefault("submission_token", uuid4().hex)
    category_mismatch = locked_category is not None and values.get("category", locked_category) != locked_category
    if locked_category is not None:
        values["category"] = locked_category
    category = values.get("category", "")
    details = BILL_CATEGORIES.get(category)
    status = 200
    if request.method == "GET" and details:
        values["provider"] = details["providers"][0]
    if not details:
        flash("Choose a valid bill category.", "danger")
        status = 400
    elif category_mismatch:
        flash("This page only accepts the selected payment type. Open Pay Bill to choose another category.", "danger")
        status = 400
    elif request.method == "POST" and values.get("action") != "choose-category":
        try:
            transaction = get_container().payments.pay_bill(
                session["user_id"], values.get("provider", ""), values.get("account_no", ""),
                values.get("amount", ""), category=category,
                invoice_reference=values.get("invoice_reference", ""),
                submission_token=values.get("submission_token", ""),
            )
            flash(f"Demo {details['label'].lower()} payment completed and recorded in Report.", "success")
            return redirect(url_for("wallet.receipt", transaction_id=transaction.id))
        except (ValidationError, InsufficientBalanceError) as exc:
            flash(str(exc), "danger")
            status = 400
    elif request.method == "POST":
        # A no-JavaScript category preview must never move money.
        values["provider"] = details["providers"][0]
    return render_template(
        "payments/pay_bill.html", categories={category: details} if locked_category is not None and details else BILL_CATEGORIES,
        values=values, details=details, locked_category=locked_category is not None,
        active_service_group=details["group"] if details else "payment",
    ), status


@bp.route("/savings", methods=["GET", "POST"])
@login_required
def savings():
    values = request.form.to_dict() if request.method == "POST" else {"months": "12"}
    plan, status = None, 200
    if request.method == "POST":
        try:
            if values.get("action") == "archive":
                archive_savings_plan(session["user_id"], request.form.get("plan_id", type=int))
                flash("Savings plan archived.", "success")
                return redirect(url_for("payments.savings"))
            plan = get_container().payments.savings_plan(values.get("amount", ""), values.get("months", ""))
            if values.get("action") == "save":
                save_savings_plan(get_container().wallet, session["user_id"], values.get("name", ""), plan)
                flash("Savings plan saved with a fixed monthly amount and tenure.", "success")
                return redirect(url_for("payments.savings"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            status = 400
    saved_plans = SavingsPlan.query.filter_by(user_id=session["user_id"], status="SAVED").order_by(SavingsPlan.created_at.desc()).all()
    return render_template("payments/savings.html", values=values, plan=plan, saved_plans=saved_plans, active_service_group="financial"), status


@bp.route("/request-money", methods=["GET", "POST"])
@login_required
def request_money():
    values = request.form.to_dict() if request.method == "POST" else {}
    status = 200
    if request.method == "POST":
        if values.get("action") == "clear":
            session.pop("prepared_money_request", None)
            return redirect(url_for("payments.request_money"))
        try:
            prepared = get_container().payments.money_request(
                session["user_id"], values.get("recipient_mobile", ""), values.get("amount", ""), values.get("note", ""),
                language=session.get("language", "en"),
            )
            session["prepared_money_request"] = prepared
            flash("Request message prepared. Share it with the recipient to ask for a demo transfer.", "success")
            return redirect(url_for("payments.request_money"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            status = 400
    # A prepared share message is shown once after its redirect. Navigating back
    # starts a new request instead of showing an old message indefinitely.
    prepared = session.pop("prepared_money_request", None) if request.method == "GET" else None
    return render_template(
        "payments/request_money.html", values=values, prepared=prepared,
        active_service_group="financial",
    ), status


@bp.route("/pay-later", methods=["GET", "POST"])
@login_required
def pay_later():
    values = request.form.to_dict() if request.method == "POST" else {"tenure": "30", "merchant": PAY_LATER_MERCHANTS[0]}
    status = 200
    if request.method == "POST":
        try:
            if values.get("action") == "repay":
                transaction, repaid_now = repay_pay_later(get_container().wallet, session["user_id"], request.form.get("purchase_id", type=int))
                flash("Demo purchase repaid from your wallet." if repaid_now else "This purchase is already repaid. Showing the existing receipt.", "success")
            else:
                purchase = create_pay_later(
                    get_container().wallet, session["user_id"], values.get("merchant", ""),
                    values.get("invoice_no", ""), values.get("amount", ""), values.get("tenure", ""),
                )
                flash("Deferred demo purchase saved. Repay it by the displayed due date.", "success")
                return redirect(url_for("wallet.receipt", transaction_id=purchase.purchase_transaction_id))
            return redirect(url_for("wallet.receipt", transaction_id=transaction.id))
        except (ValidationError, InsufficientBalanceError) as exc:
            flash(str(exc), "danger")
            status = 400
    return render_template(
        "payments/pay_later.html", values=values, summary=pay_later_summary(session["user_id"]),
        merchants=PAY_LATER_MERCHANTS, tenures=PAY_LATER_TENURES, active_service_group="financial",
    ), status
