import re
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from app.domain.models import Transaction
from app.domain.payment_plans import PaymentInvoice, PaymentSubmission
from app.extensions import db
from app.services.auth_service import AuthService
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS
from app.services.wallet_service import WalletService
from app.services.recipient_service import assert_not_blocked
from app.services.payment_plans_service import SAVINGS_ANNUAL_RATE
from app.services.validation import validate_recharge_operator


class PaymentService:
    def __init__(self, wallet: WalletService):
        self.wallet = wallet

    @staticmethod
    def _submitted_transaction(user_id, token):
        if not token:
            return None
        existing = PaymentSubmission.query.filter_by(user_id=user_id, token=token).first()
        return db.session.get(Transaction, existing.transaction_id) if existing else None

    def mobile_recharge(self, user_id: int, operator: str, mobile: str, amount, *, commit=True):
        operator = (operator or "").strip()
        if operator not in MOBILE_OPERATORS:
            raise ValidationError("Choose a supported mobile operator.")
        mobile = AuthService.normalize_mobile(mobile)
        assert_not_blocked(mobile)
        mobile = validate_recharge_operator(operator, mobile)
        return self.wallet.debit_for_payment(
            user_id,
            kind="MOBILE_RECHARGE",
            title="Mobile Recharge",
            counterparty=f"{operator} • {mobile}",
            amount_raw=amount,
            commit=commit,
        )

    def pay_bill(self, user_id: int, provider: str, account_no: str, amount, category: str = "", *, invoice_reference="", submission_token="", commit=True):
        submission_token = str(submission_token or "").strip()
        if submission_token and not re.fullmatch(r"[0-9a-f]{32}", submission_token):
            raise ValidationError("This payment form has expired. Open the payment page again.")
        existing = self._submitted_transaction(user_id, submission_token)
        if existing is not None:
            return existing
        category = (category or "").strip()
        if category not in BILL_CATEGORIES:
            raise ValidationError("Choose a valid bill category.")
        details = BILL_CATEGORIES[category]
        provider = (provider or "").strip()
        if provider not in details["providers"]:
            raise ValidationError(f"Choose a listed provider for {details['label']}.")
        account_no = (account_no or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /._-]{1,59}", account_no):
            raise ValidationError("Enter a valid account or payment reference (2–60 letters, numbers, spaces or / . _ -).")
        assert_not_blocked(account_no)
        invoice_reference = str(invoice_reference or "").strip().upper()
        if invoice_reference and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /._-]{1,59}", invoice_reference):
            raise ValidationError("Enter a valid invoice reference (2–60 letters, numbers, spaces or / . _ -).")
        if invoice_reference and PaymentInvoice.query.filter_by(user_id=user_id, category=category, provider=provider, invoice_reference=invoice_reference).first():
            raise ValidationError("This provider invoice is already paid. Open its receipt in Report.")
        try:
            transaction = self.wallet.debit_for_payment(
                user_id, kind="BILL_PAYMENT", title=f"{details['label']} Payment",
                counterparty=f"{provider} • {account_no}"[:120], amount_raw=amount,
                note=f"Bill account: {account_no}; invoice reference: {invoice_reference or 'not supplied'}; category: {details['label']}.",
                commit=False,
            )
            invoice_number = f"INV-{transaction.reference}"
            db.session.add(PaymentInvoice(
                user_id=user_id, transaction_id=transaction.id, invoice_number=invoice_number,
                category=category, provider=provider, account_reference=account_no,
                invoice_reference=invoice_reference or None,
            ))
            if submission_token:
                db.session.add(PaymentSubmission(user_id=user_id, token=submission_token, transaction_id=transaction.id))
            transaction.note = f"Invoice {invoice_number}; " + transaction.note
            self.wallet._finish(commit)
            return transaction
        except InsufficientBalanceError:
            if not commit:
                raise
            db.session.rollback()
            # Both requests can miss the token before the first commits. Its
            # debit may consume the entire balance before the second reaches
            # the unique token insert. Re-read after rollback so that duplicate
            # returns the committed receipt instead of an insufficient error.
            existing = self._submitted_transaction(user_id, submission_token)
            if existing is not None:
                return existing
            if invoice_reference and PaymentInvoice.query.filter_by(user_id=user_id, category=category, provider=provider, invoice_reference=invoice_reference).first():
                raise ValidationError("This provider invoice is already paid. Open its receipt in Report.")
            raise
        except IntegrityError as exc:
            if not commit:
                raise ValidationError("This provider invoice is already paid. Open its receipt in Report.") from exc
            db.session.rollback()
            existing = self._submitted_transaction(user_id, submission_token)
            if existing is not None:
                return existing
            raise ValidationError("This provider invoice is already paid. Open its receipt in Report.")
        except Exception:
            if commit:
                db.session.rollback()
            raise

    def savings_plan(self, monthly_amount, months):
        amount = self.wallet.parse_amount(monthly_amount)
        if not re.fullmatch(r"[0-9]{1,3}", str(months or "")) or not 1 <= int(months) <= 120:
            raise ValidationError("Choose a savings duration from 1 to 120 months.")
        duration = int(months)
        principal = amount * duration
        # Monthly payments start at the beginning of each month: the first earns
        # for `duration` months and the last for one month. No compounding.
        estimated_return = (amount * SAVINGS_ANNUAL_RATE * Decimal(duration * (duration + 1)) / Decimal(24)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "monthly_amount": amount, "months": duration, "total": principal,
            "annual_rate": SAVINGS_ANNUAL_RATE, "estimated_return": estimated_return,
            "estimated_maturity": principal + estimated_return,
        }

    def money_request(self, user_id, recipient_mobile, amount, note="", *, language="en"):
        user = self.wallet.get_user(user_id)
        recipient_mobile = AuthService.normalize_mobile(recipient_mobile)
        assert_not_blocked(recipient_mobile)
        if recipient_mobile == user.mobile:
            raise ValidationError("Choose another mobile number to request money from.")
        amount = self.wallet.parse_amount(amount)
        note = (note or "").strip()
        if len(note) > 160:
            raise ValidationError("Keep the request note within 160 characters.")
        if language == "bn":
            message = f"{user.full_name} {amount:.2f} টাকা চেয়েছেন। ডেমো ওয়ালেট {user.mobile} নম্বরে টাকা পাঠান।"
        else:
            message = f"{user.full_name} requests BDT {amount:.2f}. Send demo money to wallet {user.mobile}."
        if note:
            message += f" {'নোট' if language == 'bn' else 'Note'}: {note}"
        return {"recipient_mobile": recipient_mobile, "amount": f"{amount:.2f}", "note": note, "message": message}
