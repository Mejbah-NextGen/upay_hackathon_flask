from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import current_user, login_required
from app.container import get_container
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.preference_service import get_preferences

bp = Blueprint("profile", __name__, url_prefix="/profile")


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            get_container().profile.update_profile(
                session["user_id"], request.form.get("full_name", ""), request.form.get("email", "")
            )
            flash("Profile updated.", "success")
            return redirect(url_for("profile.index"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template("profile/index.html", user=current_user()), 400
    return render_template("profile/index.html", user=current_user())


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        preferences = get_preferences(session["user_id"], create=True)
        preferences.notifications_enabled = request.form.get("notifications_enabled") == "on"
        db.session.commit()
        flash("Notification preferences saved.", "success")
        return redirect(url_for("profile.settings"))
    return render_template("profile/settings.html", preferences=get_preferences(session["user_id"]))
