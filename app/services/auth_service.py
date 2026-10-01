from decimal import Decimal

from app.domain.models import User
from app.repositories.interfaces import UserRepository
from app.services.exceptions import AuthenticationError, ValidationError
from app.services.validation import normalize_email, normalize_mobile, validate_full_name


class AuthService:
    def __init__(self, users: UserRepository, demo_otp: str):
        self.users = users
        self.demo_otp = demo_otp

    @staticmethod
    def normalize_mobile(mobile: str) -> str:
        return normalize_mobile(mobile)

    def start_login(self, mobile: str) -> User:
        mobile = self.normalize_mobile(mobile)
        user = self.users.get_by_mobile(mobile)
        if not user:
            raise AuthenticationError("No account found. Please create an account first.")
        return user

    def register(self, full_name: str, mobile: str, email: str | None = None) -> User:
        full_name = validate_full_name(full_name)
        email = normalize_email(email)
        mobile = self.normalize_mobile(mobile)
        if self.users.get_by_mobile(mobile):
            raise ValidationError("An account with this mobile number already exists.")
        user = User(
            full_name=full_name,
            mobile=mobile,
            email=email,
            balance=Decimal("5000.00"),
            verified=True,
        )
        return self.users.add(user)

    def verify_otp(self, submitted_otp: str) -> bool:
        if (submitted_otp or "").strip() != self.demo_otp:
            raise AuthenticationError("Invalid OTP. For the demo, use the OTP shown on this page.")
        return True
