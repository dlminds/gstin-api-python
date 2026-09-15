"""GSTIN API — GST number validation and verification for Python.

Two layers, and you can stop after the first:

* **Offline.** Format, modulus-36 check digit, state, embedded PAN, entity type.
  No network call, no API key, no quota, no dependencies. This is
  :func:`is_valid_gstin` and friends.
* **Online.** :class:`GstinApiClient` looks a number up in the government
  register through https://gstinapi.com and tells you the legal name, the trade
  name, whether the registration is *still active*, and where it is registered.

The offline layer also guards the online one: a number that fails validation is
never sent, so a typo cannot cost you a credit.

    >>> from gstin_api import is_valid_gstin, parse_gstin
    >>> is_valid_gstin("27AAACR5055K1Z7")
    True
    >>> parse_gstin("27AAACR5055K1Z7").state
    'Maharashtra'

Docs: https://gstinapi.com/docs
"""

from ._version import __version__
from .client import API_KEY_ENV, DEFAULT_BASE_URL, GstinApiClient
from .errors import (
    AuthenticationError,
    GstinApiError,
    InsufficientCreditsError,
    InvalidGstinError,
    RateLimitError,
    ServiceError,
    TransportError,
)
from .gstin import (
    GSTIN_CHARSET,
    GSTIN_PATTERN,
    PAN_HOLDER_TYPES,
    PAN_PATTERN,
    GstinPart,
    ParsedGstin,
    build_gstin,
    explain_gstin,
    gstin_check_digit,
    gstin_entity_code,
    gstin_pan,
    gstin_rejection_reason,
    gstin_state_code,
    gstin_state_name,
    has_known_state_code,
    is_valid_gstin,
    is_valid_pan,
    matches_gstin_format,
    normalise_gstin,
    normalize_gstin,
    pan_holder_type,
    parse_gstin,
    registration_number_in_state,
)
from .models import Address, BulkResult, Filing, Taxpayer, VerificationResult
from .states import (
    LEGACY_CODES,
    NON_GEOGRAPHIC_CODES,
    STATE_CODES,
    UTGST_CODES,
    GstState,
    all_states,
    search_states,
    state_for_code,
)

__all__ = [
    "__version__",
    # offline
    "GSTIN_CHARSET",
    "GSTIN_PATTERN",
    "PAN_PATTERN",
    "PAN_HOLDER_TYPES",
    "GstinPart",
    "ParsedGstin",
    "build_gstin",
    "explain_gstin",
    "gstin_check_digit",
    "gstin_entity_code",
    "gstin_pan",
    "gstin_rejection_reason",
    "gstin_state_code",
    "gstin_state_name",
    "has_known_state_code",
    "is_valid_gstin",
    "is_valid_pan",
    "matches_gstin_format",
    "normalise_gstin",
    "normalize_gstin",
    "pan_holder_type",
    "parse_gstin",
    "registration_number_in_state",
    # state codes
    "STATE_CODES",
    "UTGST_CODES",
    "LEGACY_CODES",
    "NON_GEOGRAPHIC_CODES",
    "GstState",
    "all_states",
    "search_states",
    "state_for_code",
    # online
    "GstinApiClient",
    "API_KEY_ENV",
    "DEFAULT_BASE_URL",
    "Address",
    "BulkResult",
    "Filing",
    "Taxpayer",
    "VerificationResult",
    # errors
    "GstinApiError",
    "InvalidGstinError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ServiceError",
    "TransportError",
]
