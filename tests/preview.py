"""Run an isolated browser preview; never reads or changes the project database.

Usage: python -m tests.preview
"""

from app import create_app
from config import DevelopmentConfig


class PreviewConfig(DevelopmentConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


if __name__ == "__main__":
    app = create_app(PreviewConfig)
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
