"""Signed, expiring demo instructions. Reading a QR never executes a payment."""
from decimal import Decimal, InvalidOperation
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.services.exceptions import ValidationError

KINDS = {"SEND_MONEY", "CASH_OUT", "BILL_PAYMENT", "MOBILE_RECHARGE", "TRANSFER_MONEY", "REQUEST_MONEY"}


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="upayx-operation-qr-v1")


def operation_qr(user_id, fields):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderSVG
    kind = fields.get("kind", "")
    if kind not in KINDS:
        raise ValidationError("Choose a supported QR operation.")
    payload = {"user_id": user_id, "kind": kind}
    for name in ("reference", "provider", "channel", "category", "amount"):
        value = fields.get(name, "")
        if not isinstance(value, str) or len(value) > 120:
            raise ValidationError("QR details are too long.")
        payload[name] = value.strip()
    if payload["amount"]:
        try:
            amount = Decimal(payload["amount"])
        except InvalidOperation:
            raise ValidationError("Enter a valid QR amount.")
        if not amount.is_finite() or amount <= 0 or amount > 100000 or amount.as_tuple().exponent < -2:
            raise ValidationError("QR amount must be between 0.01 and 100,000, with up to two decimal places.")
    if kind == "REQUEST_MONEY":
        from app.domain.models import User
        user = User.query.filter_by(id=user_id).first()
        if user is None:
            raise ValidationError("User not found.")
        # A shared request can only request funds for its authenticated creator.
        payload.update(reference=user.mobile, provider="", channel="", category="")
    qr = QrCodeWidget("UPAYX:" + _serializer().dumps(payload), barLevel="M")
    bounds = qr.getBounds()
    size = bounds[2] - bounds[0]
    drawing = Drawing(size, size)
    drawing.add(qr)
    return renderSVG.drawToString(drawing)


def read_operation_qr(user_id, code):
    if not isinstance(code, str) or not code.startswith("UPAYX:") or len(code) > 2000:
        raise ValidationError("Use a signed UpayX demo QR code.")
    try:
        payload = _serializer().loads(code[6:], max_age=900)
    except (BadSignature, SignatureExpired):
        raise ValidationError("This QR code is invalid or expired. Generate a new code.")
    if not isinstance(payload, dict) or payload.get("kind") not in KINDS:
        raise ValidationError("This QR code belongs to another account or operation.")
    if payload["kind"] == "REQUEST_MONEY":
        from app.domain.models import User
        requester = User.query.filter_by(id=payload.get("user_id"), mobile=payload.get("reference")).first()
        if requester is None:
            raise ValidationError("This request account no longer exists.")
        payload.update(kind="SEND_MONEY", provider="", channel="", category="")
    elif payload.get("user_id") != user_id:
        raise ValidationError("This QR code belongs to another account or operation.")
    return {key: payload.get(key, "") for key in ("kind", "reference", "provider", "channel", "category", "amount")}


def read_qr_upload(user_id, upload):
    from io import BytesIO
    import warnings
    from PIL import Image, UnidentifiedImageError
    try:
        import zxingcpp
    except ImportError:
        raise ValidationError("QR image reading needs the zxing-cpp package from requirements.txt.")
    if not upload:
        raise ValidationError("Choose a QR image.")
    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValidationError("Choose an image under 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as picture:
                if picture.width * picture.height > 16_000_000:
                    raise ValidationError("Choose an image smaller than 16 megapixels.")
                picture.load()
                picture = picture.convert("L")
                picture.thumbnail((2400, 2400))
                result = zxingcpp.read_barcode(picture, formats=zxingcpp.BarcodeFormat.QRCode)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Choose a valid QR image.")
    if not result:
        raise ValidationError("No QR code found in this image.")
    return read_operation_qr(user_id, result.text)
