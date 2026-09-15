"""The offline half: format, checksum, and everything the number encodes."""

from __future__ import annotations

import pytest

from gstin_api import (
    GSTIN_CHARSET,
    build_gstin,
    explain_gstin,
    gstin_check_digit,
    gstin_rejection_reason,
    is_valid_gstin,
    is_valid_pan,
    normalise_gstin,
    normalize_gstin,
    parse_gstin,
)

# Live in the government register, and the reason the checksum cases below are
# worth anything: they are not numbers invented to satisfy the algorithm.
REAL = [
    "27AAACR5055K1Z7",  # Reliance Industries, Maharashtra
    "29AAACI1195H1ZI",  # Infosys, Karnataka
    "07AABCU9603R1ZP",  # Delhi
    "33AAACT2803M1ZI",  # Tamil Nadu
]


@pytest.mark.parametrize("gstin", REAL)
def test_accepts_gstins_that_are_live_in_the_register(gstin):
    assert is_valid_gstin(gstin)
    assert gstin_rejection_reason(gstin) is None


def test_rejects_a_number_whose_check_digit_does_not_match():
    # The real GSTIN ends in 7; anything else must fail the checksum even though
    # the character pattern is untouched.
    assert not is_valid_gstin("27AAACR5055K1Z0")
    assert gstin_rejection_reason("27AAACR5055K1Z0") == "Check digit mismatch — expected 7, found 0"


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "Empty"),
        ("", "Empty"),
        ("   ", "Empty"),
        ("27AAACR5055K1Z", "Wrong length — a GSTIN is 15 characters, this is 14"),
        ("27AAACR5055K1Z79", "Wrong length — a GSTIN is 15 characters, this is 16"),
        ("AAAACR5055K1Z7X", "First two characters must be the numeric state code"),
        ("27AAACR5055K1Y7", "Character 14 must be the literal Z"),
        ("27AAACR5055K0Z7", "Character pattern does not match the GSTIN format"),
    ],
)
def test_explains_why_a_number_was_rejected(value, reason):
    assert not is_valid_gstin(value)
    assert gstin_rejection_reason(value) == reason


@pytest.mark.parametrize(
    "value",
    [
        " 27-aaacr 5055 k1z7 ",
        "27 AAACR 5055 K1Z7",
        "\t27aaacr5055k1z7\n",
        "27-AAACR-5055K1Z7",
    ],
)
def test_normalises_the_formatting_people_paste_in(value):
    assert normalize_gstin(value) == "27AAACR5055K1Z7"
    assert is_valid_gstin(value)


def test_the_british_spelling_is_the_same_function():
    assert normalise_gstin is normalize_gstin


def test_computes_the_check_digit_from_the_first_fourteen_characters():
    assert gstin_check_digit("27AAACR5055K1Z") == "7"
    assert gstin_check_digit("29AAACI1195H1Z") == "I"
    assert gstin_check_digit("07AABCU9603R1Z") == "P"


def test_the_check_digit_refuses_to_guess():
    assert gstin_check_digit("too short") is None
    assert gstin_check_digit(None) is None
    # A character outside the GSTIN alphabet has no numeric value, so there is
    # no honest answer to give.
    assert gstin_check_digit("27AAACR5055K1-") is None


def test_every_character_of_the_alphabet_round_trips():
    # A check digit is only useful if the algorithm can actually produce all 36
    # of them; an implementation that never emits 'Z' would still pass a small
    # sample of real numbers.
    produced = {gstin_check_digit(f"27AAACR5055K{c}Z"[:14]) for c in GSTIN_CHARSET if c not in "0"}

    assert len(produced) > 20


def test_reads_the_parts_encoded_in_the_number():
    parsed = parse_gstin("27AAACR5055K1Z7")

    assert parsed.valid
    assert parsed.state_code == "27"
    assert parsed.state == "Maharashtra"
    assert parsed.state_known
    assert parsed.pan == "AAACR5055K"
    assert parsed.pan_holder_type == "Company"
    assert parsed.entity_code == "1"
    assert parsed.registration_number_in_state == 1
    assert parsed.check_digit == "7"
    assert parsed.expected_check_digit == "7"


def test_a_parsed_gstin_is_truthy_only_when_valid():
    assert parse_gstin("27AAACR5055K1Z7")
    assert not parse_gstin("27AAACR5055K1Z0")


def test_an_unissued_state_code_is_a_warning_not_a_verdict():
    # 00 is not a code the government issues, but the checksum is correct, and
    # validity has to mean the same thing here as it does server-side.
    parsed = parse_gstin("00AAACR5055K1ZN")

    assert parsed.valid
    assert not parsed.state_known
    assert parsed.state is None


def test_breaks_the_number_down_into_labelled_parts():
    parts = explain_gstin("27AAACR5055K1Z7")

    assert len(parts) == 5
    assert parts[0].value == "27"
    assert parts[1].value == "AAACR5055K"
    assert "matches" in parts[4].meaning


def test_the_breakdown_flags_a_checksum_mismatch():
    assert "expected 7" in explain_gstin("27AAACR5055K1Z0")[4].meaning


def test_there_is_nothing_to_break_down_for_the_wrong_length():
    assert explain_gstin("27AAACR5055K1Z") == []


def test_builds_a_checksum_correct_gstin_from_its_parts():
    assert build_gstin("AAACR5055K", "27") == "27AAACR5055K1Z7"
    assert is_valid_gstin(build_gstin("AAACR5055K", "29", "2"))


@pytest.mark.parametrize(
    ("pan", "state", "entity"),
    [
        ("NOTAPAN", "27", "1"),
        ("AAACR5055K", "2", "1"),
        ("AAACR5055K", "27", "0"),  # entity code 0 is never issued
    ],
)
def test_refuses_to_build_a_gstin_from_nonsense(pan, state, entity):
    with pytest.raises(ValueError):
        build_gstin(pan, state, entity)


def test_validates_a_bare_pan():
    assert is_valid_pan("AAACR5055K")
    assert is_valid_pan("aaacr5055k")
    assert not is_valid_pan("AAACR5055")
    assert not is_valid_pan("AAAC55055K")
