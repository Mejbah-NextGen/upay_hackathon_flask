"""Privacy-minimal review signals; these are not fraud determinations."""

from app.extensions import db


class TransactionReviewFlag(db.Model):
    __tablename__ = "transaction_review_flags"
    __table_args__ = (db.UniqueConstraint("transaction_id", "rule", name="uq_transaction_review_rule"),)

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, index=True)
    rule = db.Column(db.String(32), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="OPEN", index=True)
    created_at = db.Column(db.BigInteger, nullable=False)
