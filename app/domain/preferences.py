from app.extensions import db


class UserPreference(db.Model):
    """Persistent display preferences, kept separate from the existing user schema."""

    __tablename__ = "user_preferences"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    notifications_enabled = db.Column(db.Boolean, nullable=False, default=True)
