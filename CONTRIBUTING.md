# Contributing

Thanks for looking. Bug reports, corrections to the GST facts and pull requests
are all welcome.

## The one thing to know first

This library does not own the GSTIN validation rules. It is one of four
implementations — PHP (the API itself), Python, Node.js and Apps Script — pinned
to a single committed corpus, `tests/fixtures/gstins.json`. Every suite asserts
against it, which is what stops a spreadsheet, a Python script and the website
from telling a user three different things about the same number.

**If `tests/test_corpus.py` goes red, the rules moved.** Do not adjust the
library to match a new expectation without first establishing what the API now
does. If the API's behaviour genuinely changed, the corpus is regenerated on that
side and copied here — not edited by hand.

Everything else in the library is fair game.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

```bash
pytest              # tests, including the doctests in the source
ruff check .        # lint
mypy                # strict type checking
```

All three run in CI on Python 3.9 through 3.13. Please make sure they pass
locally first.

## House style

- **Comments explain why, not what.** The code already says what it does. A
  comment earns its place by recording a decision, a constraint, or a trap — the
  reason `has_known_state_code` is not folded into `is_valid_gstin`, say.
- **Tests are named as sentences** describing the behaviour they pin, not the
  function they call: `test_a_malformed_number_never_becomes_a_request`, not
  `test_lookup_2`.
- **No runtime dependencies.** The offline half has to work in a Lambda, an
  Airflow DAG and a locked-down build, and adding a dependency to a library this
  small is a cost every user pays. The sync client uses `urllib` for the same
  reason.
- **Errors are written for a person.** `'Check digit mismatch — expected 7, found
  0'` beats `'validation failed'` — someone is going to read it in a spreadsheet
  cell.

## Adding a field to `Taxpayer`

The upstream payload has far more in it than this library models. Adding a field
is welcome — model it in `models.py`, cover it in `tests/test_client.py` with a
realistic fragment of payload, and document it in `docs/api-reference.md`. The
untouched payload stays available on `taxpayer.raw` either way.

## Releasing

Maintainers only:

1. Bump `src/gstin_api/_version.py` and move the `CHANGELOG.md` entries out of
   *Unreleased*.
2. Tag `python-v<version>`.
3. The release workflow builds and publishes to PyPI via trusted publishing.
