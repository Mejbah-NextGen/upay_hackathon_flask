"""Destination validation and exact scoped ledger effects for the new demo rails."""

from decimal import Decimal
import re

from app.domain.models import Transaction, User
from app.domain.wallet_submissions import WalletSubmission
from app.extensions import db
from app.services.wallet_catalog import DEMO_ATMS, DEMO_BANKS
from tests.helpers import AppTestCase


class WalletChannelTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def bank_values(self, **changes):
        values = {"channel": "BANK", "bank": DEMO_BANKS[0], "rail": "NPSB",
                  "account_number": "1234567890", "holder_name": "Demo Recipient", "amount": "125.25"}
        values.update(changes)
        return values

    def test_agent_and_atm_have_distinct_quotes_and_ledger_deductions(self):
        for channel, amount, fee, remaining in (("AGENT", "67", "1.01", "931.99"), ("ATM", "500", "5.00", "495.00")):
            with self.subTest(channel=channel):
                self.user.balance = Decimal("1000.00")
                Transaction.query.delete()
                db.session.commit()
                quoted = self.client.get("/wallet/quote", query_string={"operation": "cash-out", "channel": channel, "amount": amount})
                self.assertEqual(quoted.status_code, 200)
                values = quoted.get_json()
                self.assertEqual((values["fee"], values["remaining"], values["can_submit"]), (fee, remaining, True))
                response = self.client.post("/wallet/cash-out", data={"channel": channel, "agent_number": "01944000002", "atm_location": next(iter(DEMO_ATMS)), "amount": amount})
                self.assertEqual(response.status_code, 302)
                transaction = Transaction.query.one()
                self.assertEqual(transaction.fee, Decimal(fee))
                self.assertEqual(self.user.balance, Decimal(remaining))
                self.assertIn(channel if channel == "ATM" else "Agent", transaction.title)

    def test_atm_amount_location_and_channel_validation_prevent_debits(self):
        for changes in ({"amount": "501"}, {"amount": "0.01"}, {"amount": "20500"}, {"atm_location": "REAL-UNKNOWN-ATM"}, {"channel": "OTHER"}):
            values = {"channel": "ATM", "atm_location": next(iter(DEMO_ATMS)), "amount": "500"}
            values.update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post("/wallet/cash-out", data=values).status_code, 400)
                self.assertEqual(self.user.balance, Decimal("1000.00"))
                self.assertEqual(Transaction.query.count(), 0)

    def test_bank_rail_fees_and_bftn_alias_are_recorded_exactly(self):
        for rail, fee, expected_rail in (("NPSB", "10.00", "NPSB"), ("BEFTN", "0.00", "BEFTN"), ("BFTN", "0.00", "BEFTN")):
            with self.subTest(rail=rail):
                self.user.balance = Decimal("1000.00")
                Transaction.query.delete()
                db.session.commit()
                response = self.client.post("/wallet/transfer-money", data=self.bank_values(rail=rail))
                self.assertEqual(response.status_code, 302)
                transaction = Transaction.query.one()
                self.assertEqual((transaction.kind, transaction.direction, transaction.fee), ("BANK_TRANSFER", "OUT", Decimal(fee)))
                self.assertIn(expected_rail, transaction.title)
                self.assertIn("ending 7890", transaction.counterparty)
                self.assertNotIn("1234567890", transaction.counterparty)
                self.assertEqual(self.user.balance, Decimal("1000.00") - transaction.amount - transaction.fee)

    def test_invalid_bank_inputs_and_insufficient_total_never_mutate_ledger(self):
        for changes in ({"bank": "Unknown Bank"}, {"rail": "ACH"}, {"account_number": "abc123"}, {"account_number": "12345"}, {"holder_name": "X"}, {"amount": "1000"}, {"channel": "CASH"}, {"note": "x" * 101}):
            with self.subTest(changes=changes):
                response = self.client.post("/wallet/transfer-money", data=self.bank_values(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.user.balance, Decimal("1000.00"))
                self.assertEqual(Transaction.query.count(), 0)

    def test_visa_checksum_fee_masking_and_owner_receipt(self):
        response = self.client.post("/wallet/transfer-money", data={"channel": "VISA", "card_number": "4111 1111 1111 1111", "holder_name": "Demo Card Holder", "amount": "67.50"})
        self.assertEqual(response.status_code, 302)
        transaction = Transaction.query.one()
        self.assertEqual((transaction.kind, transaction.fee, self.user.balance), ("VISA_TRANSFER", Decimal("0.68"), Decimal("931.82")))
        self.assertIn("ending 1111", transaction.counterparty)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"4111111111111111", page.data)
        self.assertNotIn("4111111111111111", (transaction.note or "") + transaction.counterparty)
        other = User(full_name="Other Wallet", mobile="01898000002", balance=Decimal("100.00"))
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        self.assertEqual(self.client.get(response.location).status_code, 404)

    def test_invalid_visa_numbers_leave_no_transaction(self):
        for number in ("4111111111111112", "5111111111111111", "411111111111", "not-a-card"):
            with self.subTest(number=number):
                response = self.client.post("/wallet/transfer-money", data={"channel": "VISA", "card_number": number, "holder_name": "Demo Name", "amount": "100"})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Transaction.query.count(), 0)
                self.assertEqual(self.user.balance, Decimal("1000.00"))
                self.assertNotIn(number.encode(), response.data)

    def test_quote_uses_current_session_wallet_and_never_changes_balance(self):
        response = self.client.get("/wallet/quote", query_string={"operation": "transfer-money", "channel": "BANK", "rail": "NPSB", "amount": "1000", "user_id": "999"})
        self.assertEqual(response.get_json()["remaining"], "-10.00")
        self.assertFalse(response.get_json()["can_submit"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(Transaction.query.count(), 0)
        other = User(full_name="Quote Owner", mobile="01898000003", balance=Decimal("50.00"))
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        response = self.client.get("/wallet/quote", query_string={"operation": "transfer-money", "channel": "VISA", "amount": "10"})
        self.assertEqual(response.get_json()["balance"], "50.00")
        self.assertEqual(response.get_json()["remaining"], "39.90")
        self.assertEqual(self.user.balance, Decimal("1000.00"))
        with self.client.session_transaction() as state:
            state.clear()
        self.assertEqual(self.client.get("/wallet/quote?operation=cash-out&amount=500").status_code, 302)

    def test_new_screens_expose_both_channels_and_exact_preview_fields(self):
        for url, expected in (("/wallet/cash-out", b"Agent Cash Out"), ("/wallet/cash-out?channel=ATM", b"ATM Cash Out"), ("/wallet/transfer-money", b"NPSB"), ("/wallet/transfer-money?channel=VISA", b"Visa Card")):
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertIn(expected, page.data)
            self.assertIn(b"data-wallet-remaining", page.data)

    def form_token(self, url):
        html = self.client.get(url).get_data(as_text=True)
        return re.search(r'name="operation_token" value="([a-f0-9]{32})"', html).group(1)

    def test_double_submit_returns_original_receipt_without_second_debit(self):
        token = self.form_token("/wallet/transfer-money")
        values = self.bank_values(operation_token=token)
        first = self.client.post("/wallet/transfer-money", data=values)
        second = self.client.post("/wallet/transfer-money", data=values)
        self.assertEqual((first.status_code, second.status_code), (302, 302))
        self.assertEqual(first.location, second.location)
        self.assertEqual(self.user.balance, Decimal("864.75"))
        self.assertEqual(Transaction.query.count(), 1)
        self.assertEqual(WalletSubmission.query.count(), 1)
        submission = WalletSubmission.query.one()
        self.assertEqual(submission.transaction_id, Transaction.query.one().id)
        changed = self.client.post("/wallet/transfer-money", data=self.bank_values(operation_token=token, amount="200"))
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(self.user.balance, Decimal("864.75"))

    def test_failed_submit_rolls_back_claim_then_can_retry_with_corrected_amount(self):
        token = self.form_token("/wallet/cash-out?channel=ATM")
        values = {"operation_token": token, "channel": "ATM", "atm_location": next(iter(DEMO_ATMS)), "amount": "1000"}
        self.assertEqual(self.client.post("/wallet/cash-out", data=values).status_code, 400)
        self.assertEqual(WalletSubmission.query.count(), 0)
        self.assertEqual(Transaction.query.count(), 0)
        values["amount"] = "500"
        self.assertEqual(self.client.post("/wallet/cash-out", data=values).status_code, 302)
        self.assertEqual(WalletSubmission.query.count(), 1)
        self.assertEqual(self.user.balance, Decimal("495.00"))

    def test_repeated_send_money_does_not_credit_recipient_twice(self):
        recipient = User(full_name="Replay Receiver", mobile="01898000004", balance=Decimal("0.00"))
        db.session.add(recipient)
        db.session.commit()
        token = self.form_token("/wallet/send-money")
        values = {"operation_token": token, "recipient_mobile": recipient.mobile, "amount": "50"}
        first = self.client.post("/wallet/send-money", data=values)
        self.assertEqual(self.client.post("/wallet/send-money", data=values).location, first.location)
        self.assertEqual(recipient.balance, Decimal("50.00"))
        self.assertEqual(self.user.balance, Decimal("950.00"))
        self.assertEqual(Transaction.query.count(), 2)

    def test_submission_tokens_are_scoped_to_the_session_owner(self):
        token = self.form_token("/wallet/add-money")
        values = {"operation_token": token, "source": "Bank Account", "amount": "10", "bank": DEMO_BANKS[0], "account_number": "1234567890", "holder_name": "Demo Account Holder"}
        first = self.client.post("/wallet/add-money", data=values)
        other = User(full_name="Separate Submitter", mobile="01898000005", balance=Decimal("0.00"))
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        second = self.client.post("/wallet/add-money", data=values)
        self.assertNotEqual(first.location, second.location)
        self.assertEqual(self.user.balance, Decimal("1010.00"))
        self.assertEqual(other.balance, Decimal("10.00"))
        self.assertEqual(WalletSubmission.query.count(), 2)

    def test_bangla_option_labels_preserve_submitted_values_and_user_record_text(self):
        self.user.full_name = "Payment"
        db.session.commit()
        with self.client.session_transaction() as state:
            state["language"] = "bn"
        page = self.client.get("/wallet/add-money").get_data(as_text=True)
        self.assertIn('value="Bank Account"', page)
        self.assertIn('value="Debit / Credit Card"', page)
        response = self.client.post("/wallet/transfer-money", data=self.bank_values(note="Send Money"))
        receipt = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('<dd data-user-content>Payment</dd>', receipt)
        self.assertIn('holder: Demo Recipient; Send Money</dd>', receipt)
