from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for, send_file
from io import BytesIO

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
                session["user_id"], request.form.get("full_name", ""), request.form.get("email", ""),
                nickname=request.form.get("nickname", ""), address=request.form.get("address", ""),
                photo=request.files.get("photo"), remove_photo=request.form.get("remove_photo") == "on",
            )
            flash("Profile updated.", "success")
            return redirect(url_for("profile.index"))
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template("profile/index.html", user=current_user()), 400
    return render_template("profile/index.html", user=current_user())


@bp.get("/photo")
@login_required
def photo():
    details = get_container().profile.get_details(session["user_id"])
    if not details.photo_data:
        abort(404)
    response = send_file(BytesIO(details.photo_data), mimetype="image/jpeg", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
