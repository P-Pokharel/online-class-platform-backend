from sqlalchemy.exc import IntegrityError


class ServiceError(Exception):
    """A business-rule failure. app/main.py turns each subclass into an HTTP status."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFoundError(ServiceError):  # 404
    pass


class ForbiddenError(ServiceError):  # 403: allowed role, but not this resource
    pass


class ConflictError(ServiceError):  # 409
    pass


class InvalidReferenceError(ServiceError):  # 400: the body points at something unusable
    pass


class ValidationError(ServiceError):  # 422: a rule that spans stored and new values
    pass


def violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the database constraint behind an IntegrityError, e.g. "uq_users_email".

    The names are predictable thanks to the naming convention in app/db/base.py.
    """
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
