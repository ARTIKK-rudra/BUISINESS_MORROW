from typing import Any


class AppError(Exception):
    status_code = 400
    code = "application_error"

    def __init__(self, message: str, *, details: Any = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotConfiguredError(AppError):
    status_code = 501
    code = "not_configured"
