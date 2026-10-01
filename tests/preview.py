"""Run an isolated browser preview; never reads or changes the project database.

Usage: python -m tests.preview
"""

from datetime import datetime, timedelta, timezone

from app import create_app
from app.domain.models import Transaction
from app.extensions import db
from config import DevelopmentConfig


class PreviewConfig(DevelopmentConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


if __name__ == "__main__":
    app = create_app(PreviewConfig)
    with app.app_context():
        for transaction, age in zip(Transaction.query.order_by(Transaction.id).all(), (0, 6, 29, 89)):
            transaction.created_at = datetime.now(timezone.utc) - timedelta(days=age)
        db.session.commit()
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
