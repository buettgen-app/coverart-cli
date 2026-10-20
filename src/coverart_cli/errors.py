# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT

"""Errors that callers can distinguish from ordinary processing failures."""


class UnsupportedPlatformError(OSError):
    """The selected platform/filesystem cannot provide the required operations."""
