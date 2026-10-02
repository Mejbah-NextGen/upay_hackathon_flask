from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader

from app.container import get_container
from app.domain.models import Transaction, User
from app.domain.payment_plans import PaymentInvoice, PayLaterAccount, PayLaterPurchase, SavingsPlan
from app.extensions import db
from app.services.payment_plans_service import PAY_LATER_MERCHANTS, create_pay_later, save_savings_plan
from app.services.reporting_service import transaction_totals, wallet_change
from app.services.service_catalog import BILL_CATEGORIES
from tests.helpers import AppTestCase


class PaymentPlanTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def later_purchase(self, **changes):
        values = {"merchant": PAY_LATER_MERCHANTS[0], "invoice_no": "SHOP-001", "amount": "400.00", "tenure": "30"}
        values.update(changes)
        return self.client.post("/payments/pay-later", data=values)

    def test_savings_prorates_each_contribution_at_ten_percent_annual_simple_rate(self):
        plan = get_container().payments.savings_plan("100", "12")
        self.assertEqual(Decimal("1200.00"), plan["total"])
        self.assertEqual(Decimal("65.00"), plan["estimated_return"])
        self.assertEqual(Decimal("1265.00"), plan["estimated_maturity"])
        one_month = get_container().payments.savings_plan("10000", "1")
        self.assertEqual(Decimal("83.33"), one_month["estimated_return"])
        response = self.client.post("/payments/savings", data={"amount": "100", "months": "12"})
        self.assertIn("1265.00", response.get_data(as_text=True))
        self.assertIn("not a guaranteed return", response.get_data(as_text=True))
        self.assertEqual(0, Transaction.query.count())

    def test_saved_plan_has_fixed_amount_tenure_and_calendar_maturity(self):
        calculation = get_container().payments.savings_plan("125.50", "3")
        saved = save_savings_plan(get_container().wallet, self.user_id, "School fees", calculation, now=datetime(2026, 1, 31, 6, tzinfo=timezone.utc))
        self.assertEqual("2026-01-31", saved.starts_on.isoformat())
        self.assertEqual("2026-04-30", saved.matures_on.isoformat())
        self.assertEqual(Decimal("125.50"), saved.monthly_amount)
        self.assertEqual(3, saved.months)
        self.assertIn("School fees", self.client.get("/payments/savings").get_data(as_text=True))
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00"), self.user.balance)
        self.assertEqual(0, Transaction.query.count())

    def test_savings_ownership_and_archive(self):
        response = self.client.post("/payments/savings", data={"name": "Emergency savings", "amount": "250", "months": "6", "action": "save"})
        self.assertEqual(302, response.status_code)
        saved = SavingsPlan.query.one()
        other = User(full_name="Other Person", mobile="01711223344", balance=Decimal("1000.00"))
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        self.assertNotIn("Emergency savings", self.client.get("/payments/savings").get_data(as_text=True))
        self.assertEqual(400, self.client.post("/payments/savings", data={"action": "archive", "plan_id": saved.id}).status_code)
        db.session.refresh(saved)
        self.assertEqual("SAVED", saved.status)
        self.login()
        self.assertEqual(302, self.client.post("/payments/savings", data={"action": "archive", "plan_id": saved.id}).status_code)
        db.session.refresh(saved)
        self.assertEqual("ARCHIVED", saved.status)

    def test_savings_rejects_nonfinite_amount_and_unbounded_tenure(self):
        for amount, months in (("NaN", "12"), ("Infinity", "12"), ("-1", "12"), ("1.001", "12"), ("100", "0"), ("100", "121"), ("100", "1.5")):
            with self.subTest(amount=amount, months=months):
                self.assertEqual(400, self.client.post("/payments/savings", data={"action": "save", "amount": amount, "months": months}).status_code)
        self.assertEqual(0, SavingsPlan.query.count())

    def test_all_bill_categories_have_ten_options_and_education_has_separate_types(self):
        for category, details in BILL_CATEGORIES.items():
            self.assertGreaterEqual(len(details["providers"]), 10, category)
            self.assertLessEqual(len(details["providers"]), 20, category)
        for category in ("education-school", "education-college", "education-university"):
            self.assertEqual(200, self.client.get(f"/payments/pay-bill?category={category}").status_code)

    def test_bill_invoice_records_unique_number_reference_and_exact_account(self):
        for invoice_reference in ("BILL-1001", "BILL-1002"):
            response = self.client.post("/payments/pay-bill", data={"category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-4500", "invoice_reference": invoice_reference, "amount": "125"})
            self.assertEqual(302, response.status_code)
        invoices = PaymentInvoice.query.order_by(PaymentInvoice.id).all()
        self.assertEqual(2, len(invoices))
        self.assertNotEqual(invoices[0].invoice_number, invoices[1].invoice_number)
        self.assertEqual("CUSTOMER-4500", invoices[0].account_reference)
        tx = db.session.get(Transaction, invoices[0].transaction_id)
        self.assertEqual(f"INV-{tx.reference}", invoices[0].invoice_number)
        self.assertIn(invoices[0].invoice_number, tx.note)
        receipt = self.client.get(f"/wallet/transaction/{tx.id}").get_data(as_text=True)
        self.assertIn(invoices[0].invoice_number, receipt)
        self.assertIn("BILL-1001", receipt)

    def test_repeated_provider_invoice_is_rejected_without_second_wallet_debit(self):
        values = {"category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-4500", "invoice_reference": "BILL-1001", "amount": "125"}
        self.assertEqual(302, self.client.post("/payments/pay-bill", data=values).status_code)
        values["invoice_reference"] = "bill-1001"
        self.assertEqual(400, self.client.post("/payments/pay-bill", data=values).status_code)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("875.00"), self.user.balance)
        self.assertEqual(1, Transaction.query.count())
        self.assertEqual(1, PaymentInvoice.query.count())

    def test_bill_repeated_form_submission_returns_existing_receipt_without_second_debit(self):
        values = {"category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-4500", "amount": "125", "submission_token": "a" * 32}
        first = self.client.post("/payments/pay-bill", data=values)
        second = self.client.post("/payments/pay-bill", data=values)
        self.assertEqual(302, first.status_code)
        self.assertEqual(first.location, second.location)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("875.00"), self.user.balance)
        self.assertEqual(1, Transaction.query.count())

    def test_failed_bill_creates_neither_invoice_nor_debit(self):
        response = self.client.post("/payments/pay-bill", data={"category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-4500", "invoice_reference": "BILL-1001", "amount": "1001"})
        self.assertEqual(400, response.status_code)
        self.assertEqual(0, PaymentInvoice.query.count())
        self.assertEqual(0, Transaction.query.count())
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00"), self.user.balance)

    def test_pay_later_deferred_purchase_leaves_wallet_and_completed_totals_unchanged(self):
        self.assertEqual(302, self.later_purchase().status_code)
        purchase = PayLaterPurchase.query.one()
        tx = db.session.get(Transaction, purchase.purchase_transaction_id)
        self.assertEqual("DEFERRED", tx.status)
        self.assertEqual(Decimal("0.00"), wallet_change(tx))
        self.assertEqual(Decimal("0.00"), transaction_totals([tx])["outgoing_total"])
        self.assertEqual(Decimal("400.00"), db.session.get(PayLaterAccount, self.user_id).outstanding)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("1000.00"), self.user.balance)

    def test_pay_later_total_limit_and_duplicate_invoice(self):
        self.assertEqual(302, self.later_purchase(amount="3000").status_code)
        self.assertEqual(302, self.later_purchase(invoice_no="SHOP-002", amount="2000").status_code)
        self.assertEqual(400, self.later_purchase(invoice_no="SHOP-003", amount="0.01").status_code)
        self.assertEqual(400, self.later_purchase(invoice_no="shop-001", amount="1").status_code)
        self.assertEqual(2, PayLaterPurchase.query.count())
        self.assertEqual(2, Transaction.query.count())
        self.assertEqual(Decimal("5000.00"), db.session.get(PayLaterAccount, self.user_id).outstanding)

    def test_first_pay_later_purchase_recovers_when_another_request_creates_account(self):
        db.session.add(PayLaterAccount(user_id=self.user_id, outstanding=Decimal("0.00")))
        db.session.commit()
        original_get = db.session.get
        missed_once = False
        def stale_first_read(model, identity, **kwargs):
            nonlocal missed_once
            if model is PayLaterAccount and not missed_once:
                missed_once = True
                return None
            return original_get(model, identity, **kwargs)
        with patch.object(db.session, "get", side_effect=stale_first_read):
            response = self.later_purchase()
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, PayLaterPurchase.query.count())
        self.assertEqual(Decimal("400.00"), db.session.get(PayLaterAccount, self.user_id).outstanding)

    def test_pay_later_uses_bangladesh_due_date(self):
        purchase = create_pay_later(get_container().wallet, self.user_id, PAY_LATER_MERCHANTS[0], "SHOP-DATE", "100", "7", now=datetime(2026, 10, 1, 20, tzinfo=timezone.utc))
        self.assertEqual("2026-10-09", purchase.due_on.isoformat())

    def test_pay_later_repayment_debits_exactly_once_and_releases_limit(self):
        self.later_purchase()
        purchase = PayLaterPurchase.query.one()
        first = self.client.post("/payments/pay-later", data={"action": "repay", "purchase_id": purchase.id})
        self.assertEqual(302, first.status_code)
        db.session.refresh(self.user)
        db.session.refresh(purchase)
        self.assertEqual(Decimal("600.00"), self.user.balance)
        self.assertEqual("REPAID", purchase.status)
        self.assertEqual(Decimal("0.00"), db.session.get(PayLaterAccount, self.user_id).outstanding)
        second = self.client.post("/payments/pay-later", data={"action": "repay", "purchase_id": purchase.id})
        self.assertEqual(first.location, second.location)
        db.session.refresh(self.user)
        self.assertEqual(Decimal("600.00"), self.user.balance)
        self.assertEqual(2, Transaction.query.count())

    def test_pay_later_insufficient_repayment_rolls_back_claim_and_debit(self):
        self.later_purchase(amount="1200")
        purchase = PayLaterPurchase.query.one()
        self.assertEqual(400, self.client.post("/payments/pay-later", data={"action": "repay", "purchase_id": purchase.id}).status_code)
        db.session.refresh(purchase)
        db.session.refresh(self.user)
        self.assertEqual("PENDING", purchase.status)
        self.assertIsNone(purchase.repayment_transaction_id)
        self.assertEqual(Decimal("1000.00"), self.user.balance)
        self.assertEqual(Decimal("1200.00"), db.session.get(PayLaterAccount, self.user_id).outstanding)
        self.assertEqual(1, Transaction.query.count())

    def test_pay_later_owner_scoping(self):
        self.later_purchase()
        purchase = PayLaterPurchase.query.one()
        other = User(full_name="Other Person", mobile="01711223344", balance=Decimal("1000.00"))
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        self.assertNotIn("SHOP-001", self.client.get("/payments/pay-later").get_data(as_text=True))
        self.assertEqual(400, self.client.post("/payments/pay-later", data={"action": "repay", "purchase_id": purchase.id}).status_code)
        db.session.refresh(purchase)
        self.assertEqual("PENDING", purchase.status)

    def test_pay_later_validates_merchant_invoice_and_tenure(self):
        for changes in ({"merchant": "Unlisted"}, {"invoice_no": "<script>"}, {"amount": "NaN"}, {"tenure": "31"}, {"amount": "-1"}):
            with self.subTest(changes=changes):
                self.assertEqual(400, self.later_purchase(**changes).status_code)
        self.assertEqual(0, PayLaterPurchase.query.count())
        self.assertEqual(0, Transaction.query.count())

    def test_request_money_share_message_uses_selected_bangla_language(self):
        with self.client.session_transaction() as session:
            session["language"] = "bn"
        response = self.client.post("/payments/request-money", data={"recipient_mobile": "01712345678", "amount": "125.50", "note": "Lunch"}, follow_redirects=True)
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn("টাকা চেয়েছেন", html)
        self.assertIn("নোট: Lunch", html)
        self.assertNotIn("requests BDT", html)

    def test_real_bill_pdf_contains_structured_owner_scoped_invoice_fields(self):
        from app.services.export_service import receipt_fields

        response = self.client.post("/payments/pay-bill", data={
            "category": "gas", "provider": "Titas Gas", "account_no": "CUSTOMER-4500",
            "invoice_reference": "BILL-1001", "amount": "125.00",
        })
        self.assertEqual(302, response.status_code)
        invoice = PaymentInvoice.query.one()
        tx = db.session.get(Transaction, invoice.transaction_id)
        response = self.client.get(f"/wallet/transaction/{tx.id}/download?format=pdf")
        self.assertEqual(200, response.status_code)
        text = " ".join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
        for expected in ("Invoice number", invoice.invoice_number, "Bill account", "CUSTOMER-4500", "Bill invoice reference", "BILL-1001", "Category", "Gas", self.user.full_name, self.user.mobile, tx.reference):
            self.assertIn(expected, text)

        other = User(full_name="Other Invoice Owner", mobile="01711223344", balance=Decimal("1000.00"))
        db.session.add(other)
        db.session.commit()
        self.assertNotIn("Invoice number", dict(receipt_fields(other, tx)))
        self.login(other.id)
        self.assertEqual(404, self.client.get(f"/wallet/transaction/{tx.id}/download?format=pdf").status_code)
