import re
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.models import Transaction, User
from app.domain.notifications import NotificationReadState
from app.domain.preferences import UserPreference
from app.extensions import db
from app.services.navigation_service import find_services, notification_summary
from app.services.service_catalog import SERVICES
from tests.helpers import AppTestCase


class NavigationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def transaction(self, title="Gas Payment", user_id=None, **kwargs):
        tx = Transaction(
            user_id=self.user_id if user_id is None else user_id,
            title=title, kind="BILL_PAYMENT", direction="OUT", amount=Decimal("50.00"),
            counterparty=kwargs.pop("counterparty", "Titas Gas"),
            reference=kwargs.pop("reference", "NAV-REF-1"), **kwargs,
        )
        db.session.add(tx)
        db.session.commit()
        return tx

    def second_user(self):
        user = User(full_name="Second User", mobile="01812345678", balance=Decimal("400.00"))
        db.session.add(user)
        db.session.commit()
        return user

    def test_service_search_finds_bill_types_providers_and_financial_tools(self):
        self.assertIn("gas", [service["id"] for service in find_services("gas bill")])
        self.assertIn("gas", [service["id"] for service in find_services("Titas")])
        self.assertEqual([service["id"] for service in find_services("Grameenphone")], ["recharge"])
        self.assertIn("savings", [service["id"] for service in find_services("financial services")])
        self.assertEqual(len(find_services("services")), len(SERVICES))
        self.assertEqual(find_services("%"), [])
        response = self.client.get("/search?q=gas+bill")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/payments/pay-bill?category=gas", response.data)
        self.assertNotIn(b"No services match", response.data)

    def test_bangla_search_keeps_vowel_marks_and_searches_only_own_history(self):
        self.assertIn('gas', [service['id'] for service in find_services('গ্যাস বিল')])
        self.transaction(title='Gas Payment', reference='OWN-BANGLA-SEARCH')
        other=self.second_user()
        self.transaction(title='Gas Payment',user_id=other.id,reference='OTHER-BANGLA-SEARCH')
        response=self.client.get('/search',query_string={'q':'গ্যাস'})
        self.assertEqual(response.status_code,200)
        self.assertIn(b'OWN-BANGLA-SEARCH',response.data)
        self.assertNotIn(b'OTHER-BANGLA-SEARCH',response.data)

    def test_search_is_server_rendered_user_scoped_and_escaped(self):
        self.transaction(title="My Gas Payment", reference="MY-PRIVATE-REF")
        other = self.second_user()
        self.transaction(title="Other Private Gas Payment", user_id=other.id, reference="OTHER-PRIVATE-REF")
        response = self.client.get("/search?q=gas")
        self.assertIn(b"MY-PRIVATE-REF", response.data)
        self.assertNotIn(b"OTHER-PRIVATE-REF", response.data)
        self.assertNotIn(b"Other Private Gas Payment", response.data)
        self.assertIn(b'action="/search"', response.data)
        self.assertIn(b'name="q"', response.data)
        response = self.client.get("/search", query_string={"q": "<script>alert(1)</script>"})
        self.assertNotIn(b"<script>alert(1)</script>", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)

    def test_catalog_routes_exist_and_sidebar_has_one_correct_active_item(self):
        from flask import url_for

        with self.app.test_request_context():
            urls = {url_for(service["endpoint"], **service["params"]) for service in SERVICES}
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for url, label in [
            ("/wallet/add-money", "Add Money"), ("/wallet/send-money", "Send Money"),
            ("/wallet/transfer-money", "Transfer Money"), ("/wallet/cash-out", "Cash Out"),
            ("/wallet/history", "Report"), ("/payments", "Payment"),
            ("/payments/financial-services", "Financial Services"),
            ("/payments/other-services", "Other Services"),
            ("/payments/pay-bill?category=credit-card", "Financial Services"),
            ("/payments/pay-bill?category=toll", "Other Services"),
        ]:
            with self.subTest(url=url):
                html = self.client.get(url).get_data(as_text=True)
                sidebar = html.split('<nav class="side-nav">', 1)[1].split("</nav>", 1)[0]
                active = re.findall(r'<a class="nav-link active"[^>]*>.*?</span>(.*?)</a>', sidebar)
                self.assertEqual(active, [label])

    def test_notification_read_state_persists_isolates_users_and_new_events(self):
        first = self.transaction(title="My Recent Payment")
        other = self.second_user()
        self.transaction(title="Other Secret Payment", user_id=other.id)
        self.assertEqual(notification_summary(self.user_id)["unread_count"], 1)
        response = self.client.get("/notifications")
        self.assertIn(b"My Recent Payment", response.data)
        self.assertNotIn(b"Other Secret Payment", response.data)
        self.assertEqual(self.client.post("/notifications/read").status_code, 302)
        state = db.session.get(NotificationReadState, self.user_id)
        self.assertEqual(state.last_read_transaction_id, first.id)
        self.assertEqual(notification_summary(self.user_id)["unread_count"], 0)
        self.assertEqual(notification_summary(other.id)["unread_count"], 1)
        # The persisted state survives a new client session, then a new event is unread.
        self.client = self.app.test_client()
        self.login()
        self.assertNotIn(b'class="notification-count"', self.client.get("/profile/").data)
        self.transaction(title="New Payment")
        self.assertEqual(notification_summary(self.user_id)["unread_count"], 1)
        self.assertIn(b'class="notification-count"', self.client.get("/profile/").data)

    def test_disabled_alerts_hide_navbar_events_and_keep_activity_available(self):
        self.transaction(title="Hidden Navbar Event")
        db.session.add(UserPreference(user_id=self.user_id, notifications_enabled=False))
        db.session.commit()
        response = self.client.get("/profile/")
        self.assertIn(b"Transaction alerts are turned off", response.data)
        self.assertNotIn(b'class="notification-count"', response.data)
        self.assertNotIn(b"Hidden Navbar Event", response.data)
        self.assertIn(b"Hidden Navbar Event", self.client.get("/notifications").data)
        state = self.client.get("/notifications/summary").json
        self.assertFalse(state["navbar_enabled"])
        self.assertEqual(state["unread_count"], 1)

    def test_search_and_alerts_use_bangladesh_time(self):
        self.transaction(created_at=datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc))
        self.assertIn(b"02 Oct 2026, 12:00", self.client.get("/search?q=gas").data)
        self.assertIn(b"02 Oct 2026, 12:00", self.client.get("/notifications").data)

    def test_page_input_is_bounded_to_available_results_and_search_links_keep_query(self):
        for index in range(21):
            db.session.add(Transaction(
                user_id=self.user_id, title=f"Gas Bill {index}", kind="BILL_PAYMENT",
                direction="OUT", amount=Decimal("1.00"), counterparty="Titas Gas",
                created_at=datetime(2026, 10, 2, 6, index, tzinfo=timezone.utc),
            ))
        db.session.commit()
        for path in ("/search?q=gas+bill", "/notifications"):
            for raw_page, expected in (
                ("999999999999999999999", 2), ("-999999999999999999999", 1),
                ("0", 1), ("invalid", 1), ("1.5", 1), ("1", 1), ("2", 2),
            ):
                with self.subTest(path=path, page=raw_page):
                    separator = "&" if "?" in path else "?"
                    response = self.client.get(f"{path}{separator}page={raw_page}")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(f"Page {expected} of 2".encode(), response.data)
        first = self.client.get("/search?q=gas+bill&page=1")
        second = self.client.get("/search?q=gas+bill&page=2")
        self.assertIn(b'href="/search?q=gas+bill&amp;page=2"', first.data)
        self.assertIn(b'href="/search?q=gas+bill&amp;page=1"', second.data)
        # Empty search results also handle huge offsets without errors.
        self.assertEqual(self.client.get("/search?q=unknown&page=999999999999999999999").status_code, 200)

    def test_notifications_mutation_requires_csrf_and_login(self):
        self.transaction()
        self.app.config["WTF_CSRF_ENABLED"] = True
        self.assertEqual(self.client.post("/notifications/read").status_code, 400)
        self.assertEqual(notification_summary(self.user_id)["unread_count"], 1)
        self.assertEqual(self.client.get("/notifications/read").status_code, 405)
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        for path in ["/search?q=gas", "/notifications"]:
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.client.post("/notifications/read").status_code, 302)
        self.assertEqual(notification_summary(self.user_id)["unread_count"], 1)

    def test_direct_receipt_reads_only_viewed_notification_and_summary_is_private(self):
        first = self.transaction(title="First unread")
        second = self.transaction(title="Second unread")
        other = self.second_user()
        foreign = self.transaction(title="Foreign unread", user_id=other.id)
        self.assertEqual(self.client.get(f"/wallet/transaction/{foreign.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/wallet/transaction/{second.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/wallet/transaction/{second.id}").status_code, 200)
        response = self.client.get("/notifications/summary")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(response.json["unread_count"], 1)
        self.assertIn(second.id, response.json["read_ids"])
        self.assertNotIn(first.id, response.json["read_ids"])
        self.assertNotIn(foreign.id, response.json["read_ids"])
        self.assertEqual(notification_summary(other.id)["unread_count"], 1)
        self.client.get(f"/wallet/transaction/{first.id}")
        self.assertNotIn(b'class="notification-count"', self.client.get("/").data)
        self.client.post("/auth/logout")
        self.assertEqual(self.client.get("/notifications/summary").status_code, 302)

    def test_education_back_retains_dashboard_period_and_rejects_external_targets(self):
        from html import unescape
        from urllib.parse import parse_qs, urlsplit
        html = self.client.get("/?days=30").get_data(as_text=True)
        links = [unescape(value) for value in re.findall(r'href="([^"]+)"', html)]
        education = next(value for value in links if parse_qs(urlsplit(value).query).get("category") == ["education"])
        self.assertEqual(parse_qs(urlsplit(education).query)["return_to"], ["/?days=30"])
        html = self.client.get(education).get_data(as_text=True)
        self.assertIn('class="page-back" href="/?days=30"', html)
        self.assertIn("Back to Dashboard", html)
        for invalid in ("https://example.com", "//example.com", "/auth/logout", "/\\example.com", "/?days=1#fake", "/\nLocation:x"):
            html = self.client.get("/payments/pay-bill", query_string={"category": "education", "return_to": invalid}).get_data(as_text=True)
            self.assertIn('class="page-back" href="/payments"', html)
