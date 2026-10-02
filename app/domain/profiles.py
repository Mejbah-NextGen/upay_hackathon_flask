"""Additional profile fields stored separately to preserve existing user tables."""

from app.extensions import db


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    nickname = db.Column(db.String(40), nullable=False, default="")
    address = db.Column(db.String(300), nullable=False, default="")
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_mime = db.Column(db.String(30), nullable=True)
