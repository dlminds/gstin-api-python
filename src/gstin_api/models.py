"""The shapes a lookup returns.

The API answers with the government data source's own payload, which is a
sprawling thing with keys like ``pradr``, ``ctb`` and ``rtntype``. These classes
are the readable view over it. The untouched payload is always on ``.raw``, so
nothing here is a ceiling — when a field matters and is not modelled, read it
off ``raw`` and open an issue.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .gstin import ParsedGstin

__all__ = ["Address", "Filing", "Taxpayer", "VerificationResult", "BulkResult"]

_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_date(value: Any) -> date | None:
    """Parse the several date formats the upstream payload mixes together."""
    if value in (None, "", "NA"):
        return None

    if isinstance(value, date):
        return value

    text = str(value).strip()

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Some fields arrive as a full ISO timestamp.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


@dataclass(frozen=True)
class Address:
    """A place of business, both as fields and as one printable line."""

    formatted: str
    building: str | None = None
    street: str | None = None
    locality: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    nature: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.formatted

    @classmethod
    def from_payload(cls, payload: Any) -> Address | None:
        if not isinstance(payload, dict):
            return None

        # GSTN reports the address either as the object itself or wrapped in an
        # `addr` key depending on the record. Handle both rather than betting on
        # one and silently writing blanks for the other half of the rows.
        wrapped = payload.get("addr")
        node: dict[str, Any] = wrapped if isinstance(wrapped, dict) else payload

        parts = [
            node.get("bno"),
            node.get("flno"),
            node.get("bnm"),
            node.get("st"),
            node.get("landMark"),
            node.get("loc"),
            node.get("city"),
            node.get("dst") or node.get("district"),
            node.get("stcd"),
            node.get("pncd"),
        ]

        nature = _clean(payload.get("ntr") or node.get("ntr"))

        return cls(
            formatted=", ".join(text for part in parts if (text := _clean(part))),
            building=_clean(node.get("bnm")),
            street=_clean(node.get("st")),
            locality=_clean(node.get("loc")),
            city=_clean(node.get("city")),
            district=_clean(node.get("dst") or node.get("district")),
            state=_clean(node.get("stcd")),
            pincode=_clean(node.get("pncd")),
            nature=[item.strip() for item in nature.split(",")] if nature else [],
        )


@dataclass(frozen=True)
class Filing:
    """One return the taxpayer has filed."""

    type: str | None
    period: str | None
    financial_year: str | None
    filed_on: date | None
    status: str | None
    mode: str | None
    arn: str | None


@dataclass(frozen=True)
class Taxpayer:
    """A GST registration as the government register describes it."""

    gstin: str
    legal_name: str | None
    trade_name: str | None
    status: str | None
    taxpayer_type: str | None
    constitution: str | None
    registration_date: date | None
    cancellation_date: date | None
    last_updated_at: date | None
    nature_of_business: list[str]
    state: str | None
    state_code: str | None
    centre_jurisdiction: str | None
    state_jurisdiction: str | None
    principal_address: Address | None
    additional_addresses: list[Address]
    e_invoice_enabled: bool
    filings: list[Filing]
    #: The upstream payload, untouched.
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_active(self) -> bool:
        """Whether the registration is live *right now*.

        A cancelled GSTIN still passes every offline check — the checksum does
        not expire — which is the single best argument for calling the register
        at all. Invoices from a cancelled GSTIN do not support an input tax
        credit claim.
        """
        return (self.status or "").strip().lower() == "active"

    @property
    def filing_counts(self) -> dict[str, int]:
        """How many of each return type are on record, commonest first."""
        counts: dict[str, int] = {}

        for filing in self.filings:
            key = filing.type or "Unknown"
            counts[key] = counts.get(key, 0) + 1

        return dict(sorted(counts.items(), key=lambda item: -item[1]))

    def latest_filing(self, return_type: str) -> Filing | None:
        """The most recent filing of one type, e.g. ``"GSTR3B"``."""
        wanted = return_type.strip().upper()

        for filing in self.filings:
            if (filing.type or "").upper() == wanted:
                return filing

        return None

    @classmethod
    def from_payload(cls, gstin: str, payload: dict[str, Any]) -> Taxpayer:
        taxpayer = payload.get("taxpayer_data") or {}

        legal_name = _clean(taxpayer.get("name"))
        trade_name = _clean(taxpayer.get("tradename"))

        nature = taxpayer.get("nature")
        additional = taxpayer.get("adadr")

        return cls(
            gstin=gstin,
            legal_name=legal_name,
            # The register repeats the legal name here when there is no separate
            # trade name; echoing it back would imply a distinction that is not
            # in the data.
            trade_name=trade_name if trade_name and trade_name != legal_name else None,
            status=_clean(taxpayer.get("status")),
            taxpayer_type=_clean(taxpayer.get("type")),
            constitution=_clean(taxpayer.get("constitution")),
            registration_date=_parse_date(taxpayer.get("registrationDate")),
            cancellation_date=_parse_date(taxpayer.get("cancellationDate")),
            last_updated_at=_parse_date(taxpayer.get("lastUpdateDate")),
            nature_of_business=[str(item) for item in nature if item] if isinstance(nature, list) else [],
            state=_clean(str(taxpayer["state"]).replace("_", " ")) if taxpayer.get("state") else None,
            state_code=_clean(taxpayer.get("state_cd")),
            centre_jurisdiction=_clean(taxpayer.get("center")),
            state_jurisdiction=_clean(str(taxpayer["state"]).replace("_", " ")) if taxpayer.get("state") else None,
            principal_address=Address.from_payload(taxpayer.get("pradr")),
            additional_addresses=[
                address
                for entry in (additional if isinstance(additional, list) else [])
                if (address := Address.from_payload(entry)) is not None
            ],
            e_invoice_enabled=(
                _clean(taxpayer.get("einvoiceStatus")) == "Yes"
                or ((payload.get("nc_data") or {}).get("einvoice") or {}).get("status") is True
            ),
            filings=_parse_filings(payload.get("filing_data")),
            raw=payload,
        )


def _parse_filings(payload: Any) -> list[Filing]:
    if not isinstance(payload, list):
        return []

    filings = [
        Filing(
            type=_clean(entry.get("rtntype")),
            period=_clean(entry.get("ret_prd")),
            financial_year=_financial_year(_clean(entry.get("ret_prd"))),
            filed_on=_parse_date(entry.get("dof")),
            status=_clean(entry.get("status")),
            mode=_clean(entry.get("mof")),
            arn=_clean(entry.get("arn")),
        )
        for entry in payload
        if isinstance(entry, dict)
    ]

    # Newest first. The period is MMYYYY, so sort on YYYYMM instead of parsing
    # thirty-odd strings into dates.
    return sorted(filings, key=_period_sort_key, reverse=True)


def _period_sort_key(filing: Filing) -> int:
    period = filing.period or ""

    if len(period) != 6 or not period.isdigit():
        return 0

    return int(period[2:]) * 100 + int(period[:2])


def _financial_year(period: str | None) -> str | None:
    """"072026" becomes "2026-27". India's financial year runs April to March."""
    if not period or len(period) != 6 or not period.isdigit():
        return None

    month = int(period[:2])
    year = int(period[2:])

    if not 1 <= month <= 12:
        return None

    start = year if month >= 4 else year - 1

    return f"{start}-{str(start + 1)[2:]}"


@dataclass(frozen=True)
class VerificationResult:
    """One row of a bulk verification: what was asked, and what came back.

    Unlike :meth:`GstinApiClient.lookup`, nothing here raises. A row that failed
    the offline checks, a row with no registration behind it and a row that was
    never attempted are all describable states, and a CSV job wants all three in
    the same column rather than in an exception handler.
    """

    #: The value as supplied, before normalisation.
    input: str
    parsed: ParsedGstin
    #: True when the register returned a registration for this number.
    found: bool
    taxpayer: Taxpayer | None = None
    #: Why this row did not produce a taxpayer, in words a user can act on.
    message: str | None = None
    #: False when the offline checks or an aborted run meant no request went out.
    looked_up: bool = False

    @property
    def gstin(self) -> str:
        return self.parsed.gstin

    @property
    def valid(self) -> bool:
        """Whether the number is structurally valid. Says nothing about the register."""
        return self.parsed.valid

    def __bool__(self) -> bool:
        return self.found


@dataclass(frozen=True)
class BulkResult:
    """The outcome of :meth:`GstinApiClient.verify_many`.

    ``results`` is always one entry per input, in the original order, even when
    the run stopped early — a batch that dies on row 400 of 500 should still
    hand back the 399 answers you already paid for.
    """

    results: list[VerificationResult]
    looked_up: int
    skipped: int
    stopped_early: bool = False
    #: The failure that stopped the run, if one did.
    error: Exception | None = None

    def __iter__(self) -> Iterator[VerificationResult]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def __getitem__(self, index: int) -> VerificationResult:
        return self.results[index]

    @property
    def found(self) -> list[VerificationResult]:
        return [result for result in self.results if result.found]
