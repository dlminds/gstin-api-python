"""The state-code table, and the one fact about it that changes tax maths."""

from __future__ import annotations

import pytest

from gstin_api import (
    LEGACY_CODES,
    NON_GEOGRAPHIC_CODES,
    STATE_CODES,
    UTGST_CODES,
    all_states,
    search_states,
    state_for_code,
)


def test_has_a_row_for_every_published_code():
    assert len(all_states()) == len(STATE_CODES)
    assert STATE_CODES["07"] == "Delhi"
    assert STATE_CODES["27"] == "Maharashtra"
    assert STATE_CODES["33"] == "Tamil Nadu"


@pytest.mark.parametrize("code", ["7", 7, "07", " 07 "])
def test_looks_a_code_up_however_it_was_typed(code):
    assert state_for_code(code).name == "Delhi"


def test_an_unknown_code_is_none_not_a_guess():
    assert state_for_code("00") is None
    assert state_for_code(None) is None
    assert state_for_code("banana") is None


def test_a_union_territory_without_a_legislature_levies_utgst():
    chandigarh = state_for_code("04")

    assert chandigarh.is_union_territory
    assert chandigarh.intra_state_tax == "UTGST"


@pytest.mark.parametrize("code", ["07", "34", "01"])
def test_a_union_territory_with_a_legislature_levies_sgst(code):
    # Delhi, Puducherry and Jammu and Kashmir have legislatures, so an
    # intra-territory supply attracts CGST + SGST despite the UT status. This is
    # the single most common mistake in hand-rolled GST tax tables.
    state = state_for_code(code)

    assert state.is_union_territory
    assert state.intra_state_tax == "SGST"


def test_every_state_levies_sgst():
    for state in all_states():
        if state.kind == "state":
            assert state.intra_state_tax == "SGST", state.code


def test_the_non_geographic_codes_have_no_intra_state_tax():
    for code in NON_GEOGRAPHIC_CODES:
        state = state_for_code(code)

        assert state.kind == "special"
        assert state.intra_state_tax is None


def test_flags_the_codes_that_are_no_longer_issued():
    # 25 was Daman and Diu until the 2020 merger into 26; 28 was Andhra Pradesh
    # before Telangana was carved out. Both still appear in historic invoices.
    assert set(LEGACY_CODES) == {"25", "28"}

    for code in LEGACY_CODES:
        assert state_for_code(code).legacy

    assert not state_for_code("26").legacy


def test_utgst_codes_are_all_union_territories():
    for code in UTGST_CODES:
        assert state_for_code(code).is_union_territory


def test_searches_by_name_and_by_code():
    assert [state.code for state in search_states("andhra")] == ["28", "37"]
    assert [state.code for state in search_states("27")] == ["27"]
    assert search_states("") == all_states()
    assert search_states("atlantis") == []
