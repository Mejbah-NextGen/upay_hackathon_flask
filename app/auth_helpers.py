from functools import wraps

from flask import flash, redirect, session, url_for

from app.container import get_container


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_container().users.get_by_id(user_id)
    if user is None:
        session.pop("user_id", None)
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped
