from datetime import datetime, timezone

from app.extensions import db


class NotificationReadState(db.Model):
    """A user's transaction alerts are read through this transaction ID."""

    __tablename__ = "notification_read_states"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    last_read_transaction_id = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
