import re

from app.services.exceptions import ValidationError


# Prefix routing for the offline recharge demo. There is no live portability lookup.
MOBILE_OPERATOR_PREFIXES = {
    "Grameenphone": ("013", "017"),
    "Robi": ("018",),
    "Airtel": ("016",),
    "Banglalink": ("014", "019"),
    "Teletalk": ("015",),
}


def normalize_mobile(mobile):
    value = re.sub(r"[\s()\-]", "", str(mobile or "").strip())
    if value.startswith("+88"):
        value = value[3:]
    elif value.startswith("88") and len(value) == 13:
        value = value[2:]
    if not re.fullmatch(r"01\d{9}", value, flags=re.ASCII):
        raise ValidationError("Enter a valid 11-digit Bangladeshi mobile number.")
    return value


def validate_recharge_operator(operator, mobile):
    operator = str(operator or "").strip()
    if operator not in MOBILE_OPERATOR_PREFIXES:
        raise ValidationError("Choose a supported mobile operator.")
    number = normalize_mobile(mobile)
    prefix = number[:3]
    expected = next((name for name, prefixes in MOBILE_OPERATOR_PREFIXES.items() if prefix in prefixes), None)
    if expected is None:
        raise ValidationError("Choose a supported recharge number beginning with 013–019.")
    if operator != expected:
        raise ValidationError(f"This demo number begins with {prefix}. Choose {expected} for this recharge.")
    return number


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
