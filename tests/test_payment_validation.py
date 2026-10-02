from datetime import timedelta, timezone
from decimal import Decimal

from app.domain.models import Transaction
from app.domain.operations import ScheduledPayment
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.schedule_service import create_schedule, execute_schedule, scheduling_window
from app.services.service_catalog import BILL_CATEGORIES
from app.services.wallet_catalog import DEMO_BANKS
from tests.helpers import AppTestCase
from tests.test_payments import FormOptions


class PaymentValidationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config["SCHEDULE_AUTO_RUN_ON_REQUEST"] = False
        ScheduledPayment.query.delete()
        db.session.commit()
        self.login()

    def assert_no_wallet_change(self):
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00"), self.user.balance)
        self.assertEqual(0, Transaction.query.count())

    def bank_values(self, **changes):
        values = {"source": "Bank Account", "amount": "125.25", "bank": DEMO_BANKS[0],
                  "account_number": "987654321012", "holder_name": "Demo Account Holder"}
        values.update(changes)
        return values

    def test_generic_bill_page_keeps_all_categories_and_specific_page_only_its_type(self):
        generic = FormOptions(self.client.get("/payments/pay-bill").get_data(as_text=True)).options
        self.assertEqual(set(BILL_CATEGORIES), {item["value"] for item in generic["category"] if item["value"]})
        for category in ("gas", "education-school", "credit-card"):
            html = self.client.get(f"/payments/pay-bill?category={category}").get_data(as_text=True)
            specific = FormOptions(html).options
            self.assertNotIn("category", specific)
            self.assertEqual([""] + list(BILL_CATEGORIES[category]["providers"]), [option["value"] for option in specific["provider"]])

    def test_specific_bill_page_rejects_substituted_category_without_debit(self):
        response = self.client.post("/payments/pay-bill?category=education-school", data={
            "category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-001", "amount": "50",
        })
        self.assertEqual(400, response.status_code)
        self.assertIn(b"only accepts the selected payment type", response.data)
        self.assertIn(b'School Payment', response.data)
        self.assertNotIn(b'Titas Gas', response.data)
        self.assert_no_wallet_change()

    def test_wrong_recharge_prefix_is_rejected_by_post_and_recipient_lookup(self):
        for operator, mobile in (("Grameenphone", "01612345678"), ("Robi", "01712345678"),
                                 ("Airtel", "01912345678"), ("Banglalink", "01512345678"),
                                 ("Teletalk", "01012345678")):
            with self.subTest(operator=operator, mobile=mobile):
                response = self.client.post("/payments/recharge", data={"operator": operator, "mobile": mobile, "amount": "50"})
                self.assertEqual(400, response.status_code)
                found = self.client.get("/operations/recipient", query_string={"kind": "MOBILE_RECHARGE", "provider": operator, "number": mobile})
                self.assertEqual(400, found.status_code)
                self.assertFalse(found.get_json()["can_transact"])
                self.assert_no_wallet_change()

    def test_all_supported_recharge_prefixes_accept_matching_operator(self):
        cases = (("Grameenphone", "013"), ("Grameenphone", "017"), ("Banglalink", "014"),
                 ("Banglalink", "019"), ("Teletalk", "015"), ("Airtel", "016"), ("Robi", "018"))
        for operator, prefix in cases:
            with self.subTest(operator=operator, prefix=prefix):
                response = self.client.post("/payments/recharge", data={"operator": operator, "mobile": f"+88 {prefix}12-345678", "amount": "10"})
                self.assertEqual(302, response.status_code)
        self.assertEqual(len(cases), Transaction.query.count())
        self.assertEqual(Decimal("930.00"), self.user.balance)

    def test_recharge_schedule_validates_prefix_when_created_and_executed(self):
        first_date, _ = scheduling_window()
        values = {"kind": "MOBILE_RECHARGE", "recipient_number": "01612345678", "provider": "Grameenphone",
                  "amount": "50", "frequency": "ONE_TIME", "auto_pay": "1", "due_date": first_date.isoformat()}
        with self.assertRaises(ValidationError):
            create_schedule(self.user_id, values)
        self.assertEqual(0, ScheduledPayment.query.count())
        values["provider"] = "Airtel"
        payment = create_schedule(self.user_id, values)[0]
        # Existing schedules or tampered persisted rows are checked again at execution.
        payment.provider = "Grameenphone"
        db.session.commit()
        result = execute_schedule(self.user_id, payment.id, now=payment.due_at.replace(tzinfo=timezone.utc) + timedelta(seconds=1))
        self.assertEqual("FAILED", result.status)
        self.assertIn("Choose Airtel", result.last_error)
        self.assert_no_wallet_change()

    def test_add_money_requires_source_details_and_rejects_bad_bank_inputs(self):
        for changes in ({"bank": ""}, {"bank": "Unknown Bank"}, {"account_number": ""},
                        {"account_number": "abc123"}, {"account_number": "12345"}, {"holder_name": ""},
                        {"holder_name": "X"}, {"holder_name": "Bad\nName"}):
            with self.subTest(changes=changes):
                response = self.client.post("/wallet/add-money", data=self.bank_values(**changes))
                self.assertEqual(400, response.status_code)
                self.assert_no_wallet_change()
        for source in ("Bank Account", "Debit / Credit Card", "Agent"):
            self.assertEqual(400, self.client.post("/wallet/add-money", data={"source": source, "amount": "100"}).status_code)
            self.assert_no_wallet_change()

    def test_bank_funding_records_only_masked_account(self):
        response = self.client.post("/wallet/add-money", data=self.bank_values())
        self.assertEqual(302, response.status_code)
        tx = Transaction.query.one()
        self.assertEqual("Bank Account", tx.counterparty)
        self.assertIn(DEMO_BANKS[0], tx.note)
        self.assertIn("account ending 1012", tx.note)
        self.assertNotIn("987654321012", tx.note)
        self.assertEqual(Decimal("1125.25"), self.user.balance)
        self.assertNotIn(b"987654321012", self.client.get(response.location).data)

    def test_card_funding_validates_checksum_and_never_echoes_or_stores_number(self):
        for number in ("", "4242424242424241", "0000000000000000", "not-a-card", "424242424242"):
            with self.subTest(number=number):
                response = self.client.post("/wallet/add-money", data={"source": "Debit / Credit Card", "amount": "100", "card_number": number, "holder_name": "Demo Card Holder"})
                self.assertEqual(400, response.status_code)
                if number:
                    self.assertNotIn(number.encode(), response.data)
                self.assert_no_wallet_change()
        response = self.client.post("/wallet/add-money", data={"source": "Debit / Credit Card", "amount": "100", "card_number": "4242 4242 4242 4242", "holder_name": "Demo Card Holder"})
        self.assertEqual(302, response.status_code)
        tx = Transaction.query.one()
        self.assertIn("card ending 4242", tx.note)
        for full_number in ("4242424242424242", "4242 4242 4242 4242"):
            self.assertNotIn(full_number, tx.note + tx.counterparty)
            self.assertNotIn(full_number.encode(), self.client.get(response.location).data)

    def test_source_preview_never_adds_money_and_agent_validates_mobile(self):
        response = self.client.post("/wallet/add-money", data={"action": "choose-source", "source": "Debit / Credit Card", "amount": "100"})
        self.assertEqual(200, response.status_code)
        self.assert_no_wallet_change()
        self.assertEqual(400, self.client.post("/wallet/add-money", data={"source": "Agent", "agent_number": "123", "amount": "100"}).status_code)
        self.assert_no_wallet_change()
        response = self.client.post("/wallet/add-money", data={"source": "Agent", "agent_number": "+88 01944-000002", "amount": "100"})
        self.assertEqual(302, response.status_code)
        self.assertIn("01944000002", Transaction.query.one().note)
        self.assertEqual(Decimal("1100.00"), self.user.balance)
