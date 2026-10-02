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


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
