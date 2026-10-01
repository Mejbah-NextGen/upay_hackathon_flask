from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from app.domain.models import Transaction
from app.extensions import db
from app.repositories.interfaces import TransactionRepository, UserRepository
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.validation import normalize_mobile


class WalletService:
    def __init__(self, users: UserRepository, transactions: TransactionRepository):
        self.users = users
        self.transactions = transactions

    @staticmethod
    def parse_amount(raw_amount: str | float | Decimal) -> Decimal:
        try:
            amount = Decimal(str(raw_amount).strip())
            if not amount.is_finite():
                raise InvalidOperation
            if amount <= 0:
                raise ValidationError("Amount must be greater than zero.")
            if amount > Decimal("100000.00"):
                raise ValidationError("Demo transaction limit is ৳100,000.")
            rounded = amount.quantize(Decimal("0.01"))
            if rounded != amount:
                raise ValidationError("Amount can have at most two decimal places.")
        except (InvalidOperation, ValueError):
            raise ValidationError("Enter a valid amount.")
        return rounded

    @staticmethod
    def _reference() -> str:
        return f"UPX-{uuid4().hex[:10].upper()}"

    def get_user(self, user_id: int):
        user = self.users.get_by_id(user_id)
        if not user:
            raise ValidationError("User account not found.")
        return user

    def send_money(self, user_id: int, recipient_mobile: str, amount_raw, note: str = ""):
        sender = self.get_user(user_id)
        recipient_mobile = normalize_mobile(recipient_mobile)
        amount = self.parse_amount(amount_raw)
        if recipient_mobile == sender.mobile:
            raise ValidationError("You cannot send money to your own number.")
        if Decimal(sender.balance) < amount:
            raise InsufficientBalanceError("Insufficient balance.")

        recipient = self.users.get_by_mobile(recipient_mobile)
        if recipient is None:
            raise ValidationError("No wallet account found for this number. Create a demo account first.")
        note = (note or "").strip()
        if len(note) > 255:
            raise ValidationError("Note must be 255 characters or fewer.")
        sender.balance = Decimal(sender.balance) - amount
        ref = self._reference()
        outgoing = Transaction(
            user_id=sender.id,
            kind="SEND_MONEY",
            direction="OUT",
            title="Send Money",
            counterparty=recipient.full_name,
            reference=ref,
            amount=amount,
            note=note or None,
        )
        db.session.add(outgoing)

        recipient.balance = Decimal(recipient.balance) + amount
        incoming = Transaction(
            user_id=recipient.id,
            kind="RECEIVE_MONEY",
            direction="IN",
            title="Received Money",
            counterparty=sender.full_name,
            reference=ref,
            amount=amount,
            note=note or None,
        )
        db.session.add(incoming)

        db.session.commit()
        return outgoing

    def add_money(self, user_id: int, source: str, amount_raw):
        user = self.get_user(user_id)
        amount = self.parse_amount(amount_raw)
        source = (source or "").strip()
        if source not in {"Bank Account", "Debit / Credit Card", "Agent"}:
            raise ValidationError("Choose a valid add-money source.")
        user.balance = Decimal(user.balance) + amount
        tx = Transaction(
            user_id=user.id,
            kind="ADD_MONEY",
            direction="IN",
            title="Add Money",
            counterparty=source,
            reference=self._reference(),
            amount=amount,
        )
        db.session.add(tx)
        db.session.commit()
        return tx

    def cash_out(self, user_id: int, agent_number: str, amount_raw):
        user = self.get_user(user_id)
        agent_number = normalize_mobile(agent_number)
        amount = self.parse_amount(amount_raw)
        fee = (amount * Decimal("0.015")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = amount + fee
        if Decimal(user.balance) < total:
            raise InsufficientBalanceError("Insufficient balance including cash-out fee.")
        user.balance = Decimal(user.balance) - total
        tx = Transaction(
            user_id=user.id,
            kind="CASH_OUT",
            direction="OUT",
            title="Cash Out",
            counterparty=agent_number,
            reference=self._reference(),
            amount=amount,
            fee=fee,
        )
        db.session.add(tx)
        db.session.commit()
        return tx

    def debit_for_payment(self, user_id: int, *, kind: str, title: str, counterparty: str, amount_raw):
        user = self.get_user(user_id)
        amount = self.parse_amount(amount_raw)
        if Decimal(user.balance) < amount:
            raise InsufficientBalanceError("Insufficient balance.")
        user.balance = Decimal(user.balance) - amount
        tx = Transaction(
            user_id=user.id,
            kind=kind,
            direction="OUT",
            title=title,
            counterparty=counterparty,
            reference=self._reference(),
            amount=amount,
        )
        db.session.add(tx)
        db.session.commit()
        return tx

    def dashboard_stats(self, user_id: int, days: int = 1):
        from app.services.reporting_service import dashboard_report

        user = self.get_user(user_id)
        return dashboard_report(user.balance, self.transactions.all_for_user(user_id), days=days)
