import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "hackathon-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'upay_hackathon.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEMO_OTP = os.getenv("DEMO_OTP", "123456")
    APP_NAME = os.getenv("APP_NAME", "UpayX")
    CURRENCY_SYMBOL = "৳"
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "gpt-4.1-mini")
    ASSISTANT_API_ENABLED = bool(OPENAI_API_KEY)
    SCHEDULE_AUTO_RUN_ON_REQUEST = True
    AUTO_CREATE_SCHEMA = True
    SEED_DEMO_DATA = True
    SECURITY_PRODUCTION = False
    REQUIRE_TRUSTED_SESSIONS = False
    DEMO_OTP_ALLOWED = True
    DEMO_BALANCES_ALLOWED = True
    DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY", "")
    DATA_ENCRYPTION_KEYS = os.getenv("DATA_ENCRYPTION_KEYS", "")
    REQUIRE_DATA_ENCRYPTION = False
    OBSERVABILITY_TOKEN = os.getenv("OBSERVABILITY_TOKEN", "")
    SECURITY_HASH_KEY = os.getenv("SECURITY_HASH_KEY", "")
    AUDIT_SIGNING_KEY = os.getenv("AUDIT_SIGNING_KEY", "")
    MONITOR_LARGE_AMOUNT_BDT = os.getenv("MONITOR_LARGE_AMOUNT_BDT", "50000")
    MONITOR_BURST_COUNT = 5
    MONITOR_BURST_SECONDS = 60
    TRUST_PROXY = False
    PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL", "")
    PROVIDER_SIGNING_SECRET = os.getenv("PROVIDER_SIGNING_SECRET", "")
    PROVIDER_ALLOW_LOOPBACK_HTTP = True
    PROVIDER_HTTP_TIMEOUT = 5
    PROVIDER_MAX_ATTEMPTS = 8
    PROVIDER_LEASE_SECONDS = 60
    API_TOKEN_MAX_TTL_DAYS = 30
    AI_CHAT_RETENTION_DAYS = 7
    WORKER_BATCH_SIZE = 50
    WORKER_MAX_ATTEMPTS = 5
    WORKER_RETRY_SECONDS = 30


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SECURITY_PRODUCTION = True
    REQUIRE_TRUSTED_SESSIONS = True
    DEMO_OTP_ALLOWED = False
    DEMO_BALANCES_ALLOWED = False
    REQUIRE_DATA_ENCRYPTION = True
    AUTO_CREATE_SCHEMA = False
    SEED_DEMO_DATA = False
    SCHEDULE_AUTO_RUN_ON_REQUEST = False
    PROVIDER_ALLOW_LOOPBACK_HTTP = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 10, "pool_recycle": 300}
    TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
    DATABASE_SSL_REQUIRED = os.getenv("DATABASE_SSL_REQUIRED", "1") == "1"


def validate_runtime_config(app):
    """Reject demo persistence and weak secrets in the production profile."""
    from sqlalchemy.engine import make_url
    from decimal import Decimal, InvalidOperation
    try:
        threshold = Decimal(str(app.config.get("MONITOR_LARGE_AMOUNT_BDT", "50000")))
        if not threshold.is_finite() or threshold <= 0:
            raise ValueError("Transaction review threshold must be positive and finite.")
        for key, fallback in (("MONITOR_BURST_COUNT", 5), ("MONITOR_BURST_SECONDS", 60),
                              ("WORKER_MAX_ATTEMPTS", 5), ("WORKER_RETRY_SECONDS", 30),
                              ("WORKER_BATCH_SIZE", 50)):
            if int(app.config.get(key, fallback)) < 1:
                raise ValueError(key + " must be a positive integer.")
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid transaction monitoring or worker configuration.") from exc
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if url.drivername in {"postgres", "postgresql"}:
        app.config["SQLALCHEMY_DATABASE_URI"] = url.set(drivername="postgresql+psycopg")
    if not app.config.get("SECURITY_PRODUCTION"):
        return
    secret = app.config.get("SECRET_KEY", "")
    if len(secret) < 32 or secret in {"hackathon-dev-secret-change-me", "replace-with-a-long-random-secret"}:
        raise ValueError("Production requires a unique SECRET_KEY of at least 32 characters.")
    for key in ("SECURITY_HASH_KEY", "AUDIT_SIGNING_KEY"):
        configured = app.config.get(key)
        if configured and (not isinstance(configured, str) or len(configured) < 32):
            raise ValueError(key + " must contain at least 32 characters when configured in production.")
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("Production requires PostgreSQL; SQLite is reserved for local demos.")
    if app.config.get("AUTO_CREATE_SCHEMA") or app.config.get("SEED_DEMO_DATA") or app.config.get("DEMO_OTP_ALLOWED") or app.config.get("DEMO_BALANCES_ALLOWED"):
        raise ValueError("Production cannot auto-create schemas, seed demo data or accept the shared demo OTP.")
    if app.config.get("DATABASE_SSL_REQUIRED", True) and url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Production PostgreSQL requires TLS via sslmode; use verify-full with a managed service CA.")
    if not app.config.get("SESSION_COOKIE_SECURE") or not app.config.get("REQUIRE_TRUSTED_SESSIONS"):
        raise ValueError("Production requires secure cookies and server-validated sessions.")
    from app.services.encryption_service import _cipher
    if not app.config.get("REQUIRE_DATA_ENCRYPTION"):
        raise ValueError("Production cannot disable application-field encryption.")
    with app.app_context():
        if _cipher() is None:
            raise ValueError("Production requires application data encryption.")
