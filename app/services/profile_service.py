from app.repositories.interfaces import UserRepository
from app.services.exceptions import ValidationError
from app.services.validation import normalize_email, validate_full_name


class ProfileService:
    def __init__(self, users: UserRepository):
        self.users = users

    def update_profile(self, user_id: int, full_name: str, email: str | None):
        user = self.users.get_by_id(user_id)
        if not user:
            raise ValidationError("User not found.")
        full_name = validate_full_name(full_name)
        email = normalize_email(email)
        user.full_name = full_name
        user.email = email
        return self.users.save(user)
