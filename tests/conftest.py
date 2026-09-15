"""Shared fixtures.

``fixtures/gstins.json`` is a copy of ``tests/fixtures/gstins.json`` in the
gstinapi.com repository, which is generated from the PHP implementation the API
itself runs. Every port asserts against it, which is what stops this library
from telling a user something the API contradicts. ``test_corpus.py`` fails if
the copy has drifted from the original whenever both are checked out together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def corpus() -> list:
    path = Path(__file__).parent / "fixtures" / "gstins.json"

    return json.loads(path.read_text(encoding="utf-8"))["cases"]
