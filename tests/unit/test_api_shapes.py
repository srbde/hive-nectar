import json
import os

import pytest

from nectar import Hive
from nectar.account import Account
from nectar.block import Block
from nectarapi.graphenerpc import GrapheneRPC


# Helper to load fixtures
def load_fixture(name):
    path = os.path.join(os.path.dirname(__file__), "data", "rpc_responses", f"{name}.json")
    with open(path) as f:
        data = json.load(f)
    return data["result"]


@pytest.fixture
def mock_rpc(mocker):
    # Mock GrapheneRPC.rpcexec to return static results depending on the method name
    def mocked_rpcexec(self, payload):
        # Determine the method name from payload (either batch list or dict)
        method_name = ""
        if isinstance(payload, list) and len(payload) > 0:
            query = payload[0]
        else:
            query = payload

        # Standard JSON-RPC 2.0 appbase queries use "call" method with api/method in params
        if query.get("method") == "call":
            params = query.get("params", [])
            if len(params) > 1:
                method_name = params[1]
        else:
            method_name = query.get("method", "")

        if "get_config" in method_name:
            return load_fixture("get_config")
        elif "get_accounts" in method_name or "find_accounts" in method_name:
            return load_fixture("get_accounts")
        elif "get_block" in method_name:
            return load_fixture("get_block")

        raise ValueError(f"Unhandled mock method: {method_name}")

    mocker.patch.object(GrapheneRPC, "rpcexec", mocked_rpcexec)


def test_hive_config_shape(mock_rpc):
    # Test that Hive client gets configured correctly and parses assets from mock get_config
    hv = Hive(node="http://dummy-node-url.xyz", num_retries=1)

    # Assert connected URL matches
    assert hv.rpc.url == "http://dummy-node-url.xyz"

    # Assert address prefix matches what was returned or configured on Hive instance
    assert hv.prefix == "STM"


def test_account_properties_shape(mock_rpc):
    hv = Hive(node="http://dummy-node-url.xyz", num_retries=1)
    account = Account("thecrazygm", blockchain_instance=hv)

    # Assert standard properties are correct and have correct data shapes
    assert account.name == "thecrazygm"
    assert str(account["balance"]) == "100.000 HIVE"
    assert str(account["hbd_balance"]) == "50.000 HBD"

    # Assert profile parsing is correct
    profile = account.profile
    assert profile["img"] == "foobar"


def test_block_properties_shape(mock_rpc):
    hv = Hive(node="http://dummy-node-url.xyz", num_retries=1)
    block = Block(1, blockchain_instance=hv)

    # Assert properties of the block match the mock fixture shape
    assert block["witness"] == "initminer"
    assert block["block_id"] == "0000000100000000000000000000000000000000"
    assert block["signing_key"] == "STM6oVMzJJJgSu3hV1DZBcLdMUJYj3Cs6kGXf6WVLP3HhgLgNkA5J"
