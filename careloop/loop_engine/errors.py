"""Errors raised by the CareLoop domain engine."""


class CareLoopError(Exception):
    """Base class for expected domain errors."""


class ValidationError(CareLoopError):
    """An entity or configuration value is invalid."""


class NotFoundError(CareLoopError):
    """A requested domain object does not exist."""


class DuplicateEntityError(CareLoopError):
    """An entity identifier is already in use."""


class PermissionDenied(CareLoopError):
    """The actor's role cannot perform an action."""


class InvalidTransition(CareLoopError):
    """A case transition is not declared by its current stage."""


class InvariantViolation(CareLoopError):
    """A CareLoop invariant would be broken."""


class ClosureError(CareLoopError):
    """A case cannot be closed yet."""
