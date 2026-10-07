from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app.auth_helpers import current_user, login_required
from app.container import get_container
from app.domain.security import TrustedSession
from app.extensions import db
from app.services.exceptions import AuthenticationError, ValidationError
from app.services.security_service import (audit_event, create_trusted_session, issue_otp_challenge,
    revoke_current_session, revoke_trusted_session, security_production, _digest, _now)

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.get("/login")
def login():
    if current_user():
        return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html")


@bp.post("/login")
def login_post():
    try:
        user = get_container().auth.start_login(request.form.get("mobile", ""))
        challenge_id = issue_otp_challenge(user)
        session["pending_mobile"] = "*******" + user.mobile[-4:] if security_production() else user.mobile
        session["pending_user_id"] = user.id
        session["otp_challenge"] = challenge_id
        session["auth_flow"] = "login"
        return redirect(url_for("auth.otp"))
    except (AuthenticationError, ValidationError) as exc:
        flash("Unable to start verification. Check your details or try again later." if security_production() else str(exc), "danger")
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
        challenge_id = issue_otp_challenge(user)
        session["pending_mobile"] = "*******" + user.mobile[-4:] if security_production() else user.mobile
        session["pending_user_id"] = user.id
        session["otp_challenge"] = challenge_id
        session["auth_flow"] = "signup"
        flash("Account created. Verify your mobile to continue.", "success")
        return redirect(url_for("auth.otp"))
    except (ValidationError, AuthenticationError) as exc:
        flash(str(exc), "danger")
        return render_template("auth/signup.html"), 400


@bp.route("/otp", methods=["GET", "POST"])
def otp():
    mobile = session.get("pending_mobile")
    if not mobile:
        return redirect(url_for("auth.login"))
    if request.method == "GET":
        return _render_otp(mobile)
    try:
        pending_id = session.get("pending_user_id")
        user = get_container().users.get_by_id(pending_id) if pending_id else (
            None if security_production() else get_container().users.get_by_mobile(mobile))
        if user is None:
            session.pop("pending_mobile", None)
            session.pop("pending_user_id", None)
            session.pop("otp_challenge", None)
            session.pop("auth_flow", None)
            flash("Account not found. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        get_container().auth.verify_otp(request.form.get("otp", ""), session.get("otp_challenge"), user.id)
        user.verified = True
        db.session.commit()
        display = {key: session[key] for key in ("language", "theme") if key in session}
        revoke_current_session()
        session.clear()
        session["user_id"] = user.id
        create_trusted_session(user.id)
        session.update(display)
        if display:
            from app.domain.preferences import DisplayPreference
            preference = db.session.get(DisplayPreference, user.id) or DisplayPreference(user_id=user.id)
            for key, value in display.items():
                setattr(preference, key, value)
            db.session.add(preference)
            db.session.commit()
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard.index"))
    except AuthenticationError as exc:
        audit_event("auth.otp", "rejected")
        db.session.commit()
        flash(str(exc), "danger")
        return _render_otp(mobile), 400


def _render_otp(mobile):
    demo = current_app.config.get("DEMO_OTP_ALLOWED", True) and not security_production()
    return render_template("auth/otp.html", mobile=mobile,
        demo_otp=get_container().auth.demo_otp if demo else None)


@bp.post("/logout")
def logout():
    revoke_current_session()
    display = {key: session[key] for key in ("language", "theme") if key in session}
    session.clear()
    session.update(display)
    flash("Signed out successfully.", "info")
    return redirect(url_for("auth.login"))


@bp.get("/devices")
@login_required
def devices():
    user = current_user()
    active = TrustedSession.query.filter(TrustedSession.user_id == user.id,
        TrustedSession.revoked_at.is_(None), TrustedSession.expires_at > _now()).order_by(TrustedSession.created_at.desc()).all()
    token = session.get("auth_session")
    return render_template("auth/devices.html", devices=active,
        current_session_hash=_digest(token, "session") if token else None)


@bp.post("/devices/<token_hash>/revoke")
@login_required
def revoke_device(token_hash):
    user = current_user()
    if revoke_trusted_session(token_hash, user.id):
        token = session.get("auth_session")
        if token and _digest(token, "session") == token_hash:
            revoke_current_session()
            display = {key: session[key] for key in ("language", "theme") if key in session}
            session.clear()
            session.update(display)
            return redirect(url_for("auth.login"))
        flash("Device session revoked.", "success")
    else:
        flash("Device session not found.", "warning")
    return redirect(url_for("auth.devices"))
