# gstin-api — GSTIN validation and GST verification for Python

[![PyPI](https://img.shields.io/pypi/v/gstin-api.svg)](https://pypi.org/project/gstin-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/gstin-api.svg)](https://pypi.org/project/gstin-api/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

**Validate any Indian GST number offline, then verify it against the government
register.** `gstin-api` is the official Python library for
[gstinapi.com](https://gstinapi.com). It ships two layers, and a lot of projects
never need the second one:

| | What it does | Network | API key | Cost |
| --- | --- | --- | --- | --- |
| **Offline** | Format, modulus-36 check digit, state, embedded PAN, entity type, CGST+SGST vs CGST+UTGST | No | No | Free forever |
| **Online** | Legal name, trade name, **whether the registration is still active**, constitution, addresses, filing history | Yes | Yes | 1 credit per lookup |

Zero runtime dependencies. Fully typed. Python 3.9+.

```bash
pip install gstin-api
```

```python
from gstin_api import is_valid_gstin, parse_gstin

is_valid_gstin("27AAACR5055K1Z7")        # True
is_valid_gstin("27AAACR5055K1Z8")        # False — check digit does not match

parse_gstin("27AAACR5055K1Z7").state     # 'Maharashtra'
parse_gstin("27AAACR5055K1Z7").pan        # 'AAACR5055K'
```

---

## Contents

- [Why checksum validation is not enough](#why-checksum-validation-is-not-enough)
- [Install](#install)
- [Offline GSTIN validation](#offline-gstin-validation)
- [Verifying a GSTIN against the government register](#verifying-a-gstin-against-the-government-register)
- [Bulk verification](#bulk-verification)
- [Framework recipes](#framework-recipes) — Django, Flask, FastAPI, pandas
- [Error handling](#error-handling)
- [GST state codes, SGST and UTGST](#gst-state-codes-sgst-and-utgst)
- [Command line](#command-line)
- [API reference](#api-reference)
- [How the GSTIN check digit works](#how-the-gstin-check-digit-works)
- [FAQ](#faq)

---

## Why checksum validation is not enough

A GSTIN carries its own check digit, so a regex plus twenty lines of arithmetic
will reject every typo and every number someone made up on the spot. That is
genuinely useful and it is why the offline half of this library exists.

It is also where most integrations stop, and that is the bug. Consider
`27AAACR5055K1Z7`:

- The format is right.
- The check digit is right.
- **It stays right after the registration is cancelled.** Checksums do not
  expire.

Nothing in the fifteen characters tells you whether the business is registered
today, whether it was ever registered, whether the name on the invoice is the
name on the register, or whether the GSTIN belongs to somebody else entirely. A
supplier who deregistered last quarter still hands you a number that passes
every offline test — and an invoice from a cancelled GSTIN does not support an
input tax credit claim.

So: **validate offline to reject garbage for free, verify online to decide
whether to pay an invoice.** This library does both, in that order, and it will
not let you spend a credit on a number that failed step one.

## Install

```bash
pip install gstin-api
```

No dependencies, so it drops into a Lambda, a Django app or an Airflow DAG
without pulling in a transitive tree. Everything is type-annotated and the
package ships `py.typed`, so mypy and Pyright see the real types.

## Offline GSTIN validation

```python
from gstin_api import is_valid_gstin, gstin_rejection_reason, parse_gstin, explain_gstin

is_valid_gstin("27AAACR5055K1Z7")        # True
is_valid_gstin(" 27-aaacr 5055 k1z7 ")   # True — input is normalised first
is_valid_gstin("27AAACR5055K1Z8")        # False
```

When it says no, ask why. The message is written for the person who typed the
number, not for a log file:

```python
gstin_rejection_reason("27AAACR5055K1Z8")
# 'Check digit mismatch — expected 7, found 8'

gstin_rejection_reason("27AAACR5055K1Y7")
# 'Character 14 must be the literal Z'

gstin_rejection_reason("27AAACR5055K1Z")
# 'Wrong length — a GSTIN is 15 characters, this is 14'
```

`parse_gstin` reads every field the number encodes in a single pass:

```python
parsed = parse_gstin("27AAACR5055K1Z7")

parsed.valid                          # True
parsed.state                          # 'Maharashtra'
parsed.state_code                     # '27'
parsed.pan                            # 'AAACR5055K'
parsed.pan_holder_type                # 'Company'
parsed.entity_code                    # '1'
parsed.registration_number_in_state   # 1
parsed.check_digit                    # '7'
parsed.expected_check_digit           # '7'
```

`explain_gstin` returns the same thing as a labelled breakdown, which is what
you want behind a "why was this rejected?" tooltip:

```python
for part in explain_gstin("27AAACR5055K1Z7"):
    print(f"{part.label:<32} {part.value:<12} {part.meaning}")

# Characters 1–2 · State code      27           Maharashtra
# Characters 3–12 · PAN            AAACR5055K   PAN of the registered entity — Company
# Character 13 · Entity code       1            Registration number 1 for this PAN within this state
# Character 14 · Reserved          Z            Always Z in the current GSTIN scheme
# Character 15 · Check digit       7            Checksum matches the first 14 characters
```

Need a checksum-correct GSTIN for a test fixture? `build_gstin` assembles one:

```python
from gstin_api import build_gstin

build_gstin("AAACR5055K", "27")        # '27AAACR5055K1Z7'
build_gstin("AAACR5055K", "29", "2")   # second registration for this PAN in Karnataka
```

## Verifying a GSTIN against the government register

[Get an API key](https://gstinapi.com) and put it in the environment — a key in
source control is a key on GitHub.

```bash
export GSTINAPI_API_KEY="your-api-key"
```

```python
from gstin_api import GstinApiClient

client = GstinApiClient()          # reads GSTINAPI_API_KEY

taxpayer = client.lookup("27AAACR5055K1Z7")

taxpayer.legal_name          # 'RELIANCE INDUSTRIES LIMITED'
taxpayer.status              # 'Active'
taxpayer.is_active           # True   ← the field you actually came for
taxpayer.constitution        # 'Public Limited Company'
taxpayer.taxpayer_type       # 'Regular'
taxpayer.registration_date   # datetime.date(2017, 7, 1)
taxpayer.principal_address   # 'MAKER CHAMBERS IV, NARIMAN POINT, MUMBAI, …'
taxpayer.state               # 'Maharashtra Mumbai'
taxpayer.filing_counts       # {'GSTR1': 84, 'GSTR3B': 84}
taxpayer.latest_filing("GSTR3B").period   # '082024'
taxpayer.raw                 # the untouched upstream payload
```

`lookup` returns `None` when the number is well-formed but no registration
exists behind it — a real answer, and one the API does not bill for. It raises
`InvalidGstinError` **before making any request** if the number fails the
offline checks, so a typo in a CSV can never cost you a credit.

If you would rather have a row than an exception, use `verify`:

```python
result = client.verify("27AAACR5055K1Z0")

result.valid       # False
result.found       # False
result.looked_up   # False — nothing was sent, nothing was charged
result.message     # 'Not looked up — Check digit mismatch — expected 7, found 0. No credit was spent.'
```

## Bulk verification

`verify_many` is built for the 5,000-row vendor master that lands in your inbox:

```python
gstins = ["27AAACR5055K1Z7", "29AAACI1195H1ZI", "not a gstin", "27AAACR5055K1Z7"]

bulk = client.verify_many(gstins, workers=8)

len(bulk)            # 4 — one row per input, in the original order
bulk.looked_up       # 2 — the duplicate and the typo cost nothing
bulk.skipped         # 2
bulk.stopped_early   # False

for result in bulk:
    if result.found:
        print(result.gstin, result.taxpayer.legal_name, result.taxpayer.status)
    else:
        print(result.gstin or result.input, result.message)
```

Three things happen here that a `for` loop around `lookup` would not do:

1. **Duplicates are looked up once.** The same GSTIN five times in an export
   costs one credit, not five.
2. **Malformed rows never leave the process.** A column full of typos is free.
3. **A fatal failure aborts the run.** A rejected key or an empty credit balance
   will not fix itself on row 2, so the run stops, `stopped_early` is set, and
   the rows already fetched still come back on `bulk.results` — nobody should
   have to pay twice because a batch died at row 400 of 500.

### With pandas

```python
import pandas as pd
from gstin_api import GstinApiClient

df = pd.read_csv("vendors.csv")
bulk = GstinApiClient().verify_many(df["gstin"])

df["gstin_valid"]  = [r.valid for r in bulk]
df["legal_name"]   = [r.taxpayer.legal_name if r.taxpayer else None for r in bulk]
df["gst_status"]   = [r.taxpayer.status if r.taxpayer else None for r in bulk]
df["note"]         = [r.message for r in bulk]

df.to_csv("vendors-verified.csv", index=False)
```

## Framework recipes

### Django model / form validator

```python
from django.core.exceptions import ValidationError
from gstin_api import gstin_rejection_reason, normalize_gstin


def validate_gstin(value):
    reason = gstin_rejection_reason(value)

    if reason is not None:
        raise ValidationError(f"Enter a valid GSTIN — {reason}")


class Vendor(models.Model):
    gstin = models.CharField(max_length=15, validators=[validate_gstin])

    def clean(self):
        self.gstin = normalize_gstin(self.gstin)
```

### Django REST Framework serializer

```python
from rest_framework import serializers
from gstin_api import gstin_rejection_reason, normalize_gstin


class GstinField(serializers.CharField):
    def to_internal_value(self, data):
        value = normalize_gstin(super().to_internal_value(data))
        reason = gstin_rejection_reason(value)

        if reason is not None:
            raise serializers.ValidationError(reason)

        return value
```

### Pydantic v2 / FastAPI

```python
from typing import Annotated
from pydantic import AfterValidator, BaseModel
from gstin_api import gstin_rejection_reason, normalize_gstin


def _check(value: str) -> str:
    value = normalize_gstin(value)
    reason = gstin_rejection_reason(value)

    if reason is not None:
        raise ValueError(reason)

    return value


Gstin = Annotated[str, AfterValidator(_check)]


class Invoice(BaseModel):
    supplier_gstin: Gstin
    buyer_gstin: Gstin
```

### Flask / WTForms

```python
from wtforms.validators import ValidationError
from gstin_api import gstin_rejection_reason


def gstin_check(form, field):
    reason = gstin_rejection_reason(field.data)

    if reason is not None:
        raise ValidationError(reason)
```

## Error handling

Every exception carries a `.message` written for a human and a `.status` when
there was an HTTP response. `.is_fatal` is the one to branch on in a batch: it
marks the failures that will hit every remaining row.

| Exception | Raised when | `is_fatal` | Charged? |
| --- | --- | --- | --- |
| `InvalidGstinError` | The number failed the offline checks — **no request was made** | no | no |
| `AuthenticationError` | HTTP 401: the API key was missing or rejected | **yes** | no |
| `InsufficientCreditsError` | HTTP 402: the account is out of credits | **yes** | no |
| `RateLimitError` | HTTP 429, after `max_retries` — carries `.retry_after` | no | no |
| `ServiceError` | HTTP 5xx from gstinapi.com or the government source | no | no |
| `TransportError` | DNS, TLS, timeout, connection reset — no response at all | no | no |

All of them subclass `GstinApiError`.

```python
from gstin_api import GstinApiClient, GstinApiError, InsufficientCreditsError

try:
    taxpayer = GstinApiClient().lookup(gstin)
except InsufficientCreditsError:
    alert_finance_team()
except GstinApiError as error:
    log.warning("GSTIN lookup failed: %s", error.message)
```

429s, 5xx responses and transport failures are retried automatically — twice by
default, with exponential backoff and full jitter, honouring `Retry-After` when
the server sends one. 401 and 402 are never retried, because they will not
resolve themselves.

```python
client = GstinApiClient(
    api_key="…",
    timeout=30.0,      # seconds per request
    max_retries=2,     # extra attempts for retryable failures
    base_url="https://gstinapi.com",
)
```

## GST state codes, SGST and UTGST

The first two digits of a GSTIN are the state code, and this library carries the
whole table — including the fact that decides which tax you charge:

```python
from gstin_api import state_for_code, search_states, all_states

state_for_code("27").name              # 'Maharashtra'
state_for_code(7).name                 # 'Delhi' — accepts 7, '7' or '07'
state_for_code("04").intra_state_tax   # 'UTGST' — Chandigarh has no legislature
state_for_code("07").intra_state_tax   # 'SGST'  — Delhi has one, despite being a UT
state_for_code("25").legacy            # True — merged into 26 in January 2020

len(all_states())                      # 41
[s.code for s in search_states("andhra")]   # ['28', '37']
```

That Delhi line is the one that bites people. A union territory *without* a
legislature levies CGST + UTGST; Delhi, Puducherry and Jammu and Kashmir have
legislatures and levy CGST + SGST like a state. A hand-rolled "is it a UT?"
check gets this wrong every time.

An unrecognised state code — `00`, `40` — is reported separately rather than
folded into validity:

```python
from gstin_api import is_valid_gstin, has_known_state_code

is_valid_gstin("00AAACR5055K1ZN")        # True — the checksum genuinely is correct
has_known_state_code("00AAACR5055K1ZN")  # False — but 00 is not issued
```

Validity has to mean the same thing here as it does server-side, so an odd state
code is a warning you act on, not a verdict this library changes on its own.

## Command line

Installing the package installs a `gstin-api` command. Everything except
`lookup` runs offline.

```bash
$ gstin-api validate 27AAACR5055K1Z7
valid    27AAACR5055K1Z7

$ gstin-api explain 27AAACR5055K1Z7
Characters 1–2 · State code    27            Maharashtra
Characters 3–12 · PAN          AAACR5055K    PAN of the registered entity — Company
Character 13 · Entity code     1             Registration number 1 for this PAN within this state
Character 14 · Reserved        Z             Always Z in the current GSTIN scheme
Character 15 · Check digit     7             Checksum matches the first 14 characters

$ cut -d, -f3 invoices.csv | gstin-api validate --json > report.json

$ gstin-api states delhi
07  Delhi                                         union_territory   CGST + SGST

$ gstin-api lookup 27AAACR5055K1Z7        # needs GSTINAPI_API_KEY
```

Exit codes are meant for scripts: `0` when every number checked out, `1` when at
least one did not, `2` for a usage or configuration problem.

## API reference

Full signatures in [`docs/api-reference.md`](docs/api-reference.md).

### Offline

| Function | Returns |
| --- | --- |
| `is_valid_gstin(value)` | `bool` — format **and** check digit |
| `gstin_rejection_reason(value)` | `str \| None` — why it failed, in plain words |
| `matches_gstin_format(value)` | `bool` — pattern only, checksum ignored |
| `gstin_check_digit(first14)` | `str \| None` — the 15th character |
| `normalize_gstin(value)` | `str` — uppercased, punctuation stripped |
| `parse_gstin(value)` | `ParsedGstin` — every derived field, one pass |
| `explain_gstin(value)` | `list[GstinPart]` — labelled breakdown |
| `build_gstin(pan, state_code, entity_code="1")` | `str` — checksum-correct GSTIN |
| `is_valid_pan(value)` | `bool` — PAN format |
| `gstin_state_code` / `gstin_state_name` | `str \| None` |
| `gstin_pan` / `pan_holder_type` | `str \| None` |
| `gstin_entity_code` / `registration_number_in_state` | `str \| None` / `int \| None` |
| `has_known_state_code(value)` | `bool` |

### State codes

| Function | Returns |
| --- | --- |
| `state_for_code(code)` | `GstState \| None` |
| `all_states()` | `list[GstState]` |
| `search_states(query)` | `list[GstState]` |
| `STATE_CODES` | `dict[str, str]` |
| `UTGST_CODES`, `LEGACY_CODES`, `NON_GEOGRAPHIC_CODES` | `frozenset[str]` |

### Online

| Method | Returns |
| --- | --- |
| `GstinApiClient(api_key=None, *, base_url, timeout, max_retries, transport)` | client |
| `.lookup(gstin)` | `Taxpayer \| None` — raises on failure |
| `.verify(gstin)` | `VerificationResult` — a row, not an exception |
| `.verify_many(gstins, *, workers=8)` | `BulkResult` |

## How the GSTIN check digit works

Fifteen characters: `27` `AAACR5055K` `1` `Z` `7` — state code, PAN, entity
code, a reserved `Z`, and a check digit.

The check digit is a modulus-36 Luhn variant. Each character's value is its
index in `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ`. Weights alternate 1, 2, 1, 2 …
across the first fourteen characters. Each product is folded back into a single
value by adding its quotient and remainder over 36, and the check digit is the
complement of the total:

```python
CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def check_digit(first14: str) -> str:
    total = 0

    for index, character in enumerate(first14):
        product = CHARSET.index(character) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36

    return CHARSET[(36 - total % 36) % 36]

check_digit("27AAACR5055K1Z")   # '7'
```

The long version — why modulus 36 and not 10, what the algorithm does and does
not catch, and the transposition case it misses — is in
[`docs/gstin-checksum-algorithm.md`](docs/gstin-checksum-algorithm.md).

## FAQ

### How do I validate a GST number in Python?

`pip install gstin-api`, then `is_valid_gstin("27AAACR5055K1Z7")`. It checks the
15-character format and the modulus-36 check digit offline, with no API key and
no network call.

### Can I check whether a GSTIN is active without an API key?

No, and neither can anything else. Registration status lives in the government
register and changes over time; the number itself carries no expiry. That is
what `GstinApiClient.lookup` is for.

### Is there a free GST verification API?

gstinapi.com has a free tier and a free [GST number search
tool](https://gstinapi.com/tools/gst-number-search) for one-off checks. The
offline half of this library is free and unlimited forever, because it never
calls anything.

### Does this library work without internet?

Every function except `GstinApiClient` does. Validation, parsing, the state-code
table and the whole CLI other than `lookup` are pure computation.

### How do I verify GST numbers in bulk?

`client.verify_many(list_of_gstins)`. It deduplicates, skips malformed rows for
free, runs lookups concurrently, and stops the run if your credits run out —
returning everything it fetched.

### What does the 14th character `Z` mean?

Nothing yet. It is reserved for future use and is a literal `Z` in every GSTIN
issued under the current scheme, which makes it a cheap way to catch a mistyped
number.

### Can two businesses have the same PAN in a GSTIN?

Yes — one PAN, one GSTIN per state, and multiple registrations within one state
are numbered by character 13. `registration_number_in_state` reads it: `1` is
the first, `2` the second, then `9`, `A`, `B` and onward.

### Is this an official government library?

No. It is the official Python client for [gstinapi.com](https://gstinapi.com),
which reads from the GSTN data source. The offline algorithm is the one GSTN
publishes.

## Related

- **Node.js / TypeScript:** [`gstin-api` on npm](https://www.npmjs.com/package/gstin-api) — the same API surface, same parity corpus.
- **Google Sheets:** the [GSTIN Verifier add-on](https://gstinapi.com/google-sheets-gst-add-on) for people who do not write code.
- **API docs:** <https://gstinapi.com/docs>
- **Free tools:** [GST number search](https://gstinapi.com/tools/gst-number-search) · [GST state code finder](https://gstinapi.com/tools/gst-state-code-finder)

## Contributing

Bug reports and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

One thing to know before changing the validation rules: this library is pinned
to a **shared corpus** (`tests/fixtures/gstins.json`) that the API's own PHP
implementation and the Google Sheets add-on also assert against. If a change
turns `tests/test_corpus.py` red, the rules moved — check what the API now does
before "fixing" the library to match a new expectation.

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT © [GSTIN API](https://gstinapi.com)
