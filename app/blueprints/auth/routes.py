from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.container import get_container
from app.services.exceptions import AuthenticationError, ValidationError

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.get("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html")


@bp.post("/login")
def login_post():
    try:
        user = get_container().auth.start_login(request.form.get("mobile", ""))
        session["pending_mobile"] = user.mobile
        session["auth_flow"] = "login"
        return redirect(url_for("auth.otp"))
    except (AuthenticationError, ValidationError) as exc:
        flash(str(exc), "danger")
        return render_template("auth/login.html"), 400


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("auth/signup.html")
    try:
        user = get_container().auth.register(
            request.form.get("full_name", ""),
            request.form.get("mobile", ""),
            request.form.get("email", ""),
        )
        session["pending_mobile"] = user.mobile
        session["auth_flow"] = "signup"
        flash("Account created. Verify the demo OTP to continue.", "success")
        return redirect(url_for("auth.otp"))
    except ValidationError as exc:
        flash(str(exc), "danger")
        return render_template("auth/signup.html"), 400


@bp.route("/otp", methods=["GET", "POST"])
def otp():
    mobile = session.get("pending_mobile")
    if not mobile:
        return redirect(url_for("auth.login"))
    if request.method == "GET":
        return render_template("auth/otp.html", mobile=mobile, demo_otp=get_container().auth.demo_otp)
    try:
        get_container().auth.verify_otp(request.form.get("otp", ""))
        user = get_container().users.get_by_mobile(mobile)
        if user is None:
            session.pop("pending_mobile", None)
            session.pop("auth_flow", None)
            flash("Account not found. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        display = {key: session[key] for key in ("language", "theme") if key in session}
        session.clear()
        session["user_id"] = user.id
        session.update(display)
        if display:
            from app.domain.preferences import DisplayPreference
            from app.extensions import db
            preference = db.session.get(DisplayPreference, user.id) or DisplayPreference(user_id=user.id)
            for key, value in display.items():
                setattr(preference, key, value)
            db.session.add(preference)
            db.session.commit()
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard.index"))
    except AuthenticationError as exc:
        flash(str(exc), "danger")
        return render_template("auth/otp.html", mobile=mobile, demo_otp=get_container().auth.demo_otp), 400


@bp.post("/logout")
def logout():
    display = {key: session[key] for key in ("language", "theme") if key in session}
    session.clear()
    session.update(display)
    flash("Signed out successfully.", "info")
    return redirect(url_for("auth.login"))
