"""Local demo calculations and deferred purchases; no live financial product."""

import calendar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.domain.models import Transaction
from app.domain.payment_plans import PayLaterAccount, PayLaterPurchase, SavingsPlan
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.recipient_service import normalize_reference
from app.services.reporting_service import local_datetime


SAVINGS_ANNUAL_RATE = Decimal("0.10")
PAY_LATER_LIMIT = Decimal("5000.00")
PAY_LATER_TENURES = (7, 14, 30)
PAY_LATER_MERCHANTS = (
    "Demo Grocery Store", "Demo Pharmacy", "Demo Bookshop", "Demo Electronics",
    "Demo Clothing Store", "Demo Home Essentials", "Demo Education Supplies",
    "Demo Travel Booking", "Demo Restaurant", "Demo Internet Subscription",
)


def local_today(now=None):
    return local_datetime(now or datetime.now(timezone.utc)).date()


def add_months(value, months):
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def save_savings_plan(wallet, user_id, name, calculation, *, now=None):
    wallet.get_user(user_id)
    name = str(name or "Monthly savings").strip()
    if not 1 <= len(name) <= 80:
        raise ValidationError("Plan name must be 1 to 80 characters.")
    if SavingsPlan.query.filter_by(user_id=user_id, status="SAVED").count() >= 10:
        raise ValidationError("You can save up to 10 active savings plans. Archive a plan to add another.")
    start = local_today(now)
    plan = SavingsPlan(
        user_id=user_id, name=name, monthly_amount=calculation["monthly_amount"],
        months=calculation["months"], annual_rate=SAVINGS_ANNUAL_RATE,
        contribution_total=calculation["total"], estimated_return=calculation["estimated_return"],
        starts_on=start, matures_on=add_months(start, calculation["months"]), status="SAVED",
    )
    db.session.add(plan)
    db.session.commit()
    return plan


def archive_savings_plan(user_id, plan_id):
    result = db.session.execute(
        update(SavingsPlan).where(SavingsPlan.id == plan_id, SavingsPlan.user_id == user_id, SavingsPlan.status == "SAVED").values(status="ARCHIVED"),
        execution_options={"synchronize_session": "fetch"},
    )
    if result.rowcount != 1:
        db.session.rollback()
        raise ValidationError("Saved savings plan not found.")
    db.session.commit()


def pay_later_summary(user_id, *, now=None):
    purchases = PayLaterPurchase.query.filter_by(user_id=user_id).order_by(PayLaterPurchase.created_at.desc(), PayLaterPurchase.id.desc()).all()
    outstanding = sum((Decimal(item.amount) for item in purchases if item.status == "PENDING"), Decimal("0.00"))
    today = local_today(now)
    return {
        "purchases": purchases, "limit": PAY_LATER_LIMIT, "outstanding": outstanding,
        "available": PAY_LATER_LIMIT - outstanding,
        "overdue": sum((Decimal(item.amount) for item in purchases if item.status == "PENDING" and item.due_on < today), Decimal("0.00")),
        "today": today,
    }


def create_pay_later(wallet, user_id, merchant, invoice_no, amount_raw, tenure, *, now=None):
    wallet.get_user(user_id)
    merchant = str(merchant or "").strip()
    if merchant not in PAY_LATER_MERCHANTS:
        raise ValidationError("Choose a listed demo merchant.")
    invoice_no = normalize_reference(invoice_no).upper()
    amount = wallet.parse_amount(amount_raw)
    if str(tenure) not in {str(days) for days in PAY_LATER_TENURES}:
        raise ValidationError("Choose 7, 14 or 30 days to repay.")
    if PayLaterPurchase.query.filter_by(user_id=user_id, merchant=merchant, invoice_no=invoice_no).first():
        raise ValidationError("This merchant invoice already has a Pay Later record.")
    try:
        account = db.session.get(PayLaterAccount, user_id)
        if account is None:
            # First purchases can arrive together. An account created by the
            # other request must not make this request lose its transaction.
            try:
                with db.session.begin_nested():
                    db.session.add(PayLaterAccount(user_id=user_id, outstanding=Decimal("0.00")))
                    db.session.flush()
            except IntegrityError:
                if db.session.get(PayLaterAccount, user_id) is None:
                    raise
        claimed = db.session.execute(
            update(PayLaterAccount).where(PayLaterAccount.user_id == user_id, PayLaterAccount.outstanding <= PAY_LATER_LIMIT - amount).values(outstanding=PayLaterAccount.outstanding + amount),
            execution_options={"synchronize_session": "fetch"},
        )
        if claimed.rowcount != 1:
            raise ValidationError("This purchase exceeds your available demo Pay Later limit of BDT 5,000.")
        due = local_today(now) + timedelta(days=int(tenure))
        transaction = Transaction(
            user_id=user_id, kind="PAY_LATER_PURCHASE", direction="OUT", title="Pay Later Purchase",
            counterparty=merchant, reference=wallet._reference(), amount=amount, fee=Decimal("0.00"),
            status="DEFERRED", note=f"Invoice: {invoice_no}; repay by {due.isoformat()}; wallet unchanged.",
        )
        db.session.add(transaction)
        db.session.flush()
        purchase = PayLaterPurchase(
            user_id=user_id, merchant=merchant, invoice_no=invoice_no, amount=amount,
            due_on=due, status="PENDING", purchase_transaction_id=transaction.id,
        )
        db.session.add(purchase)
        db.session.commit()
        return purchase
    except IntegrityError:
        db.session.rollback()
        raise ValidationError("This merchant invoice already has a Pay Later record.")
    except Exception:
        db.session.rollback()
        raise


def repay_pay_later(wallet, user_id, purchase_id):
    wallet.get_user(user_id)
    purchase = PayLaterPurchase.query.filter_by(id=purchase_id, user_id=user_id).first()
    if purchase is None:
        raise ValidationError("Pay Later purchase not found.")
    if purchase.status == "REPAID":
        return db.session.get(Transaction, purchase.repayment_transaction_id), False
    try:
        claimed = db.session.execute(
            update(PayLaterPurchase).where(PayLaterPurchase.id == purchase.id, PayLaterPurchase.user_id == user_id, PayLaterPurchase.status == "PENDING").values(status="PROCESSING"),
            execution_options={"synchronize_session": "fetch"},
        )
        if claimed.rowcount != 1:
            raise ValidationError("This purchase is already being repaid.")
        wallet._debit(user_id, Decimal(purchase.amount), "Insufficient wallet balance to repay this purchase.")
        transaction = Transaction(
            user_id=user_id, kind="PAY_LATER_REPAYMENT", direction="OUT", title="Pay Later Repayment",
            counterparty=purchase.merchant, reference=wallet._reference(), amount=purchase.amount,
            fee=Decimal("0.00"), status="SUCCESS", note=f"Repayment for invoice {purchase.invoice_no}; purchase #{purchase.id}.",
        )
        db.session.add(transaction)
        db.session.flush()
        purchase.status = "REPAID"
        purchase.repaid_at = datetime.now(timezone.utc)
        purchase.repayment_transaction_id = transaction.id
        db.session.execute(
            update(PayLaterAccount).where(PayLaterAccount.user_id == user_id).values(outstanding=PayLaterAccount.outstanding - Decimal(purchase.amount)),
            execution_options={"synchronize_session": "fetch"},
        )
        db.session.commit()
        return transaction, True
    except Exception:
        db.session.rollback()
        raise
