"""The parity contract.

If this file goes red, the GSTIN rules moved. Do not "fix" the library to match
a new expectation without first checking what the API now does — the whole
purpose of the corpus is that the two cannot disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gstin_api import (
    gstin_check_digit,
    gstin_entity_code,
    gstin_pan,
    gstin_state_code,
    gstin_state_name,
    has_known_state_code,
    is_valid_gstin,
    matches_gstin_format,
    normalize_gstin,
    pan_holder_type,
    registration_number_in_state,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: Where the canonical corpus lives when this package sits inside the monorepo
#: it was extracted from. Absent in the standalone repository, and that is fine.
CANONICAL_CORPUS = Path(__file__).parents[3] / "tests" / "fixtures" / "gstins.json"


def test_the_corpus_has_real_coverage(corpus):
    # A corpus of only-valid or only-invalid numbers would pass every naive
    # implementation, including one that returns a constant.
    valid = [case for case in corpus if case["valid"]]

    assert len(corpus) >= 30
    assert len(valid) > 5
    assert len(corpus) - len(valid) > 5


def test_the_fixture_copy_matches_the_canonical_corpus():
    if not CANONICAL_CORPUS.exists():
        pytest.skip("running outside the gstinapi.com monorepo; nothing to compare against")

    ours = json.loads((FIXTURES / "gstins.json").read_text(encoding="utf-8"))
    theirs = json.loads(CANONICAL_CORPUS.read_text(encoding="utf-8"))

    assert ours == theirs, (
        "tests/fixtures/gstins.json has drifted from the canonical corpus. "
        f"Copy it back: cp {CANONICAL_CORPUS} {FIXTURES / 'gstins.json'}"
    )


def test_every_case_agrees_with_the_corpus(corpus):
    problems = []

    for case in corpus:
        value = case["input"]

        actual = {
            "normalised": normalize_gstin(value),
            "valid": is_valid_gstin(value),
            "matchesFormat": matches_gstin_format(value),
            "stateCode": gstin_state_code(value),
            "state": gstin_state_name(value),
            "stateKnown": has_known_state_code(value),
            "pan": gstin_pan(value),
            "panHolderType": pan_holder_type(value),
            "entityCode": gstin_entity_code(value),
            "registrationNumberInState": registration_number_in_state(value),
            "expectedCheckDigit": (
                gstin_check_digit(normalize_gstin(value)[:14])
                if len(normalize_gstin(value)) >= 14
                else None
            ),
        }

        expected = {key: case[key] for key in actual}

        if actual != expected:
            differences = {
                key: (expected[key], actual[key]) for key in actual if actual[key] != expected[key]
            }
            problems.append(f"{value!r} ({case['note']}): {differences}")

    assert problems == [], "\n".join(problems)
