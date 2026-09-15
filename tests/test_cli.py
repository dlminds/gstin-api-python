"""The command line, which is the first thing most people try."""

from __future__ import annotations

import json

from gstin_api.cli import main

GSTIN = "27AAACR5055K1Z7"


def test_validate_exits_zero_for_a_good_number(capsys):
    assert main(["validate", GSTIN]) == 0
    assert "valid" in capsys.readouterr().out


def test_validate_exits_one_for_a_bad_number(capsys):
    # The exit code is the contract for shell scripts, so it is worth a test of
    # its own rather than being implied by the output.
    assert main(["validate", "27AAACR5055K1Z0"]) == 1
    assert "Check digit mismatch" in capsys.readouterr().out


def test_validate_reports_every_row_and_fails_if_any_row_fails(capsys):
    assert main(["validate", GSTIN, "nonsense"]) == 1

    output = capsys.readouterr().out

    assert GSTIN in output
    assert "INVALID" in output


def test_validate_json_is_machine_readable(capsys):
    assert main(["validate", "--json", GSTIN]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["state"] == "Maharashtra"
    assert payload[0]["valid"] is True


def test_reads_gstins_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _FakeStdin(f"{GSTIN},29AAACI1195H1ZI\n"))

    assert main(["validate"]) == 0
    assert capsys.readouterr().out.count("valid") == 2


def test_explain_prints_the_five_parts(capsys):
    assert main(["explain", GSTIN]) == 0

    output = capsys.readouterr().out

    assert "State code" in output
    assert "Maharashtra" in output
    assert "Check digit" in output


def test_explain_refuses_a_number_of_the_wrong_length(capsys):
    assert main(["explain", "27AAACR"]) == 1
    assert "nothing to break down" in capsys.readouterr().err


def test_parse_prints_the_derived_fields(capsys):
    assert main(["parse", GSTIN]) == 0

    output = capsys.readouterr().out

    assert "AAACR5055K" in output
    assert "Company" in output


def test_states_lists_the_table(capsys):
    assert main(["states"]) == 0

    output = capsys.readouterr().out

    assert "Maharashtra" in output
    assert "CGST + UTGST" in output


def test_states_filters(capsys):
    assert main(["states", "--json", "delhi"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert [row["code"] for row in payload] == ["07"]
    assert payload[0]["intra_state_tax"] == "SGST"


def test_lookup_without_a_key_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("GSTINAPI_API_KEY", raising=False)

    assert main(["lookup", GSTIN]) == 2
    assert "No API key" in capsys.readouterr().err


class _FakeStdin:
    def __init__(self, text):
        self._lines = text.splitlines(keepends=True)

    def isatty(self):
        return False

    def __iter__(self):
        return iter(self._lines)
