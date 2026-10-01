import re

from app.domain.models import User
from app.domain.preferences import UserPreference
from app.extensions import db
from tests.helpers import AppTestCase


class AccountTests(AppTestCase):
    def test_demo_login_otp_and_logout(self):
        response = self.client.post("/auth/login", data={"mobile": "+8801329097775"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/otp", response.location)
        self.assertEqual(self.client.post("/auth/otp", data={"otp": "000000"}).status_code, 400)
        self.assertEqual(self.client.post("/auth/otp", data={"otp": "123456"}).status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], self.user_id)
        self.assertEqual(self.client.post("/auth/logout").status_code, 302)
        self.assertIn("/auth/login", self.client.get("/wallet/history").location)

    def test_deleted_account_session_redirects_instead_of_crashing(self):
        self.login(999999)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_otp_for_missing_account_returns_to_login_without_crashing(self):
        with self.client.session_transaction() as session:
            session["pending_mobile"] = "01712345678"
            session["auth_flow"] = "login"
        response = self.client.post("/auth/otp", data={"otp": "123456"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
            self.assertNotIn("pending_mobile", session)

    def test_registration_rejects_letter_contaminated_mobile_and_bad_email(self):
        for mobile, email in (("garbage01329097776", ""), ("01329097776", "invalid-email")):
            with self.subTest(mobile=mobile, email=email):
                response = self.client.post("/auth/signup", data={"full_name": "Test Person", "mobile": mobile, "email": email})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(User.query.count(), 1)

    def test_profile_validation_does_not_partially_update_account(self):
        self.login()
        original_name = self.user.full_name
        response = self.client.post("/profile/", data={"full_name": "Valid Changed Name", "email": "bad-email"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.full_name, original_name)
        response = self.client.post("/profile/", data={"full_name": "Updated Person", "email": "updated@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.full_name, "Updated Person")
        self.assertEqual(self.user.email, "updated@example.com")

    def test_notification_setting_persists_across_sessions(self):
        self.login()
        self.assertEqual(self.client.get("/profile/settings").status_code, 200)
        self.assertEqual(self.client.post("/profile/settings", data={}).status_code, 302)
        self.assertFalse(db.session.get(UserPreference, self.user_id).notifications_enabled)
        self.client.post("/auth/logout")
        self.login()
        response = self.client.get("/profile/settings")
        self.assertNotIn(b'name="notifications_enabled" checked', response.data)
        self.assertEqual(self.client.post("/profile/settings", data={"notifications_enabled": "on"}).status_code, 302)
        self.assertTrue(db.session.get(UserPreference, self.user_id).notifications_enabled)

    def test_csrf_protects_mutating_endpoints(self):
        self.login()
        self.app.config["WTF_CSRF_ENABLED"] = True
        for path in ("/wallet/add-money", "/wallet/send-money", "/wallet/cash-out", "/payments/recharge", "/payments/pay-bill", "/profile/settings", "/auth/logout"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, data={}).status_code, 400)
        response = self.client.get("/wallet/add-money")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()
        response = self.client.post("/wallet/add-money", data={"source": "Bank Account", "amount": "10", "csrf_token": token})
        self.assertEqual(response.status_code, 302)
