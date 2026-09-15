"""The GST state codes, and the handful of facts about them that change tax maths.

``STATE_CODES`` is the authority on which codes exist and what they are called;
it is the table :func:`gstin_api.gstin.gstin_state_name` parses against and it
matches ``App\\Support\\Gstin::STATE_CODES`` on gstinapi.com exactly.

Everything else here answers the question that actually costs money to get
wrong: **for an intra-state supply, is the second half of the tax SGST or
UTGST?** A union territory *with* a legislature — Delhi, Puducherry, Jammu and
Kashmir — levies SGST like a state. One without a legislature levies UTGST. This
catches people out constantly, so it is a field rather than a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "STATE_CODES",
    "UTGST_CODES",
    "LEGACY_CODES",
    "NON_GEOGRAPHIC_CODES",
    "GstState",
    "state_for_code",
    "all_states",
    "search_states",
]

#: code -> name, for every code that appears in an issued GSTIN.
STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu (merged)",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (pre-bifurcation)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "96": "Other Country",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

#: Union territories with no legislature of their own. An intra-UT supply there
#: attracts CGST + UTGST in place of CGST + SGST.
UTGST_CODES: frozenset[str] = frozenset({"04", "25", "26", "31", "35", "38"})

#: Codes that still appear in issued GSTINs and old invoices but are not
#: assigned to new registrations. 25 (Daman and Diu) was merged into 26 on
#: 26 January 2020; 28 was Andhra Pradesh before Telangana was carved out and
#: given 36, leaving the remainder of Andhra Pradesh on 37.
LEGACY_CODES: frozenset[str] = frozenset({"25", "28"})

#: Codes that are not places: OIDAR and imports (96), unassigned territory (97),
#: and the centre's own jurisdiction for UIN holders such as embassies (99).
NON_GEOGRAPHIC_CODES: frozenset[str] = frozenset({"96", "97", "99"})

_UNION_TERRITORIES: frozenset[str] = frozenset(
    {"01", "04", "07", "25", "26", "31", "34", "35", "38"}
)

StateKind = Literal["state", "union_territory", "special"]


@dataclass(frozen=True)
class GstState:
    """One row of the GST state-code table."""

    code: str
    name: str
    kind: StateKind
    #: ``"SGST"``, ``"UTGST"``, or ``None`` for the non-geographic codes.
    intra_state_tax: str | None
    #: True for codes no longer issued but still valid in historic data.
    legacy: bool

    @property
    def is_union_territory(self) -> bool:
        return self.kind == "union_territory"

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "kind": self.kind,
            "intra_state_tax": self.intra_state_tax,
            "legacy": self.legacy,
        }


def _kind(code: str) -> StateKind:
    if code in NON_GEOGRAPHIC_CODES:
        return "special"

    return "union_territory" if code in _UNION_TERRITORIES else "state"


def _intra_state_tax(code: str) -> str | None:
    if code in NON_GEOGRAPHIC_CODES:
        return None

    return "UTGST" if code in UTGST_CODES else "SGST"


_STATES: dict[str, GstState] = {
    code: GstState(
        code=code,
        name=name,
        kind=_kind(code),
        intra_state_tax=_intra_state_tax(code),
        legacy=code in LEGACY_CODES,
    )
    for code, name in STATE_CODES.items()
}


def state_for_code(code: object) -> GstState | None:
    """Look up one state code. Accepts ``7``, ``"7"`` or ``"07"``.

    >>> state_for_code(7).name
    'Delhi'
    >>> state_for_code("04").intra_state_tax
    'UTGST'
    """
    if code is None:
        return None

    key = str(code).strip()

    if key.isdigit():
        key = key.zfill(2)

    return _STATES.get(key.upper())


def all_states() -> list[GstState]:
    """Every code in the table, in numeric order."""
    return list(_STATES.values())


def search_states(query: str) -> list[GstState]:
    """Codes whose number or name contains ``query``, case-insensitively.

    >>> [s.code for s in search_states("andhra")]
    ['28', '37']
    """
    needle = str(query).strip().lower()

    if needle == "":
        return all_states()

    return [
        state
        for state in _STATES.values()
        if needle in state.code or needle in state.name.lower()
    ]
