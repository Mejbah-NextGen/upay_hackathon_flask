"""User-owned demo savings plans, deferred payments and bill invoices."""

from datetime import datetime, timezone

from app.extensions import db


class SavingsPlan(db.Model):
    __tablename__ = "savings_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    monthly_amount = db.Column(db.Numeric(12, 2), nullable=False)
    months = db.Column(db.Integer, nullable=False)
    annual_rate = db.Column(db.Numeric(5, 4), nullable=False)
    contribution_total = db.Column(db.Numeric(14, 2), nullable=False)
    estimated_return = db.Column(db.Numeric(14, 2), nullable=False)
    starts_on = db.Column(db.Date, nullable=False)
    matures_on = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="SAVED")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def estimated_maturity(self):
        return self.contribution_total + self.estimated_return


class PayLaterAccount(db.Model):
    __tablename__ = "pay_later_accounts"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    outstanding = db.Column(db.Numeric(12, 2), nullable=False, default=0)


class PayLaterPurchase(db.Model):
    __tablename__ = "pay_later_purchases"
    __table_args__ = (db.UniqueConstraint("user_id", "merchant", "invoice_no", name="uq_pay_later_merchant_invoice"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    merchant = db.Column(db.String(100), nullable=False)
    invoice_no = db.Column(db.String(60), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    due_on = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="PENDING")
    purchase_transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, unique=True)
    repayment_transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    repaid_at = db.Column(db.DateTime(timezone=True), nullable=True)


class PaymentInvoice(db.Model):
    __tablename__ = "payment_invoices"
    __table_args__ = (
        db.UniqueConstraint("user_id", "category", "provider", "invoice_reference", name="uq_payment_invoice_reference"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, unique=True)
    invoice_number = db.Column(db.String(90), nullable=False, unique=True)
    category = db.Column(db.String(40), nullable=False)
    provider = db.Column(db.String(120), nullable=False)
    account_reference = db.Column(db.String(60), nullable=False)
    invoice_reference = db.Column(db.String(60), nullable=True)


class PaymentSubmission(db.Model):
    """Keep request deduplication separate so older invoice tables stay usable."""

    __tablename__ = "payment_submissions"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    token = db.Column(db.String(32), primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False)
