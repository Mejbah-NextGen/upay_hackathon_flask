from app.domain.preferences import UserPreference
from app.extensions import db


def get_preferences(user_id, create=False):
    preferences = db.session.get(UserPreference, user_id)
    if preferences is None:
        preferences = UserPreference(user_id=user_id, notifications_enabled=True)
        if create:
            db.session.add(preferences)
    return preferences


def notifications_enabled(user_id):
    preferences = get_preferences(user_id)
    return preferences.notifications_enabled
