from typing import Any

# Track shared httpx client alongside the shared Hive instance so callers that
# construct Hive directly (e.g., Hive(keys=[...])) still reuse the same pool.
_shared_transport: dict[str, Any] = {}


class SharedInstance:
    """Singleton for the shared Blockchain Instance (Hive-only)."""

    instance = None
    config = {}


def shared_blockchain_instance() -> Any:
    """Initialize and return the shared Hive instance.

    Hive-only: this always returns a `nectar.Hive` instance, regardless of any
    legacy configuration that may have referenced other chains.
    """
    if not SharedInstance.instance:
        clear_cache()
        SharedInstance.instance = _build_hive(**SharedInstance.config)
    return SharedInstance.instance


def set_shared_blockchain_instance(blockchain_instance: Any) -> None:
    """
    Override the shared Hive instance used by the module and clear related caches.

    This sets SharedInstance.instance to the provided blockchain instance and calls clear_cache()
    to invalidate any cached blockchain objects so consumers observe the new instance immediately.
    """
    clear_cache()
    SharedInstance.instance = blockchain_instance
    if hasattr(blockchain_instance, "rpc") and getattr(blockchain_instance, "rpc", None):
        _shared_transport["rpc"] = blockchain_instance.rpc


def shared_hive_instance() -> Any:
    """Initialize (if needed) and return the shared Hive instance."""
    return shared_blockchain_instance()


def set_shared_hive_instance(hive_instance: Any) -> None:
    """
    Override the global shared Hive instance used by the module.

    Replaces the current SharedInstance.instance with the provided hive_instance and clears related caches so subsequent calls return the new instance.

    Parameters:
        hive_instance: The nectar.Hive instance to set as the shared global instance.
    """
    set_shared_blockchain_instance(hive_instance)


def clear_cache() -> None:
    """
    Clear cached blockchain object state.

    Performs a lazy import of BlockchainObject and calls its clear_cache() method to purge any in-memory caches of blockchain objects (used when the shared Hive instance or configuration changes).
    """
    from .blockchainobject import BlockchainObject

    BlockchainObject.clear_cache()


def set_shared_config(config: dict[str, Any]) -> None:
    """
    Set configuration for the shared Hive instance without creating the instance.

    Updates the global SharedInstance.config with the provided mapping. If a shared instance already exists, clears internal caches and resets the shared instance to None so the new configuration will take effect on next access.

    Parameters:
        config (dict): Configuration options to merge into the shared instance configuration.

    Raises:
        AssertionError: If `config` is not a dict.
    """
    if not isinstance(config, dict):
        raise AssertionError()
    SharedInstance.config.update(config)
    # if one is already set, delete
    if SharedInstance.instance:
        clear_cache()
        SharedInstance.instance = None


def _build_hive(**config: Any) -> Any:
    """Internal helper to build a Hive instance while reusing shared transports."""
    from .hive import Hive

    hive = Hive(**config)
    stored_rpc = _shared_transport.get("rpc")
    configured_nodes = config.get("node", [])
    if isinstance(configured_nodes, str):
        configured_nodes = [configured_nodes]

    def _rpc_matches_config(rpc_obj: Any) -> bool:
        if not configured_nodes or rpc_obj is None:
            return True
        return getattr(rpc_obj, "url", None) in configured_nodes

    if stored_rpc and getattr(stored_rpc, "url", None) and _rpc_matches_config(stored_rpc):
        hive.rpc = stored_rpc
    else:
        rpc_obj = getattr(hive, "rpc", None)
        if rpc_obj is not None:
            current_url = getattr(rpc_obj, "url", None)
            if not current_url and hasattr(rpc_obj, "rpcconnect"):
                rpc_obj.rpcconnect()
        _shared_transport["rpc"] = getattr(hive, "rpc", None)
    return hive
