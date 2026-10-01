import re

from app.services.exceptions import ValidationError


def normalize_mobile(mobile):
    value = re.sub(r"[\s()\-]", "", str(mobile or "").strip())
    if value.startswith("+88"):
        value = value[3:]
    elif value.startswith("88") and len(value) == 13:
        value = value[2:]
    if not re.fullmatch(r"01\d{9}", value, flags=re.ASCII):
        raise ValidationError("Enter a valid 11-digit Bangladeshi mobile number.")
    return value


def validate_full_name(full_name):
    value = str(full_name or "").strip()
    if not 3 <= len(value) <= 120:
        raise ValidationError("Full name must contain 3 to 120 characters.")
    return value


def normalize_email(email):
    value = str(email or "").strip()
    if value and (len(value) > 120 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)):
        raise ValidationError("Enter a valid email address.")
    return value or None
