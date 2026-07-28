import json

from nectar.wallet import storage


def test_generate_config_store_refreshes_default_nodes_before_persisting(monkeypatch):
    refresh_calls = []

    class FakeNodeList:
        def __init__(self):
            self.nodes = ["https://static.example"]

        def update_nodes(self):
            refresh_calls.append(True)
            self.nodes = ["https://beacon.example"]

        def get_hive_nodes(self, testnet=False):
            assert testnet is False
            return self.nodes

    monkeypatch.setattr(storage, "NodeList", FakeNodeList)

    config = storage.generate_config_store({})

    assert json.loads(config["node"]) == ["https://beacon.example"]
    assert refresh_calls == [True]
