from sqlalchemy import desc

from app.domain.models import Transaction, User
from app.extensions import db
from app.repositories.interfaces import TransactionRepository, UserRepository


class SQLAlchemyUserRepository(UserRepository):
    def get_by_id(self, user_id: int):
        return db.session.get(User, user_id)

    def get_by_mobile(self, mobile: str):
        return User.query.filter_by(mobile=mobile).first()

    def add(self, user: User):
        db.session.add(user)
        db.session.commit()
        return user

    def save(self, user: User):
        db.session.add(user)
        db.session.commit()
        return user


class SQLAlchemyTransactionRepository(TransactionRepository):
    def add(self, transaction: Transaction):
        db.session.add(transaction)
        db.session.commit()
        return transaction

    def recent_for_user(self, user_id: int, limit: int = 8):
        return (
            Transaction.query.filter_by(user_id=user_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
            .all()
        )

    def all_for_user(self, user_id: int):
        return Transaction.query.filter_by(user_id=user_id).order_by(desc(Transaction.created_at)).all()

    def count_for_user(self, user_id: int):
        return Transaction.query.filter_by(user_id=user_id).count()
