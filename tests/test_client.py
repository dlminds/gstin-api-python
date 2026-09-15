"""The online half, run against a stub transport so the suite needs no network.

The behaviours pinned here are the ones that cost users money when they
regress: malformed numbers never become billed requests, duplicates are looked
up once, and a failure that applies to every row stops the run instead of
replaying down the column.
"""

from __future__ import annotations

import json

import pytest

from gstin_api import (
    AuthenticationError,
    GstinApiClient,
    InsufficientCreditsError,
    InvalidGstinError,
    RateLimitError,
    ServiceError,
    TransportError,
)

GSTIN = "27AAACR5055K1Z7"
OTHER = "29AAACI1195H1ZI"

FOUND = {
    "taxpayer_data": {
        "status_code": 1,
        "gstin": GSTIN,
        "name": "RELIANCE INDUSTRIES LIMITED",
        "tradename": "RELIANCE INDUSTRIES LIMITED",
        "status": "Active",
        "type": "Regular",
        "constitution": "Public Limited Company",
        "registrationDate": "01-07-2017",
        "lastUpdateDate": "12-08-2024",
        "state": "Maharashtra_Mumbai",
        "state_cd": "27",
        "center": "MUMBAI SOUTH",
        "einvoiceStatus": "Yes",
        "nature": ["Office / Sale Office", "Retail Business"],
        "pradr": {
            "addr": {
                "bnm": "MAKER CHAMBERS IV",
                "st": "NARIMAN POINT",
                "loc": "MUMBAI",
                "dst": "Mumbai",
                "stcd": "Maharashtra",
                "pncd": "400021",
            },
            "ntr": "Office / Sale Office, Retail Business",
        },
        "adadr": [{"addr": {"bnm": "RCP", "loc": "GHANSOLI", "stcd": "Maharashtra", "pncd": "400701"}}],
    },
    "filing_data": [
        {"rtntype": "GSTR3B", "ret_prd": "072024", "dof": "18-08-2024", "status": "Filed", "mof": "ONLINE", "arn": "AA27"},
        {"rtntype": "GSTR1", "ret_prd": "082024", "dof": "11-09-2024", "status": "Filed", "mof": "ONLINE", "arn": "AB27"},
        {"rtntype": "GSTR3B", "ret_prd": "082024", "dof": "20-09-2024", "status": "Filed", "mof": "ONLINE", "arn": "AC27"},
    ],
    "nc_data": {"einvoice": {"status": True}},
}

NOT_FOUND = {
    "taxpayer_data": {
        "status_code": 0,
        "gstin": GSTIN,
        "error": {"error_cd": "FO8000", "message": "Invalid GSTIN / UID"},
    },
    "filing_data": [],
    "nc_data": {},
}


class StubResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self.body = body if isinstance(body, str) else json.dumps(body)
        self.headers = headers or {}


class StubTransport:
    """Records every request and replays a scripted list of responses."""

    def __init__(self, *responses, repeat_last=True):
        self.responses = list(responses)
        self.repeat_last = repeat_last
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})

        if not self.responses:
            raise AssertionError(f"unscripted request to {url}")

        if len(self.responses) == 1 and self.repeat_last:
            return self.responses[0]

        return self.responses.pop(0)


def client(*responses, repeat_last=True, **kwargs):
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("max_retries", 0)
    transport = StubTransport(*responses, repeat_last=repeat_last)

    return GstinApiClient(transport=transport, **kwargs), transport


# ------------------------------------------------------------------ lookup


def test_looks_a_gstin_up_and_models_the_answer():
    api, _ = client(StubResponse(200, FOUND))

    taxpayer = api.lookup(GSTIN)

    assert taxpayer is not None
    assert taxpayer.legal_name == "RELIANCE INDUSTRIES LIMITED"
    # The register repeats the legal name when there is no distinct trade name;
    # echoing it back would imply a distinction that is not in the data.
    assert taxpayer.trade_name is None
    assert taxpayer.is_active
    assert taxpayer.state == "Maharashtra Mumbai"
    assert taxpayer.registration_date.isoformat() == "2017-07-01"
    assert taxpayer.e_invoice_enabled
    assert str(taxpayer.principal_address) == (
        "MAKER CHAMBERS IV, NARIMAN POINT, MUMBAI, Mumbai, Maharashtra, 400021"
    )
    assert taxpayer.principal_address.pincode == "400021"
    assert len(taxpayer.additional_addresses) == 1
    assert taxpayer.filing_counts == {"GSTR3B": 2, "GSTR1": 1}
    # Newest first, so "the latest GSTR-3B" is a lookup rather than a sort.
    assert taxpayer.latest_filing("gstr3b").period == "082024"
    assert taxpayer.latest_filing("GSTR3B").financial_year == "2024-25"
    assert taxpayer.raw == FOUND


def test_sends_the_key_in_the_header_the_api_expects():
    api, transport = client(StubResponse(200, FOUND))

    api.lookup(" 27-aaacr 5055 k1z7 ")

    call = transport.calls[0]
    assert call["url"] == "https://gstinapi.com/api/get-taxpayer-info/27AAACR5055K1Z7"
    assert call["headers"]["X-API-Key"] == "test-key"
    assert call["headers"]["User-Agent"].startswith("gstin-api-python/")


def test_a_well_formed_number_with_no_registration_is_none_not_an_error():
    api, _ = client(StubResponse(200, NOT_FOUND))

    assert api.lookup(GSTIN) is None


def test_a_malformed_number_never_becomes_a_request():
    api, transport = client(StubResponse(200, FOUND))

    with pytest.raises(InvalidGstinError) as caught:
        api.lookup("27AAACR5055K1Z0")

    assert "Check digit mismatch" in caught.value.reason
    assert transport.calls == [], "a typo must not cost a credit"


def test_a_missing_key_is_caught_before_the_network():
    api, transport = client(StubResponse(200, FOUND), api_key="")

    with pytest.raises(AuthenticationError):
        api.lookup(GSTIN)

    assert transport.calls == []


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationError),
        (402, InsufficientCreditsError),
        (429, RateLimitError),
        (500, ServiceError),
        (502, ServiceError),
    ],
)
def test_maps_each_status_to_the_error_you_can_act_on(status, error):
    api, _ = client(StubResponse(status, {"success": False, "message": "nope"}))

    with pytest.raises(error) as caught:
        api.lookup(GSTIN)

    # The server's own message beats a generic one — it is usually specific.
    assert caught.value.message == "nope"
    assert caught.value.status == status


def test_only_the_errors_that_apply_to_every_row_are_fatal():
    api, _ = client(StubResponse(402, {}))

    with pytest.raises(InsufficientCreditsError) as caught:
        api.lookup(GSTIN)

    assert caught.value.is_fatal

    api, _ = client(StubResponse(503, {}))

    with pytest.raises(ServiceError) as caught:
        api.lookup(GSTIN)

    assert not caught.value.is_fatal


def test_a_body_that_is_not_json_is_a_service_error():
    api, _ = client(StubResponse(200, "<html>502 Bad Gateway</html>"))

    with pytest.raises(ServiceError):
        api.lookup(GSTIN)


# ------------------------------------------------------------------ retries


def test_retries_a_transient_failure_and_then_succeeds(monkeypatch):
    monkeypatch.setattr("gstin_api.client.time.sleep", lambda _: None)

    api, transport = client(
        StubResponse(503, {}),
        StubResponse(200, FOUND),
        max_retries=2,
    )

    assert api.lookup(GSTIN) is not None
    assert len(transport.calls) == 2


def test_never_retries_a_rejected_key(monkeypatch):
    monkeypatch.setattr("gstin_api.client.time.sleep", lambda _: None)

    api, transport = client(StubResponse(401, {}), max_retries=5)

    with pytest.raises(AuthenticationError):
        api.lookup(GSTIN)

    assert len(transport.calls) == 1, "a rejected key will not un-reject itself"


def test_honours_retry_after_when_the_server_sends_one(monkeypatch):
    slept = []
    monkeypatch.setattr("gstin_api.client.time.sleep", slept.append)

    api, _ = client(
        StubResponse(429, {}, {"retry-after": "4"}),
        StubResponse(200, FOUND),
        max_retries=1,
    )

    api.lookup(GSTIN)

    # Jittered down by up to half, never up: a server that says 4 seconds must
    # not be hit at 8.
    assert 2.0 <= slept[0] <= 4.0


def test_a_transport_failure_is_retried_then_raised(monkeypatch):
    monkeypatch.setattr("gstin_api.client.time.sleep", lambda _: None)

    def boom(url, headers, timeout):
        raise TransportError("connection reset")

    api = GstinApiClient("k", transport=boom, max_retries=1)

    with pytest.raises(TransportError):
        api.lookup(GSTIN)


# ------------------------------------------------------------------- verify


def test_verify_describes_a_bad_number_instead_of_raising():
    api, transport = client(StubResponse(200, FOUND))

    result = api.verify("27AAACR5055K1Z0")

    assert not result.valid
    assert not result.found
    assert not result.looked_up
    assert "No credit was spent" in result.message
    assert transport.calls == []


def test_verify_skips_a_state_code_the_government_does_not_issue():
    api, transport = client(StubResponse(200, FOUND))

    result = api.verify("00AAACR5055K1ZN")

    assert result.valid, "the checksum is genuinely correct"
    assert not result.looked_up
    assert transport.calls == []


def test_verify_turns_a_transient_failure_into_a_row_not_an_exception():
    api, _ = client(StubResponse(503, {"message": "upstream is down."}))

    result = api.verify(GSTIN)

    assert not result.found
    assert "upstream is down." in result.message


def test_verify_still_raises_the_failures_that_end_the_run():
    api, _ = client(StubResponse(402, {}))

    with pytest.raises(InsufficientCreditsError):
        api.verify(GSTIN)


# --------------------------------------------------------------- verify_many


def test_verify_many_keeps_the_input_order_and_answers_every_row():
    api, _ = client(StubResponse(200, FOUND))

    bulk = api.verify_many([GSTIN, "not a gstin", OTHER])

    assert len(bulk) == 3
    assert [result.input for result in bulk] == [GSTIN, "not a gstin", OTHER]
    assert bulk.results[1].message.startswith("Not looked up")
    assert bulk.looked_up == 2
    assert bulk.skipped == 1
    assert not bulk.stopped_early


def test_verify_many_looks_a_repeated_gstin_up_once():
    api, transport = client(StubResponse(200, FOUND))

    bulk = api.verify_many([GSTIN, GSTIN, GSTIN, " 27-aaacr-5055-k1z7 "])

    assert len(transport.calls) == 1, "four rows, one number, one credit"
    assert all(result.found for result in bulk)


def test_verify_many_hands_back_what_it_fetched_when_the_run_dies():
    api, _ = client(
        StubResponse(200, FOUND),
        StubResponse(402, {"message": "Insufficient credits"}),
        repeat_last=False,
    )

    bulk = api.verify_many([GSTIN, OTHER, "07AABCU9603R1ZP"], workers=1)

    assert bulk.stopped_early
    assert isinstance(bulk.error, InsufficientCreditsError)
    assert len(bulk) == 3, "every input still gets a row"
    assert bulk.results[0].found, "the row already paid for is not thrown away"
    assert bulk.results[1].message == "Not looked up — the run stopped early."


def test_verify_many_keeps_a_row_that_was_already_billed():
    # Both requests in the chunk were in flight when the 402 came back. The one
    # that succeeded has already cost a credit, so discarding it would make the
    # user pay for that number twice on the re-run. Keyed by GSTIN rather than
    # scripted in order, because thread scheduling decides who finishes first.
    def transport(url, headers, timeout):
        if url.endswith(OTHER):
            return StubResponse(200, FOUND)

        return StubResponse(402, {"message": "Insufficient credits"})

    api = GstinApiClient("test-key", transport=transport, max_retries=0)

    bulk = api.verify_many([GSTIN, OTHER], workers=2)

    assert bulk.stopped_early
    assert bulk.results[0].message == "Not looked up — the run stopped early."
    assert bulk.results[1].found, "the sibling that succeeded survives"
    assert bulk.looked_up == 1


def test_verify_many_on_an_empty_list_does_nothing():
    api, transport = client(StubResponse(200, FOUND))

    bulk = api.verify_many([])

    assert len(bulk) == 0
    assert transport.calls == []


def test_found_filters_to_the_rows_with_a_registration():
    api, _ = client(StubResponse(200, FOUND))

    bulk = api.verify_many([GSTIN, "nonsense"])

    assert len(bulk.found) == 1
