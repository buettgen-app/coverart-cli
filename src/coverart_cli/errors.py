"""Errors that callers can distinguish from ordinary processing failures."""


class UnsupportedPlatformError(OSError):
    """The selected platform/filesystem cannot provide the required operations."""
