from app.extensions import db


class UserPreference(db.Model):
    """Persistent display preferences, kept separate from the existing user schema."""

    __tablename__ = "user_preferences"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    notifications_enabled = db.Column(db.Boolean, nullable=False, default=True)


class DisplayPreference(db.Model):
    """Separate table so existing databases need no destructive schema change."""

    __tablename__ = "display_preferences"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    language = db.Column(db.String(2), nullable=False, default="en")
    theme = db.Column(db.String(6), nullable=False, default="system")
