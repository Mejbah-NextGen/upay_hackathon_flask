from decimal import Decimal
from pathlib import Path

from flask import Flask, render_template

from config import DevelopmentConfig
from app.container import build_container, get_container
from app.domain.models import Transaction, User
from app.domain.notifications import NotificationReadState
from app.domain.preferences import UserPreference
from app.domain.profiles import UserProfile
from app.domain.operations import RecipientRegistration, ScheduledPayment
from app.extensions import csrf, db


def create_app(config_object=DevelopmentConfig):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    Path(app.root_path).parent.joinpath("instance").mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.dashboard.routes import bp as dashboard_bp
    from app.blueprints.wallet.routes import bp as wallet_bp
    from app.blueprints.payments.routes import bp as payments_bp
    from app.blueprints.profile.routes import bp as profile_bp
    from app.blueprints.navigation.routes import bp as navigation_bp
    from app.blueprints.assistant.routes import bp as assistant_bp
    from app.blueprints.operations.routes import bp as operations_bp, register_operations_cli

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(navigation_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(operations_bp)
    register_operations_cli(app)

    app.extensions["ioc_container"] = build_container(app)

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template("errors/upload_too_large.html"), 413

    @app.context_processor
    def inject_global_ui():
        from app.auth_helpers import current_user
        from app.services.navigation_service import notification_summary
        from app.services.preference_service import get_preferences
        from app.services.reporting_service import local_datetime

        user = current_user()
        alerts_enabled = bool(user and get_preferences(user.id).notifications_enabled)
        alerts = notification_summary(user.id) if alerts_enabled else {
            "items": [], "unread_count": 0, "read_through": 0,
        }

        return {
            "app_name": app.config["APP_NAME"],
            "currency": app.config["CURRENCY_SYMBOL"],
            "current_user": user,
            "navbar_alerts": alerts,
            "navbar_alerts_enabled": alerts_enabled,
            "ui_local_time": local_datetime,
            "profile_details": get_container().profile.get_details(user.id) if user else None,
        }

    with app.app_context():
        db.create_all()
        _seed_demo_data()
        from app.services.demo_seed import seed_demo_operations
        seed_demo_operations(User.query.filter_by(mobile="01329097775").one())

    return app


def _seed_demo_data():
    if User.query.filter_by(mobile="01329097775").first():
        return

    user = User(
        full_name="Md. Mejbahul Islam",
        mobile="01329097775",
        email="mejbah@example.com",
        balance=Decimal("12450.00"),
        verified=True,
    )
    db.session.add(user)
    db.session.flush()

    samples = [
        ("MOBILE_RECHARGE", "OUT", "Mobile Recharge", "Grameenphone • 017XXXXXXXX", "300.00"),
        ("SEND_MONEY", "OUT", "Send Money", "018XXXXXXXX", "500.00"),
        ("BILL_PAYMENT", "OUT", "Bill Payment", "DESCO", "620.00"),
        ("ADD_MONEY", "IN", "Add Money", "Bank Account", "2000.00"),
    ]
    for kind, direction, title, counterparty, amount in samples:
        db.session.add(
            Transaction(
                user_id=user.id,
                kind=kind,
                direction=direction,
                title=title,
                counterparty=counterparty,
                reference=f"DEMO-{kind[:4]}-{user.id}",
                amount=Decimal(amount),
            )
        )
    db.session.commit()
