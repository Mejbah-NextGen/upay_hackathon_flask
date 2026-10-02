from io import BytesIO
import math
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener
    register_heif_opener(thumbnails=False)
except ImportError:
    pass  # Other formats remain usable before requirements are upgraded.

from app.domain.profiles import UserProfile
from app.extensions import db
from app.repositories.interfaces import UserRepository
from app.services.exceptions import ValidationError
from app.services.validation import normalize_email, validate_full_name


class ProfileService:
    def __init__(self, users: UserRepository):
        self.users = users

    def get_details(self, user_id: int):
        return db.session.get(UserProfile, user_id) or UserProfile(
            user_id=user_id, nickname="", address=""
        )

    @staticmethod
    def _prepare_photo(upload, size=512, fit="fit", crop_x=50, crop_y=50):
        raw = upload.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise ValidationError("Choose a profile picture under 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(raw)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "ICO", "AVIF", "HEIF", "JPEG2000", "PPM", "TGA", "QOI", "PSD"}:
                        raise ValidationError("Choose a supported raster image: JPG, PNG, WebP, GIF, BMP, TIFF, ICO, AVIF or HEIC.")
                    if image.width * image.height > 16_000_000:
                        raise ValidationError("Choose a profile picture smaller than 16 megapixels.")
                    image.load()
                    image = ImageOps.exif_transpose(image)
                    if fit == "square":
                        side = min(image.size)
                        left = round((image.width - side) * crop_x / 100)
                        top = round((image.height - side) * crop_y / 100)
                        image = image.crop((left, top, left + side, top + side))
                    image.thumbnail((size, size), Image.Resampling.LANCZOS)
                    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        background = Image.new("RGB", rgba.size, "white")
                        background.paste(rgba, mask=rgba.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                    photo = BytesIO()
                    image.save(photo, "JPEG", quality=88, optimize=True)
                    return photo.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning):
            raise ValidationError("Upload a valid supported image. HEIC needs the pillow-heif package from requirements.txt.")

    def update_profile(self, user_id: int, full_name: str, email: str | None,
                       nickname=None, address=None, photo=None, remove_photo=False,
                       photo_size=512, photo_fit="fit", crop_x=50, crop_y=50):
        user = self.users.get_by_id(user_id)
        if not user:
            raise ValidationError("User not found.")
        full_name = validate_full_name(full_name)
        email = normalize_email(email)
        nickname = (nickname or "").strip() if nickname is not None else None
        address = (address or "").strip() if address is not None else None
        if nickname is not None and len(nickname) > 40:
            raise ValidationError("Nickname must be 40 characters or fewer.")
        if address is not None and len(address) > 300:
            raise ValidationError("Address must be 300 characters or fewer.")
        try:
            photo_size = int(photo_size)
            crop_x, crop_y = float(crop_x), float(crop_y)
        except (ValueError, TypeError):
            raise ValidationError("Choose valid image resize and crop settings.")
        if photo_size not in {128, 256, 512, 1024} or photo_fit not in {"fit", "square"} or not all(math.isfinite(v) and 0 <= v <= 100 for v in (crop_x, crop_y)):
            raise ValidationError("Choose valid image resize and crop settings.")
        photo_data = self._prepare_photo(photo, photo_size, photo_fit, crop_x, crop_y) if photo and photo.filename else None
        details = self.get_details(user_id)
        if nickname is not None:
            details.nickname = nickname
        if address is not None:
            details.address = address
        if remove_photo:
            details.photo_data, details.photo_mime = None, None
        if photo_data:
            details.photo_data, details.photo_mime = photo_data, "image/jpeg"
        user.full_name = full_name
        user.email = email
        db.session.add(details)
        return self.users.save(user)
