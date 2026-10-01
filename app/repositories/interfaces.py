from abc import ABC, abstractmethod
from typing import Iterable, Optional

from app.domain.models import Transaction, User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]: ...

    @abstractmethod
    def get_by_mobile(self, mobile: str) -> Optional[User]: ...

    @abstractmethod
    def add(self, user: User) -> User: ...

    @abstractmethod
    def save(self, user: User) -> User: ...


class TransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: Transaction) -> Transaction: ...

    @abstractmethod
    def recent_for_user(self, user_id: int, limit: int = 8) -> Iterable[Transaction]: ...

    @abstractmethod
    def all_for_user(self, user_id: int) -> Iterable[Transaction]: ...

    @abstractmethod
    def count_for_user(self, user_id: int) -> int: ...
