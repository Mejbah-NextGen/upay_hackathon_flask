import unittest
from decimal import Decimal

from app import create_app
from app.domain.models import Transaction, User
from app.extensions import db
from config import DevelopmentConfig


class TestConfig(DevelopmentConfig):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "isolated-test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    ASSISTANT_API_ENABLED = False


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.user = User.query.filter_by(mobile="01329097775").one()
        self.user_id = self.user.id
        Transaction.query.delete()
        self.user.balance = Decimal("1000.00")
        db.session.commit()

    def login(self, user_id=None):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id if user_id is None else user_id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
