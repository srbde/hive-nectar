import json

import httpx2
import pytest

from nectar.haf import HAF


class FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_for_status_exc=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raise_exc = raise_for_status_exc
        self._bad_json = bad_json
        self.text = json.dumps(self._payload) if not bad_json else "<html>not json</html>"

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        if self._bad_json:
            # Simulate invalid JSON parse error
            raise json.JSONDecodeError("Expecting value", self.text, 0)
        return self._payload


@pytest.fixture
def patch_requests(monkeypatch):
    calls = {
        "last": None,
        "history": [],
    }

    def _request(self, method, url, headers=None, **kwargs):
        # Default success response returning an echo of the endpoint
        payload = kwargs.pop("_payload", {"ok": True, "url": url, "method": method})
        resp = FakeResponse(payload=payload)
        calls["last"] = (method, url, headers, kwargs)
        calls["history"].append((method, url))
        return resp

    # Patch httpx2.Client.request instead of requests.request
    monkeypatch.setattr("httpx2.Client.request", _request)
    return calls


def test_init_and_current_api_default():
    haf = HAF()
    assert haf.get_current_api() in HAF.DEFAULT_APIS


def test_init_invalid_api_raises():
    with pytest.raises(ValueError):
        HAF(api="invalid://nope")


def test_set_api_switch_and_strip():
    haf = HAF()
    haf.set_api("https://api.syncad.com/")
    assert haf.get_current_api() == "https://api.syncad.com"


def test_get_available_apis():
    haf = HAF()
    apis = haf.get_available_apis()
    assert isinstance(apis, list)
    assert all(api.startswith("http") for api in apis)


def test_reputation_success(monkeypatch):
    # Arrange: respond with a simple reputation payload
    def responder(self, method, url, headers=None, **kwargs):
        return FakeResponse(payload={"account": "alice", "reputation": 70})

    monkeypatch.setattr("httpx2.Client.request", responder)

    haf = HAF()
    data = haf.reputation("alice")
    assert data is not None
    assert data["account"] == "alice"
    assert "reputation" in data


def test_reputation_invalid_account_raises_value_error():
    haf = HAF()
    with pytest.raises(ValueError):
        haf.reputation(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        haf.reputation("")


@pytest.mark.parametrize(
    "method_name, endpoint_suffix, sample_payload",
    [
        (
            "get_account_balances",
            "balance-api/accounts/alice/balances",
            {"hive_balance": "1.000 HIVE"},
        ),
        (
            "get_account_delegations",
            "balance-api/accounts/alice/delegations",
            {"incoming_delegations": []},
        ),
        (
            "get_account_recurrent_transfers",
            "balance-api/accounts/alice/recurrent-transfers",
            {"outgoing_recurrent_transfers": []},
        ),
        ("get_reputation_version", "reputation-api/version", "1.0.0"),
        ("get_reputation_last_synced_block", "reputation-api/last-synced-block", 12345678),
        ("get_balance_version", "balance-api/version", "2.0.0"),
        ("get_balance_last_synced_block", "balance-api/last-synced-block", 87654321),
    ],
)
def test_haf_methods_success(monkeypatch, method_name, endpoint_suffix, sample_payload):
    def _request(self, method, url, headers=None, **kwargs):
        # Verify we hit the expected endpoint
        assert url.endswith("/" + endpoint_suffix)
        return FakeResponse(payload=sample_payload)

    monkeypatch.setattr("httpx2.Client.request", _request)

    haf = HAF()
    method = getattr(haf, method_name)
    # Method may require account arg
    if "accounts/alice" in endpoint_suffix:
        result = method("alice")
    else:
        result = method()
    assert result == sample_payload


@pytest.mark.parametrize(
    "method_name, needs_account",
    [
        ("reputation", True),
        ("get_account_balances", True),
        ("get_account_delegations", True),
        ("get_account_recurrent_transfers", True),
        ("get_reputation_version", False),
        ("get_reputation_last_synced_block", False),
        ("get_balance_version", False),
        ("get_balance_last_synced_block", False),
    ],
)
def test_haf_methods_request_exception_returns_none(monkeypatch, method_name, needs_account):
    def _request(self, method, url, headers=None, **kwargs):
        raise httpx2.RequestError("network down", request=None)

    monkeypatch.setattr("httpx2.Client.request", _request)

    haf = HAF()
    method = getattr(haf, method_name)
    result = method("alice") if needs_account else method()
    assert result is None


@pytest.mark.parametrize(
    "method_name, needs_account",
    [
        ("reputation", True),
        ("get_account_balances", True),
        ("get_account_delegations", True),
        ("get_account_recurrent_transfers", True),
        ("get_reputation_version", False),
        ("get_reputation_last_synced_block", False),
        ("get_balance_version", False),
        ("get_balance_last_synced_block", False),
    ],
)
def test_haf_methods_invalid_json_returns_none(monkeypatch, method_name, needs_account):
    def _request(self, method, url, headers=None, **kwargs):
        # Valid HTTP, but broken JSON
        return FakeResponse(payload=None, bad_json=True)

    monkeypatch.setattr("httpx2.Client.request", _request)

    haf = HAF()
    method = getattr(haf, method_name)
    result = method("alice") if needs_account else method()
    assert result is None
