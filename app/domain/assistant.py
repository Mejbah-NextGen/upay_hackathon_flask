from app.extensions import db


class AssistantConversation(db.Model):
    """Bounded, server-owned conversation scoped to one authenticated wallet."""

    __tablename__ = "assistant_conversations"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    messages = db.Column(db.Text, nullable=False, default="[]")
