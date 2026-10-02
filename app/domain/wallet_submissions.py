"""Atomic form submission receipts prevent accidental duplicate wallet mutations."""

from app.extensions import db


class WalletSubmission(db.Model):
    __tablename__ = "wallet_submissions"
    __table_args__ = (db.UniqueConstraint("user_id", "token", name="uq_wallet_submission_token"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(32), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
