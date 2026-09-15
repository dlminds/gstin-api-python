"""The authorised half of the library: everything that talks to gstinapi.com.

Two rules shape this file, and both exist because the API bills per successful
lookup:

1. **A number that fails the offline checks never becomes a request.** A typo
   cannot succeed upstream, so sending it would spend a credit to be told what
   :func:`gstin_api.is_valid_gstin` already knew for free.
2. **A failure that applies to every row stops the run.** A rejected key or an
   empty credit balance will not fix itself on row 2, so
   :meth:`GstinApiClient.verify_many` aborts and hands back what it has instead
   of replaying the same failure a few thousand times.

Get an API key at https://gstinapi.com — the free tier is enough to run
everything in the README.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Protocol

from ._version import __version__
from .errors import (
    AuthenticationError,
    GstinApiError,
    InsufficientCreditsError,
    InvalidGstinError,
    RateLimitError,
    ServiceError,
    TransportError,
)
from .gstin import gstin_rejection_reason, is_valid_gstin, normalize_gstin, parse_gstin
from .models import BulkResult, Taxpayer, VerificationResult

__all__ = ["GstinApiClient", "Response", "Transport", "DEFAULT_BASE_URL", "API_KEY_ENV"]

DEFAULT_BASE_URL = "https://gstinapi.com"

#: Where the client looks for a key when none is passed to the constructor.
API_KEY_ENV = "GSTINAPI_API_KEY"

_LOOKUP_PATH = "/api/get-taxpayer-info/"


class Response(Protocol):
    """The shape a transport returns. Deliberately smaller than an HTTP library."""

    status: int
    headers: dict[str, str]
    body: str


class _Response:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: dict[str, str], body: str) -> None:
        self.status = status
        self.headers = headers
        self.body = body


Transport = Callable[[str, dict[str, str], float], Response]


def _urllib_transport(url: str, headers: dict[str, str], timeout: float) -> Response:
    """The default transport: the standard library, so the package has no dependencies.

    ``urlopen`` raises on a 4xx/5xx rather than returning it, so the error body
    is read back out of the exception — the API puts a useful message there and
    throwing it away would make every failure say "HTTP 402" and nothing else.
    """
    request = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as error:
        return _Response(
            status=error.code,
            headers={key.lower(): value for key, value in (error.headers or {}).items()},
            body=error.read().decode("utf-8", errors="replace"),
        )
    except urllib.error.URLError as error:
        raise TransportError(f"Could not reach {url}: {error.reason}") from error
    except OSError as error:  # socket timeouts and resets surface here
        raise TransportError(f"Could not reach {url}: {error}") from error


class GstinApiClient:
    """A client for the gstinapi.com GST verification API.

    >>> client = GstinApiClient("your-api-key")           # doctest: +SKIP
    >>> taxpayer = client.lookup("27AAACR5055K1Z7")       # doctest: +SKIP
    >>> taxpayer.legal_name, taxpayer.is_active           # doctest: +SKIP
    ('RELIANCE INDUSTRIES LIMITED', True)

    :param api_key: Your key from https://gstinapi.com. Falls back to the
        ``GSTINAPI_API_KEY`` environment variable, which is what you want in
        production — a key in source control is a key on GitHub.
    :param base_url: Override for self-hosted or staging deployments.
    :param timeout: Seconds to wait for a single request.
    :param max_retries: Extra attempts for failures that are worth retrying —
        429, 5xx and transport errors. Never applied to 401 or 402, which will
        not resolve themselves.
    :param transport: Swap the HTTP layer. Anything matching :data:`Transport`
        works, which is how the test suite runs without a network.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.user_agent = user_agent or f"gstin-api-python/{__version__} (+https://gstinapi.com)"
        self._transport: Transport = transport or _urllib_transport

    # ------------------------------------------------------------------ single

    def lookup(self, gstin: str) -> Taxpayer | None:
        """Look up one GSTIN in the government register.

        Returns ``None`` when the number is well-formed but has no registration
        behind it — a real answer, and one the API does not bill for.

        :raises InvalidGstinError: the number failed the offline checks, so no
            request was made and no credit was spent.
        :raises AuthenticationError: the key was rejected.
        :raises InsufficientCreditsError: the account is out of credits.
        :raises RateLimitError: still rate limited after ``max_retries``.
        :raises ServiceError: gstinapi.com or its upstream failed.
        :raises TransportError: the request never reached a server.
        """
        normalized = normalize_gstin(gstin)

        if not is_valid_gstin(normalized):
            raise InvalidGstinError(normalized, gstin_rejection_reason(normalized) or "unknown")

        if self.api_key == "":
            raise AuthenticationError(
                f"No API key. Pass one to GstinApiClient() or set {API_KEY_ENV}. "
                "Get a key at https://gstinapi.com."
            )

        response = self._request(normalized)
        payload = self._decode(response)

        taxpayer_data = payload.get("taxpayer_data")

        if not isinstance(taxpayer_data, dict):
            raise ServiceError("The API returned a body with no taxpayer_data.", status=response.status)

        # The endpoint answers 200 with status_code 0 for a number that is well
        # formed but has no registration behind it.
        if taxpayer_data.get("status_code") != 1:
            return None

        return Taxpayer.from_payload(normalized, payload)

    def verify(self, gstin: str) -> VerificationResult:
        """Validate offline, look up whatever survives, and describe the outcome.

        Unlike :meth:`lookup` this does not raise for a bad number, a missing
        registration, or a transient upstream failure — it puts them in
        ``message`` so a spreadsheet column can hold all of them. Fatal
        conditions (a rejected key, an empty balance) still raise, because they
        mean every subsequent call is pointless too.
        """
        parsed = parse_gstin(gstin)

        if not parsed.valid:
            return VerificationResult(
                input=parsed.input,
                parsed=parsed,
                found=False,
                message=f"Not looked up — {parsed.reason}. No credit was spent.",
                looked_up=False,
            )

        if not parsed.state_known:
            return VerificationResult(
                input=parsed.input,
                parsed=parsed,
                found=False,
                message=(
                    f"Not looked up — state code {parsed.state_code} is not one the government issues. "
                    "No credit was spent."
                ),
                looked_up=False,
            )

        try:
            taxpayer = self.lookup(parsed.gstin)
        except (AuthenticationError, InsufficientCreditsError):
            raise
        except GstinApiError as error:
            return VerificationResult(
                input=parsed.input,
                parsed=parsed,
                found=False,
                message=f"Lookup failed — {error.message} Nothing was charged.",
                looked_up=False,
            )

        if taxpayer is None:
            return VerificationResult(
                input=parsed.input,
                parsed=parsed,
                found=False,
                message="No GST registration exists for this number in the government register.",
                looked_up=True,
            )

        return VerificationResult(
            input=parsed.input,
            parsed=parsed,
            found=True,
            taxpayer=taxpayer,
            message=None,
            looked_up=True,
        )

    # -------------------------------------------------------------------- bulk

    def verify_many(self, gstins: Iterable[str], *, workers: int = 8) -> BulkResult:
        """Verify a list of GSTINs, in order, without spending credits twice.

        Three things happen here that a naive loop would not do:

        * **Duplicates are looked up once.** The same GSTIN five times in a
          5,000-row export costs one credit, not five.
        * **Malformed rows never leave the process**, so a column of typos is
          free.
        * **A fatal failure aborts the run** and the rows already fetched come
          back anyway, on :attr:`BulkResult.results`, with
          :attr:`BulkResult.stopped_early` set.

        :param workers: Concurrent in-flight requests. The default is polite;
          raise it if you have the rate limit for it.
        """
        inputs = list(gstins)
        results: list[VerificationResult | None] = [None] * len(inputs)

        # Pass one is entirely offline: settle every row we can answer for free,
        # and work out which distinct numbers are even worth a request.
        pending: dict[str, list[int]] = {}

        for index, value in enumerate(inputs):
            parsed = parse_gstin(value)

            if not parsed.valid:
                results[index] = VerificationResult(
                    input=parsed.input,
                    parsed=parsed,
                    found=False,
                    message=f"Not looked up — {parsed.reason}. No credit was spent.",
                )
            elif not parsed.state_known:
                results[index] = VerificationResult(
                    input=parsed.input,
                    parsed=parsed,
                    found=False,
                    message=(
                        f"Not looked up — state code {parsed.state_code} is not one the government "
                        "issues. No credit was spent."
                    ),
                )
            else:
                pending.setdefault(parsed.gstin, []).append(index)

        looked_up = 0
        stopped_early = False
        fatal: Exception | None = None
        queue = list(pending.items())
        batch = max(1, int(workers))

        with ThreadPoolExecutor(max_workers=batch) as pool:
            for start in range(0, len(queue), batch):
                if fatal is not None:
                    break

                chunk = queue[start : start + batch]
                futures = [(indices, pool.submit(self.verify, gstin)) for gstin, indices in chunk]

                for indices, future in futures:
                    try:
                        result = future.result()
                    except (AuthenticationError, InsufficientCreditsError) as error:
                        # Every request in this chunk was already in flight when
                        # this one failed, so keep draining the rest: a sibling
                        # that succeeded has already been billed, and throwing it
                        # away would make the user pay for it twice. The outer
                        # loop is what stops the run.
                        fatal = fatal or error
                        stopped_early = True
                        continue

                    looked_up += 1 if result.looked_up else 0

                    for index in indices:
                        results[index] = result

        # Anything the abort left untouched should say so, rather than look like
        # a number with no registration behind it.
        for indices in pending.values():
            for index in indices:
                if results[index] is None:
                    parsed = parse_gstin(inputs[index])
                    results[index] = VerificationResult(
                        input=parsed.input,
                        parsed=parsed,
                        found=False,
                        message="Not looked up — the run stopped early.",
                    )

        settled = [result for result in results if result is not None]

        return BulkResult(
            results=settled,
            looked_up=looked_up,
            skipped=len(settled) - looked_up,
            stopped_early=stopped_early,
            error=fatal,
        )

    # ----------------------------------------------------------------- private

    def _request(self, gstin: str) -> Response:
        url = f"{self.base_url}{_LOOKUP_PATH}{urllib.parse.quote(gstin)}"
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

        attempt = 0

        while True:
            try:
                response = self._transport(url, headers, self.timeout)
            except TransportError:
                if attempt >= self.max_retries:
                    raise

                self._sleep_before_retry(attempt, None)
                attempt += 1
                continue

            if response.status == 401:
                raise AuthenticationError(
                    self._message(response, "gstinapi.com rejected the API key. Check it at https://gstinapi.com."),
                    status=401,
                )

            if response.status == 402:
                raise InsufficientCreditsError(
                    self._message(
                        response,
                        "Out of credits. Nothing was charged for this request; top up at "
                        "https://gstinapi.com/pricing.",
                    ),
                    status=402,
                )

            if response.status == 429 or response.status >= 500:
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt, self._retry_after(response))
                    attempt += 1
                    continue

                if response.status == 429:
                    raise RateLimitError(
                        self._message(response, "Rate limited by gstinapi.com; slow down and retry."),
                        retry_after=self._retry_after(response),
                    )

                raise ServiceError(
                    self._message(
                        response,
                        f"gstinapi.com returned {response.status}. Nothing was charged; retry later.",
                    ),
                    status=response.status,
                )

            if response.status >= 400:
                raise GstinApiError(
                    self._message(response, f"gstinapi.com returned {response.status}."),
                    status=response.status,
                )

            return response

    def _sleep_before_retry(self, attempt: int, retry_after: float | None) -> None:
        # Full jitter: identical clients that fail at the same moment must not
        # come back in lockstep and fail together again.
        delay = retry_after if retry_after is not None else min(8.0, 0.5 * (2**attempt))

        time.sleep(delay * (0.5 + random.random() / 2))

    @staticmethod
    def _retry_after(response: Response) -> float | None:
        raw = response.headers.get("retry-after")

        try:
            return float(raw) if raw is not None else None
        except ValueError:
            return None

    @staticmethod
    def _message(response: Response, fallback: str) -> str:
        """Prefer the server's own explanation; it is usually the specific one."""
        try:
            body: Any = json.loads(response.body)
        except (ValueError, TypeError):
            return fallback

        if isinstance(body, dict):
            message = body.get("message") or body.get("error")

            if isinstance(message, str) and message.strip():
                return message.strip()

        return fallback

    @staticmethod
    def _decode(response: Response) -> dict[str, Any]:
        try:
            payload = json.loads(response.body)
        except ValueError as error:
            raise ServiceError(
                "gstinapi.com returned a body that is not JSON.", status=response.status
            ) from error

        if not isinstance(payload, dict):
            raise ServiceError("gstinapi.com returned an unexpected JSON shape.", status=response.status)

        return payload
