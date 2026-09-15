"""Everything that can be known about a GSTIN from the string alone.

No network call, no API key, no quota. Import this half of the library and it
works offline forever — which is the point: a mistyped number is not worth a
billed request, and most of what people want from a GSTIN (which state, which
PAN, what kind of entity) is encoded in the fifteen characters themselves.

This is a deliberate port of ``App\\Support\\Gstin`` from the gstinapi.com
codebase, and of the Apps Script port that powers the Google Sheets add-on. All
three are pinned to one shared corpus, ``tests/fixtures/gstins.json``, which
every suite asserts against — so this file cannot silently drift from the rules
the API itself applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "GSTIN_CHARSET",
    "GSTIN_PATTERN",
    "PAN_PATTERN",
    "PAN_HOLDER_TYPES",
    "ParsedGstin",
    "GstinPart",
    "normalize_gstin",
    "normalise_gstin",
    "matches_gstin_format",
    "gstin_check_digit",
    "is_valid_gstin",
    "gstin_rejection_reason",
    "gstin_state_code",
    "gstin_state_name",
    "has_known_state_code",
    "gstin_pan",
    "pan_holder_type",
    "gstin_entity_code",
    "registration_number_in_state",
    "parse_gstin",
    "explain_gstin",
    "build_gstin",
    "is_valid_pan",
]

#: Character set used by the GSTIN check-digit algorithm. A character's numeric
#: value is its index in this string, which is what makes the checksum a
#: modulus-36 Luhn variant rather than the base-10 Luhn everyone knows.
GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: 2 state digits, 10-char PAN, 1 entity code, a literal Z, 1 check character.
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

#: The PAN embedded at characters 3–12: 5 letters, 4 digits, 1 letter.
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")

#: The 4th character of a PAN encodes the kind of entity that holds it, which is
#: therefore also readable straight out of a GSTIN.
PAN_HOLDER_TYPES: dict[str, str] = {
    "A": "Association of Persons (AOP)",
    "B": "Body of Individuals (BOI)",
    "C": "Company",
    "F": "Firm / Limited Liability Partnership",
    "G": "Government",
    "H": "Hindu Undivided Family (HUF)",
    "J": "Artificial Juridical Person",
    "L": "Local Authority",
    "P": "Individual / Proprietor",
    "T": "Trust",
    "K": "Krish (Trust under Wealth Tax Act)",
}


@dataclass(frozen=True)
class GstinPart:
    """One labelled slice of a GSTIN, for a field-by-field explanation."""

    label: str
    value: str
    meaning: str

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "value": self.value, "meaning": self.meaning}


@dataclass(frozen=True)
class ParsedGstin:
    """Every derived field of a GSTIN, computed in a single pass.

    ``parse_gstin`` builds one of these so that code rendering a table of
    results does not recompute the checksum once per column.
    """

    input: str
    gstin: str
    valid: bool
    reason: str | None
    state_code: str | None
    state: str | None
    state_known: bool
    pan: str | None
    pan_holder_type: str | None
    entity_code: str | None
    registration_number_in_state: int | None
    check_digit: str | None
    expected_check_digit: str | None
    parts: list[GstinPart] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "gstin": self.gstin,
            "valid": self.valid,
            "reason": self.reason,
            "state_code": self.state_code,
            "state": self.state,
            "state_known": self.state_known,
            "pan": self.pan,
            "pan_holder_type": self.pan_holder_type,
            "entity_code": self.entity_code,
            "registration_number_in_state": self.registration_number_in_state,
            "check_digit": self.check_digit,
            "expected_check_digit": self.expected_check_digit,
            "parts": [part.as_dict() for part in self.parts],
        }


def normalize_gstin(value: object) -> str:
    """Strip the formatting people paste in from invoices and spreadsheets.

    Dashes, spaces, tabs and lowercase all survive a copy-paste from a PDF, and
    none of them change what the number is. Everything else in this module
    normalises first, so callers never have to.

    >>> normalize_gstin(" 27-aaacr 5055 k1z7 ")
    '27AAACR5055K1Z7'
    """
    if value is None:
        return ""

    return _NON_ALNUM.sub("", str(value)).upper()


#: British spelling, for parity with the PHP and Apps Script implementations.
normalise_gstin = normalize_gstin


def matches_gstin_format(value: object) -> bool:
    """Whether the characters are in the right places, checksum ignored."""
    return bool(GSTIN_PATTERN.match(normalize_gstin(value)))


def gstin_check_digit(first14: object) -> str | None:
    """Compute the 15th character from the first 14.

    The algorithm is the modulus-36 scheme published by GSTN: give each
    character its index in :data:`GSTIN_CHARSET`, multiply by an alternating
    1, 2, 1, 2 … weight, fold each product back into a single digit by adding
    its quotient and remainder over 36, then take the sum's complement.

    Returns ``None`` when the input is shorter than 14 characters or contains a
    character outside the GSTIN alphabet, rather than guessing.
    """
    if not isinstance(first14, str) or len(first14) < 14:
        return None

    total = 0

    for index, character in enumerate(first14[:14]):
        value = GSTIN_CHARSET.find(character)

        if value == -1:
            return None

        # Weights alternate 1, 2, 1, 2 … across the 14 characters.
        product = value * (1 if index % 2 == 0 else 2)

        total += product // 36 + product % 36

    return GSTIN_CHARSET[(36 - total % 36) % 36]


def is_valid_gstin(value: object) -> bool:
    """Whether a GSTIN is structurally valid: right format *and* right checksum.

    This catches the overwhelming majority of typos and every casually invented
    number — but not a number invented by someone who has read the algorithm,
    and not a number that was valid until the registration was cancelled last
    Tuesday. Both of those need the register, which is what
    :class:`gstin_api.client.GstinApiClient` is for.
    """
    gstin = normalize_gstin(value)

    if not GSTIN_PATTERN.match(gstin):
        return False

    return gstin_check_digit(gstin[:14]) == gstin[14]


def gstin_rejection_reason(value: object) -> str | None:
    """Why a particular number was rejected, in words a user can act on.

    Returns ``None`` whenever :func:`is_valid_gstin` is true, so the two can
    never contradict each other in a rendered row.
    """
    gstin = normalize_gstin(value)

    if gstin == "":
        return "Empty"

    if len(gstin) != 15:
        return f"Wrong length — a GSTIN is 15 characters, this is {len(gstin)}"

    if not GSTIN_PATTERN.match(gstin):
        if not gstin[:2].isdigit():
            return "First two characters must be the numeric state code"

        if gstin[13] != "Z":
            return "Character 14 must be the literal Z"

        return "Character pattern does not match the GSTIN format"

    expected = gstin_check_digit(gstin[:14])

    if expected != gstin[14]:
        return f"Check digit mismatch — expected {expected}, found {gstin[14]}"

    return None


def gstin_state_code(value: object) -> str | None:
    """The leading two characters, whatever they turn out to be."""
    gstin = normalize_gstin(value)

    return gstin[:2] if len(gstin) >= 2 else None


def gstin_state_name(value: object) -> str | None:
    """The state the leading two digits name, or ``None`` if unrecognised."""
    from .states import STATE_CODES

    code = gstin_state_code(value)

    return STATE_CODES.get(code) if code is not None else None


def has_known_state_code(value: object) -> bool:
    """Whether the leading two digits are a code the government actually issues.

    Deliberately *not* part of :func:`is_valid_gstin`. The server-side rule is
    format plus checksum, and every port has to agree on validity, so an
    unrecognised state code is surfaced as a separate warning rather than
    quietly changing the verdict. It is still worth acting on: nothing the
    government has issued starts with ``00`` or ``40``.
    """
    from .states import STATE_CODES

    code = gstin_state_code(value)

    return code is not None and code in STATE_CODES


def gstin_pan(value: object) -> str | None:
    """The PAN embedded at characters 3–12."""
    gstin = normalize_gstin(value)

    return gstin[2:12] if len(gstin) >= 12 else None


def pan_holder_type(value: object) -> str | None:
    """What kind of entity holds the PAN inside this GSTIN."""
    pan = gstin_pan(value)

    if not pan:
        return None

    return PAN_HOLDER_TYPES.get(pan[3], "Unknown entity type")


def gstin_entity_code(value: object) -> str | None:
    """Character 13 — the registration counter for this PAN in this state."""
    gstin = normalize_gstin(value)

    return gstin[12] if len(gstin) >= 13 else None


def registration_number_in_state(value: object) -> int | None:
    """Character 13 read as a number: ``1`` is the first registration, then 2…9, A…Z."""
    code = gstin_entity_code(value)

    if code is None:
        return None

    position = GSTIN_CHARSET.find(code)

    return None if position == -1 else position


def parse_gstin(value: object) -> ParsedGstin:
    """Read every derived field out of a GSTIN in one pass.

    >>> parsed = parse_gstin("27AAACR5055K1Z7")
    >>> parsed.valid, parsed.state, parsed.pan_holder_type
    (True, 'Maharashtra', 'Company')
    """
    gstin = normalize_gstin(value)

    return ParsedGstin(
        input="" if value is None else str(value),
        gstin=gstin,
        valid=is_valid_gstin(gstin),
        reason=gstin_rejection_reason(gstin),
        state_code=gstin_state_code(gstin),
        state=gstin_state_name(gstin),
        state_known=has_known_state_code(gstin),
        pan=gstin_pan(gstin),
        pan_holder_type=pan_holder_type(gstin),
        entity_code=gstin_entity_code(gstin),
        registration_number_in_state=registration_number_in_state(gstin),
        check_digit=gstin[14] if len(gstin) >= 15 else None,
        expected_check_digit=gstin_check_digit(gstin[:14]) if len(gstin) >= 14 else None,
        parts=explain_gstin(gstin),
    )


def explain_gstin(value: object) -> list[GstinPart]:
    """A field-by-field breakdown of a 15-character GSTIN.

    Returns an empty list for anything that is not 15 characters long — there is
    nothing honest to say about the parts of a number that is the wrong size.
    """
    gstin = normalize_gstin(value)

    if len(gstin) != 15:
        return []

    expected = gstin_check_digit(gstin[:14])
    registration = registration_number_in_state(gstin)
    state = gstin_state_name(gstin)

    return [
        GstinPart(
            label="Characters 1–2 · State code",
            value=gstin[:2],
            meaning=state or "Unrecognised state code — not one the government issues",
        ),
        GstinPart(
            label="Characters 3–12 · PAN",
            value=gstin[2:12],
            meaning="PAN of the registered entity — " + (pan_holder_type(gstin) or "unknown type"),
        ),
        GstinPart(
            label="Character 13 · Entity code",
            value=gstin[12],
            meaning=(
                f"Registration number {registration} for this PAN within this state"
                if registration
                else "Registration sequence for this PAN within this state"
            ),
        ),
        GstinPart(
            label="Character 14 · Reserved",
            value=gstin[13],
            meaning=(
                "Always Z in the current GSTIN scheme"
                if gstin[13] == "Z"
                else "Should be Z — this number is non-standard"
            ),
        ),
        GstinPart(
            label="Character 15 · Check digit",
            value=gstin[14],
            meaning=(
                "Checksum matches the first 14 characters"
                if expected == gstin[14]
                else f"Checksum mismatch — expected {expected}"
            ),
        ),
    ]


def build_gstin(pan: str, state_code: str, entity_code: str = "1") -> str:
    """Assemble a checksum-correct GSTIN from its parts.

    Useful for generating fixtures and property-test inputs. It builds a number
    that *passes validation*; it does not conjure a registration into the
    government register, and using it to fabricate an invoice would be fraud.

    >>> build_gstin("AAACR5055K", "27")
    '27AAACR5055K1Z7'

    :raises ValueError: if the PAN, state code or entity code is malformed.
    """
    pan = normalize_gstin(pan)
    state_code = normalize_gstin(state_code)
    entity_code = normalize_gstin(entity_code)

    if not PAN_PATTERN.match(pan):
        raise ValueError(f"{pan!r} is not a valid PAN: 5 letters, 4 digits, 1 letter")

    if not re.fullmatch(r"[0-9]{2}", state_code):
        raise ValueError(f"{state_code!r} is not a two-digit state code")

    if not re.fullmatch(r"[1-9A-Z]", entity_code):
        raise ValueError(f"{entity_code!r} is not a valid entity code: 1–9 or A–Z")

    first14 = f"{state_code}{pan}{entity_code}Z"
    check = gstin_check_digit(first14)

    # Unreachable given the guards above, but a None here would silently produce
    # the string "…ZNone", which is far worse than an exception.
    if check is None:  # pragma: no cover
        raise ValueError(f"could not compute a check digit for {first14!r}")

    return first14 + check


def is_valid_pan(value: object) -> bool:
    """Whether a string is a well-formed Indian PAN.

    PAN has no check digit of its own, so this is a format test only — unlike a
    GSTIN, a plausible-looking PAN cannot be arithmetically disproved.
    """
    return bool(PAN_PATTERN.match(normalize_gstin(value)))
