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


def test_sqlite_config_store_falls_back_on_corrupt_file(tmp_path):
    corrupt_file = tmp_path / "nectar.sqlite"
    corrupt_file.write_bytes(b"corrupt non-sqlite file content")

    config = storage.get_default_config_store(data_dir=str(tmp_path))

    assert getattr(config, "use_memory", False) is True
    assert not corrupt_file.exists()
    renamed = list(tmp_path.glob("nectar.sqlite.corrupted.*"))
    assert len(renamed) == 1
    assert config["default_chain"] == "hive"


def test_hive_initialization_with_corrupt_database(tmp_path):
    from nectar import Hive

    corrupt_file = tmp_path / "nectar.sqlite"
    corrupt_file.write_bytes(b"corrupt non-sqlite file content")

    # First initialization: recovers by falling back to memory
    hive = Hive(data_dir=str(tmp_path), offline=True)
    assert hive.config.use_memory is True
    assert hive.wallet.store.use_memory is True
    assert not corrupt_file.exists()
    assert len(list(tmp_path.glob("nectar.sqlite.corrupted.*"))) == 1

    # Restart (second initialization): now that corrupt file was renamed aside,
    # it successfully initializes a fresh clean database on disk.
    hive2 = Hive(data_dir=str(tmp_path), offline=True)
    assert hive2.config.use_memory is False
    assert hive2.wallet.store.use_memory is False
    assert corrupt_file.is_file()

    hive.close()
    hive2.close()
    if hasattr(hive.config, "close"):
        hive.config.close()
    if hasattr(hive.wallet.store, "close"):
        hive.wallet.store.close()


def test_sqlite_store_programming_error_not_masked(tmp_path):
    import sqlite3

    import pytest

    from nectarstorage.sqlite import SQLiteStore

    class BrokenStore(SQLiteStore):
        __tablename__ = "testing"
        __key__ = "key"
        __value__ = "value"

    store = BrokenStore(data_dir=str(tmp_path))
    assert store.use_memory is False

    # Query errors (e.g. column mismatch) should be raised directly, not trigger memory fallback
    with pytest.raises(sqlite3.OperationalError, match="1 values for 2 columns"):
        store.sql_execute(("INSERT INTO testing (key, value) VALUES (?)", ("only_one_param",)))

    # Store should stay on disk and not be renamed or migrated to memory
    assert store.use_memory is False
    assert (tmp_path / "nectar.sqlite").is_file()
    assert len(list(tmp_path.glob("nectar.sqlite.corrupted.*"))) == 0
