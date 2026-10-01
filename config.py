import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "hackathon-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'upay_hackathon.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEMO_OTP = os.getenv("DEMO_OTP", "123456")
    APP_NAME = os.getenv("APP_NAME", "UpayX")
    CURRENCY_SYMBOL = "৳"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
