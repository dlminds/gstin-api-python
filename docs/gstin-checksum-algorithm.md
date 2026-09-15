# The GSTIN checksum algorithm, documented properly

*What the fifteen characters of an Indian GST number mean, how the check digit
is computed, and — the part nobody writes down — exactly which errors it catches
and which it does not.*

Every example here is executable. The claims about detection rates at the end
were measured, not assumed, and the script that measures them is included.

---

## The anatomy of a GSTIN

A GSTIN is exactly fifteen characters, drawn from `0-9` and `A-Z`. Take
`27AAACR5055K1Z7`:

```
27  AAACR5055K  1  Z  7
│   │           │  │  └─ check digit
│   │           │  └──── reserved, always 'Z'
│   │           └─────── entity code: which registration this is for this PAN in this state
│   └─────────────────── the PAN of the registered entity
└─────────────────────── state code
```

| Position | Length | Contents | Notes |
| --- | --- | --- | --- |
| 1–2 | 2 | State code | `01`–`38` plus `96`, `97`, `99`. Numeric, and not every value in the range is issued. |
| 3–12 | 10 | PAN | 5 letters, 4 digits, 1 letter. Character 4 of the PAN (position 6 overall) encodes the entity type. |
| 13 | 1 | Entity code | `1`–`9` then `A`–`Z`. **Never `0`.** The *n*th registration against this PAN in this state. |
| 14 | 1 | Reserved | A literal `Z` in every GSTIN issued under the current scheme. |
| 15 | 1 | Check digit | Computed from the first fourteen. |

So the format is:

```
/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/
```

Two things in that regex are worth pausing on, because a lot of published
regexes get them wrong:

- **`[1-9A-Z]` for the entity code, not `[0-9A-Z]`.** Registration counting
  starts at 1. A GSTIN with `0` in position 13 does not exist.
- **The check digit is `[0-9A-Z]`.** It really can be any of the 36 characters,
  including `0` — unlike the entity code.

## The check digit

The check digit is a **modulus-36 Luhn variant**. If you already know the
base-10 Luhn algorithm from credit cards, this is the same shape with a wider
alphabet.

Each character has a numeric value: its index in

```
0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ
```

So `0` is 0, `9` is 9, `A` is 10, `Z` is 35.

Walk the first fourteen characters left to right:

1. Multiply each character's value by an alternating weight — **1, 2, 1, 2 …**,
   starting at 1 for the first character.
2. Fold the product back into a single value: `Math.floor(product / 36) + (product % 36)`.
   This is the modulus-36 equivalent of "add the digits of the product", which is
   what base-10 Luhn does with a doubled digit over 9.
3. Sum all fourteen folded values.
4. The check digit is the character at index `(36 - (sum % 36)) % 36`.

That final `% 36` matters: when the sum is already a multiple of 36, `36 - 0` is
36, which is off the end of the alphabet. It wraps to `0`.

```python
CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(first14: str) -> str:
    total = 0

    for index, character in enumerate(first14[:14]):
        product = CHARSET.index(character) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36

    return CHARSET[(36 - total % 36) % 36]


gstin_check_digit("27AAACR5055K1Z")   # '7'
gstin_check_digit("29AAACI1195H1Z")   # 'I'
gstin_check_digit("07AABCU9603R1Z")   # 'P'
```

### Worked example

`27AAACR5055K1Z`, character by character:

| # | Char | Value | Weight | Product | Folded |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 1 | `2` | 2 | 1 | 2 | 2 |
| 2 | `7` | 7 | 2 | 14 | 14 |
| 3 | `A` | 10 | 1 | 10 | 10 |
| 4 | `A` | 10 | 2 | 20 | 20 |
| 5 | `A` | 10 | 1 | 10 | 10 |
| 6 | `C` | 12 | 2 | 24 | 24 |
| 7 | `R` | 27 | 1 | 27 | 27 |
| 8 | `5` | 5 | 2 | 10 | 10 |
| 9 | `0` | 0 | 1 | 0 | 0 |
| 10 | `5` | 5 | 2 | 10 | 10 |
| 11 | `5` | 5 | 1 | 5 | 5 |
| 12 | `K` | 20 | 2 | 40 | 5 |
| 13 | `1` | 1 | 1 | 1 | 1 |
| 14 | `Z` | 35 | 2 | 70 | 35 |

Row 12 is where the folding shows: `20 × 2 = 40`, and `40 / 36 = 1` remainder
`4`, so `1 + 4 = 5`. Row 14 likewise: `35 × 2 = 70` folds to `1 + 34 = 35`.

The sum is **173**. `173 % 36 = 29`. `36 − 29 = 7`. Index 7 in the alphabet is
`7`. And indeed the real GSTIN is `27AAACR5055K1Z7`.

## What the checksum actually catches

This is the part that is missing everywhere else, so it was measured rather than
asserted. Over `27AAACR5055K1Z` as a base string:

```python
from itertools import permutations

from gstin_api import gstin_check_digit

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
base = "27AAACR5055K1Z"

# Every single-character substitution.
missed_substitutions = sum(
    gstin_check_digit(base[:i] + c + base[i + 1:]) == gstin_check_digit(base)
    for i in range(14)
    for c in CHARSET
    if c != base[i]
)

# Every adjacent transposition.
missed_transpositions = {
    a + b
    for i in range(13)
    for a, b in permutations(CHARSET, 2)
    if gstin_check_digit(base[:i] + a + b + base[i + 2:])
    == gstin_check_digit(base[:i] + b + a + base[i + 2:])
}

print(missed_substitutions)    # 0, out of 490
print(missed_transpositions)   # {'0Z', 'Z0'}
```

### Every single-character typo is caught

**0 out of 490** single-character substitutions produce the same check digit.
Mistype one character anywhere in the first fourteen and the checksum will
notice. That is the strong guarantee, and it is the reason offline validation is
worth doing at all: it is the single most common data-entry error, and it is
caught for free.

### Almost every transposition is caught, with exactly one blind spot

Swap two adjacent characters and the checksum notices — **unless the two
characters are `0` and `Z`.**

`27AAAC0Z55K1Z7` and `27AAACZ055K1Z7` have the same check digit. Both are
otherwise absurd, but the arithmetic does not care.

The reason falls out of the folding step. For a character value `v < 18`, doubling
gives `2v`, which folds to itself. For `v ≥ 18`, doubling gives `2v ≥ 36`, which
folds to `2v − 35`. Transposing values `a` and `b` across a weight-1/weight-2
boundary leaves the sum unchanged only when `a + f(2b) = b + f(2a)`, and across
the 36-character alphabet the only solution with `a ≠ b` is `{0, 35}` — that is,
`0` and `Z`.

In practice this does not matter much: position 14 is always `Z`, position 13 is
never `0`, and a `0Z` pair inside a PAN is impossible because the PAN's own
format forbids it. But it is the honest answer to "is the checksum
transposition-proof?", and the answer is *almost*.

### A random string has a 1-in-36 chance

If someone invents a fifteen-character string that happens to satisfy the format
regex, it has roughly a **2.8% chance** of also satisfying the checksum. So the
check digit turns "looks like a GSTIN" into "is 36× less likely to be fabricated"
— useful, and nowhere near proof.

## What the checksum cannot catch, ever

This is the important part, and it is not a limitation of the algorithm. It is a
limitation of *arithmetic*.

**1. A cancelled registration.** The check digit is a function of the first
fourteen characters. Those characters do not change when a business
deregisters, so the number stays valid forever. A supplier who cancelled their
registration last quarter still hands you a GSTIN that passes every offline test.
An invoice from a cancelled GSTIN does not support an input tax credit claim.

**2. A number that was never issued.** `00AAACR5055K1ZN` has a correct check
digit. `00` is not a state code the government issues, and nothing was ever
registered under it. The checksum has no opinion about which numbers exist —
only about which strings are self-consistent.

**3. A number belonging to someone else.** The GSTIN on the invoice may be
perfectly real and belong to a different company entirely. Only the register
knows whose name is on it.

**4. Anything invented deliberately.** The algorithm is public. This document is
part of the reason it is public. Anyone can generate a checksum-correct GSTIN in
four lines of code — including you:

```python
from gstin_api import build_gstin

build_gstin("AAACR5055K", "27")   # '27AAACR5055K1Z7'
```

So the correct posture is a two-stage funnel:

1. **Validate offline.** Free, instant, catches every typo, and costs nothing to
   run on a million rows.
2. **Verify against the register** for anything that survives and actually
   matters — a new supplier, an invoice you are about to pay, a GSTIN that
   appears on a tax return.

Stage one exists to make stage two cheap. It is not a substitute for it.

## An implementation, and how to check yours

```bash
pip install gstin-toolkit
```

```python
from gstin_api import gstin_check_digit, gstin_rejection_reason, is_valid_gstin

is_valid_gstin("27AAACR5055K1Z7")       # True
gstin_check_digit("27AAACR5055K1Z")     # '7'
gstin_rejection_reason("27AAACR5055K1Z8")
# 'Check digit mismatch — expected 7, found 8'
```

If you would rather write your own — and this document exists partly so you
can — test it against these, which cover the cases naive implementations get
wrong:

| Input | Valid | Why it is in the list |
| --- | :---: | --- |
| `27AAACR5055K1Z7` | ✅ | A real, live registration |
| `29AAACI1195H1ZI` | ✅ | Check digit is a **letter** |
| `07AABCU9603R1ZP` | ✅ | Another letter check digit |
| `99AAACR5055KAZN` | ✅ | Entity code `A`, state code `99` |
| `00AAACR5055K1ZN` | ✅ | **Valid checksum, state code never issued** |
| `27AAACR5055K1Z0` | ❌ | Check digit off by one |
| `27AAACR5055K1Y7` | ❌ | Position 14 is not `Z` |
| `27AAACR5055K0Z7` | ❌ | Entity code `0`, which is never issued |
| `27AAACR50X5K1Z7` | ❌ | Letter inside the PAN's digit block |
| `271234R5055K1Z7` | ❌ | Digits inside the PAN's letter block |
| `27aaacr5055k1z7` | ✅ | Lowercase must normalise, not fail |
| `27-AAACR-5055K1Z7` | ✅ | So must punctuation people paste in |

The row that separates a careful implementation from a hasty one is
`00AAACR5055K1ZN`. Its checksum is genuinely correct, so a validator that
reports "invalid" is making a different claim from the one it thinks it is
making. The honest answer is "structurally valid, but `00` is not a state code
the government issues" — two facts, reported separately. `gstin-toolkit` returns
`valid=True` alongside `state_known=False` for exactly this reason.

That whole table, and thirty-odd more cases, is the committed corpus at
[`tests/fixtures/gstins.json`](../tests/fixtures/gstins.json). It is generated from
the implementation behind [gstinapi.com](https://gstinapi.com) and asserted
against by the PHP service, this library, its Node.js twin and a Google Sheets
add-on — which is what stops any of them from quietly disagreeing with the
others. Copy it; that is what it is for.

## See also

- [`gstin-toolkit` for Python](https://pypi.org/project/gstin-toolkit/) · [for Node.js](https://www.npmjs.com/package/gstin-api)
- [GST verification API docs](https://gstinapi.com/docs) — the register lookup this checksum cannot replace
- [Free GST number search](https://gstinapi.com/tools/gst-number-search) — one-off checks, no signup
- [GST state code finder](https://gstinapi.com/tools/gst-state-code-finder) — all 38 codes, plus the SGST/UTGST split

---

*Written by the team behind [gstinapi.com](https://gstinapi.com). Corrections
welcome — [open an issue](https://github.com/dlminds/gstin-api-python/issues).*
