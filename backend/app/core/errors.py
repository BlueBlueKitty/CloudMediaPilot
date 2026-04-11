from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400


class ProviderError(AppError):
    pass


class AuthError(AppError):
    pass


class NotFoundError(AppError):
    pass


class ValidationError(AppError):
    pass
