from decimal import Decimal
from html.parser import HTMLParser

from flask import url_for

from app.domain.models import Transaction
from app.extensions import db
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS, SERVICES
from tests.helpers import AppTestCase


class FormOptions(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.select = None
        self.options = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.select = attrs.get("name")
            self.options[self.select] = []
        elif tag == "option" and self.select:
            self.options[self.select].append(attrs)

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None


class PaymentTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def assert_wallet_unchanged(self):
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00"), self.user.balance)
        self.assertEqual(0, Transaction.query.count())

    def test_every_catalog_link_opens_a_real_service(self):
        with self.app.test_request_context():
            links = [url_for(service["endpoint"], **service["params"]) for service in SERVICES]
        for link in links:
            with self.subTest(link=link):
                self.assertEqual(200, self.client.get(link).status_code)

    def test_hubs_have_distinct_relevant_services(self):
        payments = self.client.get("/payments").get_data(as_text=True)
        financial = self.client.get("/payments/financial-services").get_data(as_text=True)
        other = self.client.get("/payments/other-services").get_data(as_text=True)
        self.assertIn('href="/payments/pay-bill?category=gas"', payments)
        self.assertNotIn('href="/payments/savings"', payments)
        self.assertIn('href="/payments/savings"', financial)
        self.assertIn('href="/payments/request-money"', financial)
        self.assertIn('href="/payments/pay-bill?category=insurance"', financial)
        self.assertIn('href="/payments/pay-bill?category=hotel"', other)
        self.assertIn('href="/payments/pay-bill?category=donation"', other)

    def test_gas_opens_selected_category_with_only_gas_providers_enabled(self):
        response = self.client.get("/payments/pay-bill?category=gas")
        html = response.get_data(as_text=True)
        options = FormOptions(html).options
        self.assertIn("Gas Payment", html)
        self.assertEqual(["gas"], [item["value"] for item in options["category"] if "selected" in item])
        enabled_providers = [item["value"] for item in options["provider"] if item["value"] and "disabled" not in item]
        self.assertEqual(list(BILL_CATEGORIES["gas"]["providers"]), enabled_providers)
        self.assertFalse(set(enabled_providers).intersection(MOBILE_OPERATORS))

    def test_wrong_category_provider_rejected_without_debit_and_input_retained(self):
        response = self.client.post("/payments/pay-bill", data={
            "category": "gas", "provider": "Grameenphone", "account_no": "GAS-12345", "amount": "99.00",
        })
        html = response.get_data(as_text=True)
        self.assertEqual(400, response.status_code)
        self.assertIn("Choose a listed provider for Gas", html)
        self.assertIn('value="GAS-12345"', html)
        self.assertIn('value="99.00"', html)
        self.assertIn("Gas Payment", html)
        self.assert_wallet_unchanged()

    def test_unknown_category_rejected(self):
        for method in ("get", "post"):
            with self.subTest(method=method):
                if method == "get":
                    response = self.client.get("/payments/pay-bill?category=unknown")
                else:
                    response = self.client.post("/payments/pay-bill", data={"category": "unknown", "provider": "Titas Gas", "account_no": "1234", "amount": "100"})
                self.assertEqual(400, response.status_code)
        self.assert_wallet_unchanged()

    def test_all_bill_categories_record_correct_receipt_and_debit(self):
        for category, details in BILL_CATEGORIES.items():
            with self.subTest(category=category):
                response = self.client.post("/payments/pay-bill", data={
                    "category": category, "provider": details["providers"][0], "account_no": "REF-12345", "amount": "10.00",
                })
                self.assertEqual(302, response.status_code)
                self.assertIn("/wallet/transaction/", response.location)
                tx = Transaction.query.order_by(Transaction.id.desc()).first()
                self.assertEqual("BILL_PAYMENT", tx.kind)
                self.assertEqual(f"{details['label']} Payment", tx.title)
                self.assertEqual(f"{details['providers'][0]} • REF-12345", tx.counterparty)
                self.assertEqual(Decimal("10.00"), tx.amount)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00") - Decimal("10.00") * len(BILL_CATEGORIES), self.user.balance)
        self.assertEqual(len(BILL_CATEGORIES), Transaction.query.count())

    def test_invalid_reference_and_insufficient_balance_keep_wallet_unchanged(self):
        for reference, amount in (("", "10"), ("<script>", "10"), ("A" * 61, "10"), ("VALID-1234", "1001")):
            with self.subTest(reference=reference, amount=amount):
                response = self.client.post("/payments/pay-bill", data={"category": "gas", "provider": "Titas Gas", "account_no": reference, "amount": amount})
                self.assertEqual(400, response.status_code)
                self.assert_wallet_unchanged()

    def test_category_preview_does_not_process_payment(self):
        response = self.client.post("/payments/pay-bill", data={"action": "choose-category", "category": "gas", "provider": "DESCO Electricity", "account_no": "KEEP-123", "amount": "50"})
        self.assertEqual(200, response.status_code)
        self.assertIn("Gas Payment", response.get_data(as_text=True))
        self.assert_wallet_unchanged()

    def test_recharge_validates_operator_and_mobile_and_keeps_values(self):
        for operator, mobile in (("Titas Gas", "01712345678"), ("Grameenphone", "01712"), ("Robi", "01712345678abc")):
            with self.subTest(operator=operator, mobile=mobile):
                response = self.client.post("/payments/recharge", data={"operator": operator, "mobile": mobile, "amount": "50.00"})
                self.assertEqual(400, response.status_code)
                self.assertIn(f'value="{mobile}"', response.get_data(as_text=True))
                self.assertIn('value="50.00"', response.get_data(as_text=True))
                self.assert_wallet_unchanged()

    def test_recharge_normalizes_mobile_and_records_once(self):
        response = self.client.post("/payments/recharge", data={"operator": "Airtel", "mobile": "+88 01612-345678", "amount": "50"})
        self.assertEqual(302, response.status_code)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("950.00"), self.user.balance)
        tx = Transaction.query.one()
        self.assertEqual("MOBILE_RECHARGE", tx.kind)
        self.assertEqual("Airtel • 01612345678", tx.counterparty)

    def test_savings_calculator_shows_plan_without_wallet_transaction(self):
        response = self.client.post("/payments/savings", data={"amount": "100.00", "months": "12"})
        self.assertEqual(200, response.status_code)
        self.assertIn("Total contributions: ৳ 1200.00", response.get_data(as_text=True))
        for months in ("0", "121", "12.5", "abc"):
            with self.subTest(months=months):
                self.assertEqual(400, self.client.post("/payments/savings", data={"amount": "100", "months": months}).status_code)
        self.assert_wallet_unchanged()

    def test_request_money_prepares_message_without_transfer(self):
        response = self.client.post("/payments/request-money", data={"recipient_mobile": "01712345678", "amount": "125.50", "note": "Lunch"}, follow_redirects=True)
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn("requests BDT 125.50", html)
        self.assertIn(self.user.mobile, html)
        self.assertIn("Note: Lunch", html)
        with self.client.session_transaction() as session:
            self.assertNotIn("prepared_money_request", session)
        self.assertNotIn("requests BDT 125.50", self.client.get("/payments/request-money").get_data(as_text=True))
        self.assert_wallet_unchanged()
        self.assertEqual(400, self.client.post("/payments/request-money", data={"recipient_mobile": self.user.mobile, "amount": "100"}).status_code)
        self.assert_wallet_unchanged()

    def test_payment_services_require_login(self):
        with self.client.session_transaction() as session:
            session.clear()
        for link in ("/payments", "/payments/financial-services", "/payments/other-services", "/payments/recharge", "/payments/pay-bill?category=gas", "/payments/savings", "/payments/request-money"):
            with self.subTest(link=link):
                response = self.client.get(link)
                self.assertEqual(302, response.status_code)
                self.assertTrue(response.location.endswith("/auth/login"))
