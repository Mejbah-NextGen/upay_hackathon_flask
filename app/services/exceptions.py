class ServiceError(Exception):
    """Base exception for application service failures."""


class ValidationError(ServiceError):
    pass


class InsufficientBalanceError(ServiceError):
    pass


class AuthenticationError(ServiceError):
    pass
