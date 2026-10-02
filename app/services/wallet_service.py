from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from uuid import uuid4

from sqlalchemy import update

from app.domain.models import Transaction, User
from app.extensions import db
from app.repositories.interfaces import TransactionRepository, UserRepository
from app.services.exceptions import InsufficientBalanceError, ValidationError
from app.services.validation import normalize_mobile
from app.services.recipient_service import assert_not_blocked
from app.services.wallet_catalog import (
    ATM_INCREMENT, ATM_LIMIT, BANK_TRANSFER_FEES, CASH_OUT_RATES,
    DEMO_ATMS, DEMO_BANKS, VISA_TRANSFER_RATE,
)


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

    @staticmethod
    def _debit(user_id, amount, message="Insufficient balance."):
        changed = db.session.execute(
            update(User).where(User.id == user_id, User.balance >= amount).values(balance=User.balance - amount),
            execution_options={"synchronize_session": "fetch"},
        )
        if changed.rowcount != 1:
            raise InsufficientBalanceError(message)

    @staticmethod
    def _credit(user_id, amount):
        db.session.execute(
            update(User).where(User.id == user_id).values(balance=User.balance + amount),
            execution_options={"synchronize_session": "fetch"},
        )

    @staticmethod
    def _finish(commit):
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def send_money(self, user_id: int, recipient_mobile: str, amount_raw, note: str = "", *, commit=True):
        sender = self.get_user(user_id)
        recipient_mobile = normalize_mobile(recipient_mobile)
        assert_not_blocked(recipient_mobile)
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
        self._debit(sender.id, amount)
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

        self._credit(recipient.id, amount)
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

        self._finish(commit)
        return outgoing

    def add_money(self, user_id: int, source: str, amount_raw, *, commit=True):
        user = self.get_user(user_id)
        amount = self.parse_amount(amount_raw)
        source = (source or "").strip()
        if source not in {"Bank Account", "Debit / Credit Card", "Agent"}:
            raise ValidationError("Choose a valid add-money source.")
        self._credit(user.id, amount)
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
        self._finish(commit)
        return tx

    @staticmethod
    def _cash_out_channel(channel):
        channel = str(channel or "AGENT").strip().upper()
        if channel not in CASH_OUT_RATES:
            raise ValidationError("Choose Agent or ATM cash-out.")
        return channel

    @staticmethod
    def _transfer_rail(rail):
        rail = str(rail or "").strip().upper()
        # BFTN is the alternate spelling used on some demo screens.
        if rail == "BFTN":
            rail = "BEFTN"
        if rail not in BANK_TRANSFER_FEES:
            raise ValidationError("Choose NPSB or BEFTN (BFTN).")
        return rail

    def quote(self, user_id, operation, amount_raw, *, channel="AGENT", rail="NPSB"):
        user = self.get_user(user_id)
        amount = self.parse_amount(amount_raw)
        if operation == "cash-out":
            channel = self._cash_out_channel(channel)
            if channel == "ATM" and (amount > ATM_LIMIT or amount % ATM_INCREMENT):
                raise ValidationError("Demo ATM withdrawals must be multiples of ৳500, up to ৳20,000.")
            fee = (amount * CASH_OUT_RATES[channel]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif operation == "transfer-money":
            channel = str(channel or "BANK").strip().upper()
            if channel == "BANK":
                fee = BANK_TRANSFER_FEES[self._transfer_rail(rail)]
            elif channel == "VISA":
                fee = (amount * VISA_TRANSFER_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                raise ValidationError("Choose Bank Account or Visa Card.")
        else:
            raise ValidationError("Choose a supported wallet operation.")
        total = amount + fee
        balance = Decimal(user.balance)
        return {"amount": amount, "fee": fee, "total": total, "balance": balance,
                "remaining": balance - total, "can_submit": balance >= total}

    def cash_out(self, user_id: int, agent_number: str, amount_raw, *, channel="AGENT", atm_location="", commit=True):
        user = self.get_user(user_id)
        channel = self._cash_out_channel(channel)
        if channel == "AGENT":
            counterparty = normalize_mobile(agent_number)
            assert_not_blocked(counterparty)
            note = "Demo Agent cash-out. No physical cash is dispensed."
        else:
            if atm_location not in DEMO_ATMS:
                raise ValidationError("Choose a listed demo ATM location.")
            counterparty = DEMO_ATMS[atm_location]
            note = f"Demo ATM cash-out: {atm_location}. No physical cash is dispensed."
        quote = self.quote(user_id, "cash-out", amount_raw, channel=channel)
        if not quote["can_submit"]:
            raise InsufficientBalanceError("Insufficient balance including cash-out fee.")
        self._debit(user.id, quote["total"], "Insufficient balance including cash-out fee.")
        tx = Transaction(
            user_id=user.id,
            kind="CASH_OUT",
            direction="OUT",
            title=f"Cash Out ({channel.title() if channel == 'AGENT' else 'ATM'})",
            counterparty=counterparty,
            reference=self._reference(),
            amount=quote["amount"],
            fee=quote["fee"],
            note=note,
        )
        db.session.add(tx)
        self._finish(commit)
        return tx

    @staticmethod
    def _visa_number(value):
        number = re.sub(r"[ -]", "", str(value or ""))
        if not re.fullmatch(r"4[0-9]{15}", number):
            raise ValidationError("Enter a 16-digit demo Visa card number beginning with 4.")
        checksum = 0
        for index, digit in enumerate(number):
            value = int(digit)
            if index % 2 == 0:
                value *= 2
                if value > 9:
                    value -= 9
            checksum += value
        if checksum % 10:
            raise ValidationError("The demo Visa card number did not pass its checksum.")
        return number

    def transfer_money(self, user_id, channel, amount_raw, *, bank="", account_number="", card_number="", holder_name="", rail="NPSB", note="", commit=True):
        user = self.get_user(user_id)
        channel = str(channel or "").strip().upper()
        holder_name = str(holder_name or "").strip()
        if not 2 <= len(holder_name) <= 120 or any(ord(character) < 32 for character in holder_name):
            raise ValidationError("Enter the destination account or card holder name (2–120 characters).")
        note = str(note or "").strip()
        if len(note) > 100:
            raise ValidationError("Transfer note must be 100 characters or fewer.")
        if channel == "BANK":
            if bank not in DEMO_BANKS:
                raise ValidationError("Choose a listed demo bank.")
            account_number = str(account_number or "").strip()
            if not re.fullmatch(r"[0-9]{6,20}", account_number):
                raise ValidationError("Enter a demo bank account number with 6–20 digits.")
            assert_not_blocked(account_number)
            rail = self._transfer_rail(rail)
            destination = f"{bank} • account ending {account_number[-4:]}"
            title, kind = f"Bank Transfer ({rail})", "BANK_TRANSFER"
        elif channel == "VISA":
            number = self._visa_number(card_number)
            destination = f"Demo Visa • card ending {number[-4:]}"
            rail = "VISA"
            title, kind = "Visa Card Transfer", "VISA_TRANSFER"
        else:
            raise ValidationError("Choose Bank Account or Visa Card.")
        quote = self.quote(user_id, "transfer-money", amount_raw, channel=channel, rail=rail)
        if not quote["can_submit"]:
            raise InsufficientBalanceError("Insufficient balance including transfer fee.")
        self._debit(user.id, quote["total"], "Insufficient balance including transfer fee.")
        transaction = Transaction(
            user_id=user.id, kind=kind, direction="OUT", title=title,
            counterparty=destination, reference=self._reference(), amount=quote["amount"],
            fee=quote["fee"], note=f"Demo {rail}; holder: {holder_name}; {note}".rstrip("; "),
        )
        db.session.add(transaction)
        self._finish(commit)
        return transaction

    def debit_for_payment(self, user_id: int, *, kind: str, title: str, counterparty: str, amount_raw, note=None, commit=True):
        user = self.get_user(user_id)
        amount = self.parse_amount(amount_raw)
        if note and len(str(note)) > 255:
            raise ValidationError("Payment note must be 255 characters or fewer.")
        if Decimal(user.balance) < amount:
            raise InsufficientBalanceError("Insufficient balance.")
        self._debit(user.id, amount)
        tx = Transaction(
            user_id=user.id,
            kind=kind,
            direction="OUT",
            title=title,
            counterparty=counterparty,
            reference=self._reference(),
            amount=amount,
            note=note,
        )
        db.session.add(tx)
        self._finish(commit)
        return tx

    def dashboard_stats(self, user_id: int, days: int = 1):
        from app.services.reporting_service import dashboard_report

        user = self.get_user(user_id)
        return dashboard_report(user.balance, self.transactions.all_for_user(user_id), days=days)
