import json
import logging
from typing import Any, MutableMapping

from nectar.nodelist import NodeList
from nectarstorage import SqliteConfigurationStore, SqliteEncryptedKeyStore
from nectarstorage.interfaces import StoreInterface

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


timeformat = "%Y%m%d-%H%M%S"


def generate_config_store(
    config: StoreInterface | MutableMapping[str, Any],
    blockchain: str = "hive",
    node: Any = None,
    offline: bool = False,
    **kwargs: Any,
) -> StoreInterface | MutableMapping[str, Any]:
    #: Default configuration
    """
    Populate a configuration mapping with sensible defaults for Hive-related settings and return it.

    This function mutates the provided mapping in-place by ensuring a set of default configuration keys exist and returns the same mapping. When `blockchain` is "hive" it fills the "node" entry with a current list of Hive nodes; for other values "node" is set to an empty list. Defaults include client and RPC placeholders, order expiration (7 days), canonical URL, default derivation path, and a Tor toggle.

    Parameters:
        config (MutableMapping): A dict-like configuration object to populate. It will be modified in place.
        blockchain (str): Chain identifier; "hive" populates Hive nodes, any other value leaves the node list empty.

    Returns:
        MutableMapping: The same `config` mapping after defaults have been set.
    """
    if "node" not in config:
        if node:
            # Ensure provided node is a list if it's a string representation
            if isinstance(node, str) and node.startswith("["):
                # It's already serialized or a string, let it pass, though validation would be better.
                # Assuming callers pass raw lists or single strings usually.
                config["node"] = node
            elif isinstance(node, list):
                config["node"] = json.dumps(node)
            else:
                config["node"] = node  # Fallback

        elif offline:
            config["node"] = json.dumps([])
        else:
            nodelist = NodeList()
            if blockchain == "hive":
                nodes = nodelist.get_hive_nodes(testnet=False)
            else:
                # Hive-only
                nodes = []

            # Serialize list to JSON string for SQLite storage
            config["node"] = json.dumps(nodes)
    config.setdefault("default_chain", blockchain)
    config.setdefault("password_storage", "environment")
    config.setdefault("rpcpassword", "")
    config.setdefault("rpcuser", "")
    config.setdefault("order-expiration", 7 * 24 * 60 * 60)
    config.setdefault("client_id", "")
    config.setdefault("default_canonical_url", "https://hive.blog")
    config.setdefault("default_path", "48'/13'/0'/0'/0'")
    # Legacy toggle retained for compatibility; always treated as False in code paths.
    config.setdefault("use_condenser", False)
    config.setdefault("use_tor", False)
    return config


def get_default_config_store(*args, **kwargs) -> StoreInterface | MutableMapping[str, Any]:
    config_store = SqliteConfigurationStore(*args, **kwargs)
    return generate_config_store(config_store, blockchain="hive", **kwargs)


def get_default_key_store(
    config: StoreInterface | MutableMapping[str, Any], *args, **kwargs
) -> SqliteEncryptedKeyStore:
    return SqliteEncryptedKeyStore(config=config, **kwargs)
