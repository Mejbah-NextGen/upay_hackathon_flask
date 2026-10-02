"""Local demo registry. It identifies demo recipients; it is not a live fraud feed."""

import re

from app.domain.models import User
from app.domain.operations import RecipientRegistration
from app.services.exceptions import ValidationError
from app.services.service_catalog import BILL_CATEGORIES
from app.services.validation import normalize_mobile, validate_recharge_operator


SUPPORTED_KINDS = frozenset({"SEND_MONEY", "MOBILE_RECHARGE", "CASH_OUT", "BILL_PAYMENT", "REQUEST_MONEY"})


def normalize_reference(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /._-]{1,59}", value):
        raise ValidationError("Enter a valid account or payment reference (2–60 letters, numbers, spaces or / . _ -).")
    return value


def _registry_number(number):
    # Bill references are case insensitive in this demo registry.
    return number.upper()


def assert_not_blocked(number):
    registration = RecipientRegistration.query.filter_by(number=_registry_number(number), status="BLOCKED").first()
    if registration:
        raise ValidationError("Blocked number. This recipient is flagged in the demo safety registry; payment is unavailable.")


def lookup_recipient(kind, number, *, provider="", category=""):
    kind = str(kind or "").upper()
    provider = str(provider or "").strip()
    if kind not in SUPPORTED_KINDS:
        raise ValidationError("Choose a supported transaction type.")
    authorization_name = None
    if kind == "BILL_PAYMENT":
        details = BILL_CATEGORIES.get(category)
        if not details or provider not in details["providers"]:
            raise ValidationError("Choose a listed provider for the selected bill category.")
        number = normalize_reference(number)
        authorization_name = provider
    else:
        number = normalize_mobile(number)
        authorization_name = provider or None

    base = {"number": number, "name": None, "authorization_name": authorization_name}
    blocked = RecipientRegistration.query.filter_by(number=_registry_number(number), status="BLOCKED").first()
    if blocked:
        return {**base, "status": "blocked", "message": "Blocked number — flagged in the demo safety registry.", "can_transact": False}

    if kind == "MOBILE_RECHARGE":
        validate_recharge_operator(provider, number)

    # Wallet identity is required for send money; a directory record alone cannot receive funds.
    wallet = User.query.filter_by(mobile=number).first() if kind != "BILL_PAYMENT" else None
    if wallet and kind != "CASH_OUT":
        return {**base, "name": wallet.full_name, "status": "registered", "message": f"Registered recipient: {wallet.full_name}", "can_transact": True}
    registrations = RecipientRegistration.query.filter_by(number=_registry_number(number), status="REGISTERED").all()
    registration = next((row for row in registrations if row.kind in {kind, "ANY"} and row.provider in {provider, ""}), None)
    if registration and kind not in {"SEND_MONEY", "REQUEST_MONEY"}:
        return {**base, "name": registration.name, "status": "registered", "message": f"Registered recipient: {registration.name}", "can_transact": True}
    if kind == "SEND_MONEY":
        suffix = " Create a wallet before sending money."
    elif kind == "REQUEST_MONEY":
        suffix = " You can still prepare a demo money request."
    else:
        suffix = " Demo-only payment is available; verify the number before continuing."
    return {**base, "status": "not_registered", "message": "Not registered." + suffix, "can_transact": kind != "SEND_MONEY"}
