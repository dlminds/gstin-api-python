# API reference — `gstin-toolkit` for Python

Every export, with its exact signature. For the guided version with recipes, see
the [README](../README.md).

```python
from gstin_api import ...
```

Everything is type-annotated and the package ships `py.typed`, so mypy and
Pyright see the real types.

---

## Offline validation

Nothing here makes a network call, needs an API key, or raises.

### `is_valid_gstin(value: object) -> bool`

Format **and** modulus-36 check digit. Input is normalised first, so
`" 27-aaacr 5055 k1z7 "` is accepted.

Returns `True` for a checksum-correct number whose state code is not one the
government issues — see [`has_known_state_code`](#has_known_state_codevalue-object---bool).

### `gstin_rejection_reason(value: object) -> str | None`

Why the number was rejected, in words a user can act on. `None` whenever
`is_valid_gstin` is true, so the two can never contradict each other.

| Input | Returns |
| --- | --- |
| `""`, `"   "`, `None` | `'Empty'` |
| `"27AAACR5055K1Z"` | `'Wrong length — a GSTIN is 15 characters, this is 14'` |
| `"AAAACR5055K1Z7X"` | `'First two characters must be the numeric state code'` |
| `"27AAACR5055K1Y7"` | `'Character 14 must be the literal Z'` |
| `"27AAACR5055K0Z7"` | `'Character pattern does not match the GSTIN format'` |
| `"27AAACR5055K1Z0"` | `'Check digit mismatch — expected 7, found 0'` |

### `matches_gstin_format(value: object) -> bool`

Pattern only, checksum ignored. Useful when you want to distinguish "the shape is
wrong" from "the shape is right but the number is fake".

### `gstin_check_digit(first14: object) -> str | None`

The 15th character, computed from the first 14. `None` when the input is shorter
than 14 characters or contains a character outside `GSTIN_CHARSET` — it refuses
to guess rather than returning a wrong answer.

### `normalize_gstin(value: object) -> str`

Uppercased, with everything that is not a letter or digit stripped. Also exported
as `normalise_gstin` (the same function) for parity with the server-side
implementation.

Store the normalised form. `"27-AAACR-5055K1Z7"` and `"27aaacr5055k1z7"` are the
same registration and should not be two rows in your database.

### `parse_gstin(value: object) -> ParsedGstin`

Every derived field in one pass, so rendering a table does not recompute the
checksum once per column.

```python
@dataclass(frozen=True)
class ParsedGstin:
    input: str                                  # as supplied, before normalisation
    gstin: str                                  # normalised
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
    parts: list[GstinPart]
```

It is truthy exactly when `valid` is true, and `.as_dict()` returns a
JSON-serialisable `dict`.

### `explain_gstin(value: object) -> list[GstinPart]`

A five-row labelled breakdown. Returns `[]` for anything that is not exactly 15
characters — there is nothing honest to say about the parts of a number that is
the wrong size.

```python
@dataclass(frozen=True)
class GstinPart:
    label: str    # 'Characters 1–2 · State code'
    value: str    # '27'
    meaning: str  # 'Maharashtra'
```

### `build_gstin(pan: str, state_code: str, entity_code: str = "1") -> str`

Assembles a checksum-correct GSTIN. Raises `ValueError` if the PAN, state code or
entity code is malformed.

For fixtures and property tests. It builds a number that *passes validation*; it
does not conjure a registration into the government register.

### Field readers

| Function | Returns | Notes |
| --- | --- | --- |
| `gstin_state_code(value)` | `str \| None` | The leading two characters, whatever they are |
| `gstin_state_name(value)` | `str \| None` | `None` for an unrecognised code |
| `gstin_pan(value)` | `str \| None` | Characters 3–12 |
| `pan_holder_type(value)` | `str \| None` | From character 4 of the PAN; `'Unknown entity type'` for an unmapped letter |
| `gstin_entity_code(value)` | `str \| None` | Character 13 |
| `registration_number_in_state(value)` | `int \| None` | Character 13 as a number: `1`, then 2…9, A…Z |
| `has_known_state_code(value)` | `bool` | Whether the leading digits are a code the government issues |
| `is_valid_pan(value)` | `bool` | PAN format only — PAN has no check digit |

### Constants

| Export | Type |
| --- | --- |
| `GSTIN_CHARSET` | `str` — `'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'` |
| `GSTIN_PATTERN` | `re.Pattern[str]` |
| `PAN_PATTERN` | `re.Pattern[str]` |
| `PAN_HOLDER_TYPES` | `dict[str, str]` |

---

## State codes

### `state_for_code(code: object) -> GstState | None`

Accepts `7`, `"7"` or `"07"`. `None` for anything not in the table.

```python
@dataclass(frozen=True)
class GstState:
    code: str                    # '04'
    name: str                    # 'Chandigarh'
    kind: str                    # 'state' | 'union_territory' | 'special'
    intra_state_tax: str | None  # 'SGST' | 'UTGST' | None for 96, 97, 99
    legacy: bool                 # True for 25 and 28

    @property
    def is_union_territory(self) -> bool: ...
```

### `all_states() -> list[GstState]`

All 41 codes, in numeric order.

### `search_states(query: str) -> list[GstState]`

Matches on code or name, case-insensitively. An empty query returns everything.

### Constants

| Export | Contents |
| --- | --- |
| `STATE_CODES` | `dict[str, str]` — code → name, for every code that appears in an issued GSTIN |
| `UTGST_CODES` | `{'04', '25', '26', '31', '35', '38'}` — union territories with no legislature |
| `LEGACY_CODES` | `{'25', '28'}` — no longer issued, still valid in historic data |
| `NON_GEOGRAPHIC_CODES` | `{'96', '97', '99'}` |

Delhi (`07`), Puducherry (`34`) and Jammu and Kashmir (`01`) are union
territories **with** legislatures, so they levy SGST like a state and are
deliberately absent from `UTGST_CODES`.

---

## `GstinApiClient`

```python
GstinApiClient(
    api_key: str | None = None,
    *,
    base_url: str = "https://gstinapi.com",
    timeout: float = 30.0,
    max_retries: int = 2,
    user_agent: str | None = None,
    transport: Transport | None = None,
)
```

`api_key` falls back to the `GSTINAPI_API_KEY` environment variable.
`transport` swaps the HTTP layer — anything callable as
`(url, headers, timeout) -> Response` — which is how the test suite runs without
a network.

### `.lookup(gstin: str) -> Taxpayer | None`

Returns `None` when the number is well-formed but has no registration behind it.
Raises:

| Exception | When |
| --- | --- |
| `InvalidGstinError` | Failed the offline checks — **no request was made, no credit spent** |
| `AuthenticationError` | HTTP 401 |
| `InsufficientCreditsError` | HTTP 402 |
| `RateLimitError` | HTTP 429 after `max_retries`; carries `.retry_after` in seconds |
| `ServiceError` | HTTP 5xx, or a body that is not the expected JSON |
| `TransportError` | No HTTP response at all |

All subclass `GstinApiError`, which carries `.message`, `.status: int | None` and
`.is_fatal: bool`. `is_fatal` is true only for `AuthenticationError` and
`InsufficientCreditsError` — the two failures that will hit every remaining row.

429s, 5xx responses and transport failures are retried up to `max_retries` with
exponential backoff and full jitter, honouring `Retry-After`. 401 and 402 are
never retried.

### `.verify(gstin: str) -> VerificationResult`

Validates offline, looks up whatever survives, and describes the outcome without
raising — except for the two fatal errors, which still raise.

```python
@dataclass(frozen=True)
class VerificationResult:
    input: str
    parsed: ParsedGstin
    found: bool
    taxpayer: Taxpayer | None
    message: str | None
    looked_up: bool

    @property
    def gstin(self) -> str: ...
    @property
    def valid(self) -> bool: ...   # structurally valid; says nothing about the register
```

It is truthy exactly when `found` is true.

### `.verify_many(gstins: Iterable[str], *, workers: int = 8) -> BulkResult`

Deduplicates, skips malformed rows without spending a credit, runs lookups
`workers` at a time on a thread pool, and aborts the run on a fatal error while
still returning everything already fetched.

```python
@dataclass(frozen=True)
class BulkResult:
    results: list[VerificationResult]   # one per input, in the original order
    looked_up: int
    skipped: int
    stopped_early: bool
    error: Exception | None

    @property
    def found(self) -> list[VerificationResult]: ...
```

It is iterable, sized and indexable, so `for result in bulk`, `len(bulk)` and
`bulk[0]` all work.

---

## `Taxpayer`

What the government register says about a registration. Dates are
`datetime.date`.

```python
@dataclass(frozen=True)
class Taxpayer:
    gstin: str
    legal_name: str | None
    trade_name: str | None          # None when identical to legal_name
    status: str | None              # 'Active', 'Cancelled', 'Suspended', …
    taxpayer_type: str | None       # 'Regular', 'Composition', …
    constitution: str | None        # 'Private Limited Company', 'Proprietorship', …
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
    filings: list[Filing]           # newest first
    raw: dict[str, Any]             # the untouched upstream payload

    @property
    def is_active(self) -> bool: ...
    @property
    def filing_counts(self) -> dict[str, int]: ...

    def latest_filing(self, return_type: str) -> Filing | None: ...
```

`latest_filing` is case-insensitive: `taxpayer.latest_filing("gstr3b")` works.

When a field you need is not modelled, read it off `raw` and
[open an issue](https://github.com/dlminds/gstin-api-python/issues).

```python
@dataclass(frozen=True)
class Filing:
    type: str | None            # 'GSTR1', 'GSTR3B', …
    period: str | None          # raw MMYYYY, e.g. '082024'
    financial_year: str | None  # '2024-25' — April to March
    filed_on: date | None
    status: str | None
    mode: str | None
    arn: str | None


@dataclass(frozen=True)
class Address:
    formatted: str              # one printable line; also what str() returns
    building: str | None
    street: str | None
    locality: str | None
    city: str | None
    district: str | None
    state: str | None
    pincode: str | None
    nature: list[str]
```

---

## Command line

See [the README](../README.md#command-line). `gstin-api --help` prints the same
list.

| Command | Network | Exit `0` when |
| --- | --- | --- |
| `validate [gstin...]` | no | every number is valid |
| `parse [gstin...]` | no | every number is valid |
| `explain <gstin>` | no | the number is valid |
| `states [query]` | no | at least one code matched |
| `lookup [gstin...]` | **yes** | every number was found in the register |

`--json` on any of them emits machine-readable output. With no GSTIN arguments,
`validate`, `parse` and `lookup` read from stdin.

The parser is also importable, so a project can wrap it:

```python
from gstin_api.cli import build_parser, main

raise SystemExit(main(["validate", "27AAACR5055K1Z7"]))
```
