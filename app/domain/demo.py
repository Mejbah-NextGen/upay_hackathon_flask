"""Explicit opening ledger anchors and provenance for generated demonstrations."""

from app.extensions import db


class WalletOpeningBalance(db.Model):
    __tablename__ = "wallet_opening_balances"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    opening_balance = db.Column(db.Numeric(12, 2), nullable=False)
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False)
    source = db.Column(db.String(120), nullable=False)


class DemoDataset(db.Model):
    __tablename__ = "demo_datasets"

    run_key = db.Column(db.String(80), primary_key=True)
    starts_on = db.Column(db.Date, nullable=False)
    ends_on = db.Column(db.Date, nullable=False)
    generated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    generator_version = db.Column(db.String(40), nullable=False)
    synthetic = db.Column(db.Boolean, nullable=False, default=True)
    description = db.Column(db.String(500), nullable=False)
