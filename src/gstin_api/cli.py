"""``gstin-api`` — validate, explain and look up GST numbers from a terminal.

Everything except ``lookup`` runs offline, so the whole tool is useful the
moment it is installed:

    $ gstin-api validate 27AAACR5055K1Z7
    $ gstin-api explain 27AAACR5055K1Z7
    $ gstin-api parse 27AAACR5055K1Z7 --json
    $ cat gstins.csv | gstin-api validate --json
    $ gstin-api lookup 27AAACR5055K1Z7          # needs GSTINAPI_API_KEY

Exit codes are meant for scripts: ``0`` when every number checked out, ``1``
when at least one did not, ``2`` for a usage or configuration problem.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from ._version import __version__
from .client import API_KEY_ENV, GstinApiClient
from .errors import GstinApiError
from .gstin import explain_gstin, parse_gstin
from .states import all_states, search_states

_EXIT_OK = 0
_EXIT_INVALID = 1
_EXIT_USAGE = 2


def _encode(value: Any) -> Any:
    """JSON encoder for the dataclasses and dates the library returns."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, (set, frozenset)):
        return sorted(value)

    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _dump(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, default=_encode, ensure_ascii=False)
    sys.stdout.write("\n")


def _inputs(values: Sequence[str]) -> Iterator[str]:
    """Take GSTINs from the command line, or from stdin when none are given.

    Reading stdin by default is what makes the tool composable — ``cut -d, -f3
    invoices.csv | gstin-api validate`` is the whole point.
    """
    if values:
        yield from values
        return

    if sys.stdin.isatty():
        return

    for line in sys.stdin:
        for token in line.replace(",", " ").split():
            if token:
                yield token


def _cmd_validate(args: argparse.Namespace) -> int:
    rows = [parse_gstin(value) for value in _inputs(args.gstin)]

    if not rows:
        print("No GSTINs given. Pass them as arguments or pipe them in.", file=sys.stderr)
        return _EXIT_USAGE

    if args.json:
        _dump([row.as_dict() for row in rows])
    else:
        for row in rows:
            mark = "valid  " if row.valid else "INVALID"
            detail = "" if row.valid else f"  — {row.reason}"
            # An empty row has no GSTIN to name, so quote whatever was typed —
            # otherwise a line of whitespace prints as a blank line.
            print(f"{mark}  {row.gstin or repr(row.input)}{detail}")

    return _EXIT_OK if all(row.valid for row in rows) else _EXIT_INVALID


def _cmd_parse(args: argparse.Namespace) -> int:
    rows = [parse_gstin(value) for value in _inputs(args.gstin)]

    if not rows:
        print("No GSTINs given.", file=sys.stderr)
        return _EXIT_USAGE

    if args.json:
        _dump([row.as_dict() for row in rows])
    else:
        for row in rows:
            print(f"{row.gstin or row.input}")
            print(f"  valid           {row.valid}{'' if row.valid else '  (' + str(row.reason) + ')'}")
            print(f"  state           {row.state or '—'} ({row.state_code or '—'})")
            print(f"  PAN             {row.pan or '—'}")
            print(f"  entity type     {row.pan_holder_type or '—'}")
            print(f"  registration    {row.registration_number_in_state if row.registration_number_in_state is not None else '—'} in this state")
            print(f"  check digit     {row.check_digit or '—'} (expected {row.expected_check_digit or '—'})")

    return _EXIT_OK if all(row.valid for row in rows) else _EXIT_INVALID


def _cmd_explain(args: argparse.Namespace) -> int:
    parts = explain_gstin(args.gstin)

    if not parts:
        print(f"{args.gstin!r} is not 15 characters, so there is nothing to break down.", file=sys.stderr)
        return _EXIT_INVALID

    if args.json:
        _dump([part.as_dict() for part in parts])
        return _EXIT_OK

    width = max(len(part.label) for part in parts)

    for part in parts:
        print(f"{part.label.ljust(width)}  {part.value:<12}  {part.meaning}")

    return _EXIT_OK if parse_gstin(args.gstin).valid else _EXIT_INVALID


def _cmd_states(args: argparse.Namespace) -> int:
    states = search_states(args.query) if args.query else all_states()

    if args.json:
        _dump([state.as_dict() for state in states])
        return _EXIT_OK

    if not states:
        print(f"No state code matches {args.query!r}.", file=sys.stderr)
        return _EXIT_INVALID

    for state in states:
        tax = state.intra_state_tax or "—"
        flags = " (no longer issued)" if state.legacy else ""
        print(f"{state.code}  {state.name:<44}  {state.kind:<16}  CGST + {tax}{flags}")

    return _EXIT_OK


def _cmd_lookup(args: argparse.Namespace) -> int:
    api_key = args.api_key or os.environ.get(API_KEY_ENV, "")

    if not api_key:
        print(
            f"No API key. Pass --api-key or set {API_KEY_ENV}. Get one at https://gstinapi.com.",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    client = GstinApiClient(api_key, timeout=args.timeout)
    values = list(_inputs(args.gstin))

    if not values:
        print("No GSTINs given.", file=sys.stderr)
        return _EXIT_USAGE

    try:
        bulk = client.verify_many(values)
    except GstinApiError as error:
        print(error.message, file=sys.stderr)
        return _EXIT_USAGE

    if args.json:
        _dump(
            [
                {
                    "input": result.input,
                    "gstin": result.gstin,
                    "valid": result.valid,
                    "found": result.found,
                    "message": result.message,
                    "taxpayer": (
                        {
                            key: value
                            for key, value in asdict(result.taxpayer).items()
                            if key != "raw" or args.raw
                        }
                        if result.taxpayer
                        else None
                    ),
                }
                for result in bulk.results
            ]
        )
    else:
        for result in bulk.results:
            if result.taxpayer:
                taxpayer = result.taxpayer
                print(f"{result.gstin}  {taxpayer.legal_name}")
                print(f"  status          {taxpayer.status}")
                print(f"  trade name      {taxpayer.trade_name or '—'}")
                print(f"  type            {taxpayer.taxpayer_type or '—'} · {taxpayer.constitution or '—'}")
                print(f"  registered      {taxpayer.registration_date or '—'}")
                print(f"  address         {taxpayer.principal_address or '—'}")
            else:
                print(f"{result.gstin or result.input}  {result.message}")

    if bulk.stopped_early and bulk.error is not None:
        print(f"\nRun stopped early: {bulk.error}", file=sys.stderr)
        return _EXIT_USAGE

    return _EXIT_OK if all(result.found for result in bulk.results) else _EXIT_INVALID


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gstin-api",
        description="Validate, explain and look up Indian GST numbers (GSTINs).",
        epilog="Docs: https://gstinapi.com/docs",
    )
    parser.add_argument("--version", action="version", version=f"gstin-api {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check format and check digit (offline)")
    validate.add_argument("gstin", nargs="*", help="one or more GSTINs; reads stdin when omitted")
    validate.add_argument("--json", action="store_true", help="emit JSON")
    validate.set_defaults(func=_cmd_validate)

    parse = sub.add_parser("parse", help="show every field encoded in the number (offline)")
    parse.add_argument("gstin", nargs="*", help="one or more GSTINs; reads stdin when omitted")
    parse.add_argument("--json", action="store_true", help="emit JSON")
    parse.set_defaults(func=_cmd_parse)

    explain = sub.add_parser("explain", help="break one GSTIN into its five labelled parts (offline)")
    explain.add_argument("gstin")
    explain.add_argument("--json", action="store_true", help="emit JSON")
    explain.set_defaults(func=_cmd_explain)

    states = sub.add_parser("states", help="list or search the GST state codes (offline)")
    states.add_argument("query", nargs="?", help="filter by code or name")
    states.add_argument("--json", action="store_true", help="emit JSON")
    states.set_defaults(func=_cmd_states)

    lookup = sub.add_parser("lookup", help="look GSTINs up in the government register (spends credits)")
    lookup.add_argument("gstin", nargs="*", help="one or more GSTINs; reads stdin when omitted")
    lookup.add_argument("--api-key", help=f"defaults to ${API_KEY_ENV}")
    lookup.add_argument("--timeout", type=float, default=30.0, help="seconds per request (default: 30)")
    lookup.add_argument("--json", action="store_true", help="emit JSON")
    lookup.add_argument("--raw", action="store_true", help="with --json, include the untouched upstream payload")
    lookup.set_defaults(func=_cmd_lookup)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except BrokenPipeError:  # `gstin-api states | head` should not traceback
        return _EXIT_OK
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
