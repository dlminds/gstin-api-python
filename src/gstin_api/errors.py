"""Exceptions raised by :class:`gstin_api.client.GstinApiClient`.

The split is deliberate: some failures apply to a single GSTIN and some apply to
every request you are about to make. A bulk run should retry the first kind and
stop dead on the second, so they are different classes rather than one error
with a status-code attribute.
"""

from __future__ import annotations

__all__ = [
    "GstinApiError",
    "InvalidGstinError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ServiceError",
    "TransportError",
]


class GstinApiError(Exception):
    """Base class for everything this library raises."""

    #: HTTP status that produced the error, when there was a response at all.
    status: int | None

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status

    @property
    def is_fatal(self) -> bool:
        """Whether the same failure will hit every remaining request.

        A bulk run checks this to decide between skipping a row and aborting.
        """
        return False


class InvalidGstinError(GstinApiError):
    """The GSTIN failed the offline checks, so no request was made.

    Raised before any network call. The API bills per successful lookup and a
    malformed number cannot succeed, so sending it would spend a credit to be
    told what :func:`gstin_api.is_valid_gstin` already knew for free.
    """

    def __init__(self, gstin: str, reason: str) -> None:
        super().__init__(f"{gstin!r} is not a valid GSTIN: {reason}")
        self.gstin = gstin
        self.reason = reason


class AuthenticationError(GstinApiError):
    """The API key was missing, malformed, or rejected (HTTP 401)."""

    @property
    def is_fatal(self) -> bool:
        return True


class InsufficientCreditsError(GstinApiError):
    """The account has no credits left (HTTP 402).

    Top up at https://gstinapi.com/pricing. Nothing was charged for the request
    that raised this.
    """

    @property
    def is_fatal(self) -> bool:
        return True


class RateLimitError(GstinApiError):
    """Too many requests (HTTP 429).

    ``retry_after`` carries the server's ``Retry-After`` header in seconds when
    it sent one. The client retries these on its own up to ``max_retries``; this
    is what you get when it has run out of patience.
    """

    def __init__(self, message: str, *, status: int | None = 429, retry_after: float | None = None) -> None:
        super().__init__(message, status=status)
        self.retry_after = retry_after


class ServiceError(GstinApiError):
    """gstinapi.com or the government source behind it failed (HTTP 5xx).

    Nothing is charged for these, so the number is safe to retry later.
    """


class TransportError(GstinApiError):
    """The request never got an HTTP response: DNS, TLS, timeout, reset."""
