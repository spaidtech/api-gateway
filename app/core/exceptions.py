class AppException(Exception):
    """Base exception for application-level errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
    ) -> None:
        self.message = message
        self.status_code = status_code

        super().__init__(message)


class NotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(
        self,
        message: str = "Resource not found",
    ) -> None:
        super().__init__(
            message=message,
            status_code=404,
        )


class UnauthorizedException(AppException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication required",
    ) -> None:
        super().__init__(
            message=message,
            status_code=401,
        )


class ForbiddenException(AppException):
    """Raised when the user lacks permission."""

    def __init__(
        self,
        message: str = "Permission denied",
    ) -> None:
        super().__init__(
            message=message,
            status_code=403,
        )


class ConflictException(AppException):
    """Raised when a resource conflicts with existing state."""

    def __init__(
        self,
        message: str = "Resource conflict",
    ) -> None:
        super().__init__(
            message=message,
            status_code=409,
        )