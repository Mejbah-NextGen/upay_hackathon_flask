from dataclasses import dataclass

from flask import current_app

from app.repositories.sqlalchemy import SQLAlchemyTransactionRepository, SQLAlchemyUserRepository
from app.services.auth_service import AuthService
from app.services.payment_service import PaymentService
from app.services.profile_service import ProfileService
from app.services.wallet_service import WalletService


@dataclass(frozen=True)
class Container:
    """Simple IoC container: routes depend on services, services depend on repository abstractions."""

    users: SQLAlchemyUserRepository
    transactions: SQLAlchemyTransactionRepository
    auth: AuthService
    wallet: WalletService
    payments: PaymentService
    profile: ProfileService


def build_container(app) -> Container:
    users = SQLAlchemyUserRepository()
    transactions = SQLAlchemyTransactionRepository()
    wallet = WalletService(users, transactions)
    return Container(
        users=users,
        transactions=transactions,
        auth=AuthService(users, app.config["DEMO_OTP"]),
        wallet=wallet,
        payments=PaymentService(wallet),
        profile=ProfileService(users),
    )


def get_container() -> Container:
    return current_app.extensions["ioc_container"]
