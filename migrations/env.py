"""Migration-only app metadata; never auto-create or seed a database."""

from alembic import context
import os
from app import create_app
from app.extensions import db
from config import DevelopmentConfig


class MigrationConfig(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", DevelopmentConfig.SQLALCHEMY_DATABASE_URI)
    AUTO_CREATE_SCHEMA = False
    SEED_DEMO_DATA = False
    SECURITY_PRODUCTION = False
    TESTING = True


app = create_app(MigrationConfig)
with app.app_context():
    try:
        with db.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=db.metadata,
                              compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
            with context.begin_transaction():
                context.run_migrations()
    finally:
        db.session.remove()
        db.engine.dispose()
