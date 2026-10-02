from decimal import Decimal

from app.domain.models import Transaction, User
from app.extensions import db
from app.services.exceptions import ValidationError
from app.services.wallet_service import WalletService
from tests.helpers import AppTestCase


class WalletTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_invalid_amounts_are_errors_without_balance_changes(self):
        for amount in ("", "NaN", "Infinity", "-Infinity", "sNaN", "1e999999", "0", "-1", "1.234", "100000.01"):
            with self.subTest(amount=amount):
                response = self.client.post("/wallet/add-money", data={"source": "Bank Account", "amount": amount})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.user.balance, Decimal("1000.00"))
                self.assertEqual(Transaction.query.count(), 0)

    def test_add_money_records_source_and_updates_balance(self):
        response = self.client.post("/wallet/add-money", data={"source": "Debit / Credit Card", "amount": "125.25", "card_number": "4111 1111 1111 1111", "holder_name": "Demo Card Holder"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.balance, Decimal("1125.25"))
        transaction = Transaction.query.one()
        self.assertEqual((transaction.kind, transaction.direction), ("ADD_MONEY", "IN"))
        self.assertEqual(transaction.counterparty, "Debit / Credit Card")

    def test_unknown_add_money_source_is_rejected(self):
        response = self.client.post("/wallet/add-money", data={"source": "Arbitrary source", "amount": "100"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.balance, Decimal("1000.00"))

    def test_transfer_credits_existing_recipient_with_matching_reference(self):
        recipient = User(full_name="Recipient Test", mobile="01712345678", balance=Decimal("50.00"))
        db.session.add(recipient)
        db.session.commit()
        response = self.client.post("/wallet/send-money", data={"recipient_mobile": "+8801712345678", "amount": "150.25", "note": "Lunch"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.balance, Decimal("849.75"))
        self.assertEqual(recipient.balance, Decimal("200.25"))
        outgoing = Transaction.query.filter_by(user_id=self.user_id).one()
        incoming = Transaction.query.filter_by(user_id=recipient.id).one()
        self.assertEqual(outgoing.reference, incoming.reference)
        self.assertEqual(incoming.direction, "IN")
        self.assertEqual(outgoing.amount, incoming.amount)

    def test_invalid_unknown_and_self_recipient_do_not_debit(self):
        for recipient in ("garbage", "01712345678", self.user.mobile):
            with self.subTest(recipient=recipient):
                response = self.client.post("/wallet/send-money", data={"recipient_mobile": recipient, "amount": "50"})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.user.balance, Decimal("1000.00"))
                self.assertEqual(Transaction.query.count(), 0)

    def test_cash_out_rounds_fee_and_records_full_deduction(self):
        response = self.client.post("/wallet/cash-out", data={"agent_number": "01712345678", "amount": "67"})
        self.assertEqual(response.status_code, 302)
        transaction = Transaction.query.one()
        self.assertEqual(transaction.fee, Decimal("1.01"))
        self.assertEqual(self.user.balance, Decimal("931.99"))

    def test_cash_out_checks_balance_including_fee(self):
        response = self.client.post("/wallet/cash-out", data={"agent_number": "01712345678", "amount": "1000"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        self.assertEqual(Transaction.query.count(), 0)

    def test_failed_form_preserves_entered_values(self):
        response = self.client.post("/wallet/send-money", data={"recipient_mobile": "01712345678", "amount": "100.25", "note": "Rent payment"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'value="01712345678"', response.data)
        self.assertIn(b'value="100.25"', response.data)
        self.assertIn(b"Rent payment", response.data)

    def test_amount_parser_returns_exact_decimal(self):
        self.assertEqual(WalletService.parse_amount("12.34"), Decimal("12.34"))
        with self.assertRaises(ValidationError):
            WalletService.parse_amount("NaN")

