from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

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
    def _prepare_photo(upload):
        raw = upload.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise ValidationError("Choose a profile picture under 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(raw)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ValidationError("Choose a JPG, PNG or WebP profile picture.")
                    if image.width * image.height > 16_000_000:
                        raise ValidationError("Choose a profile picture smaller than 16 megapixels.")
                    image.load()
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((512, 512))
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
            raise ValidationError("Upload a valid JPG, PNG or WebP picture.")

    def update_profile(self, user_id: int, full_name: str, email: str | None,
                       nickname=None, address=None, photo=None, remove_photo=False):
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
        photo_data = self._prepare_photo(photo) if photo and photo.filename else None
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
