"""Authenticated application-field encryption with explicit key rotation."""

from flask import current_app


PREFIX = "enc:v1:"


def _cipher():
    keys = current_app.config.get("DATA_ENCRYPTION_KEYS") or current_app.config.get("DATA_ENCRYPTION_KEY", "")
    if isinstance(keys, str):
        keys = [value.strip() for value in keys.split(",") if value.strip()]
    if not keys:
        if current_app.config.get("REQUIRE_DATA_ENCRYPTION", False):
            raise ValueError("A data encryption key is required.")
        return None
    from cryptography.fernet import Fernet, MultiFernet
    return MultiFernet([Fernet(key.encode() if isinstance(key, str) else key) for key in keys])


def encrypt_text(value):
    value = str(value)
    cipher = _cipher()
    return PREFIX + cipher.encrypt(value.encode("utf-8")).decode("ascii") if cipher else value


def decrypt_text(value):
    value = str(value)
    cipher = _cipher()
    if value.startswith(PREFIX):
        if cipher is None:
            raise ValueError("The stored data requires its encryption key.")
        return cipher.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    if current_app.config.get("REQUIRE_DATA_ENCRYPTION", False):
        raise ValueError("Unencrypted legacy data must be migrated before use.")
    return value


def rotate_text(value):
    """Re-encrypt under the first active key; old keys remain read-only."""
    return encrypt_text(decrypt_text(value))
