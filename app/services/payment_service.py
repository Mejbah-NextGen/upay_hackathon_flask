import re

from app.services.auth_service import AuthService
from app.services.exceptions import ValidationError
from app.services.service_catalog import BILL_CATEGORIES, MOBILE_OPERATORS
from app.services.wallet_service import WalletService


class PaymentService:
    def __init__(self, wallet: WalletService):
        self.wallet = wallet

    def mobile_recharge(self, user_id: int, operator: str, mobile: str, amount):
        operator = (operator or "").strip()
        if operator not in MOBILE_OPERATORS:
            raise ValidationError("Choose a supported mobile operator.")
        mobile = AuthService.normalize_mobile(mobile)
        return self.wallet.debit_for_payment(
            user_id,
            kind="MOBILE_RECHARGE",
            title="Mobile Recharge",
            counterparty=f"{operator} • {mobile}",
            amount_raw=amount,
        )

    def pay_bill(self, user_id: int, provider: str, account_no: str, amount, category: str = ""):
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
        return self.wallet.debit_for_payment(
            user_id,
            kind="BILL_PAYMENT",
            title=f"{details['label']} Payment",
            counterparty=f"{provider} • {account_no}",
            amount_raw=amount,
        )

    def savings_plan(self, monthly_amount, months):
        amount = self.wallet.parse_amount(monthly_amount)
        if not re.fullmatch(r"[0-9]{1,3}", str(months or "")) or not 1 <= int(months) <= 120:
            raise ValidationError("Choose a savings duration from 1 to 120 months.")
        return {"monthly_amount": amount, "months": int(months), "total": amount * int(months)}

    def money_request(self, user_id, recipient_mobile, amount, note=""):
        user = self.wallet.get_user(user_id)
        recipient_mobile = AuthService.normalize_mobile(recipient_mobile)
        if recipient_mobile == user.mobile:
            raise ValidationError("Choose another mobile number to request money from.")
        amount = self.wallet.parse_amount(amount)
        note = (note or "").strip()
        if len(note) > 160:
            raise ValidationError("Keep the request note within 160 characters.")
        message = f"{user.full_name} requests BDT {amount:.2f}. Send demo money to wallet {user.mobile}."
        if note:
            message += f" Note: {note}"
        return {"recipient_mobile": recipient_mobile, "amount": f"{amount:.2f}", "note": note, "message": message}
