import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from nectar.blockchaininstance.core import BlockChainInstance
from nectarapi.exceptions import RPCClosed, WorkingNodeMissing
from nectarapi.graphenerpc import AsyncGrapheneRPC, GrapheneRPC
from nectarapi.node import Nodes
from nectarapi.pool import NodePoolManager


def test_graphene_rpc_close_releases_session_and_stops_pool_monitor():
    rpc = GrapheneRPC.__new__(GrapheneRPC)
    rpc._closed = False
    rpc.session = session = MagicMock()
    rpc._failover_session = session
    rpc.url = "https://api.hive.blog"
    pool_mgr = MagicMock()
    nodes = MagicMock()
    nodes.pool_manager = pool_mgr
    rpc.nodes = nodes

    rpc.close()

    session.close.assert_called_once_with()
    pool_mgr.close.assert_called_once_with()
    assert rpc.session is None
    assert rpc.url is None
    assert rpc.closed is True
    assert "_failover_session" not in rpc.__dict__


def test_graphene_rpc_close_is_hard_no_reconnect():
    rpc = GrapheneRPC.__new__(GrapheneRPC)
    rpc._closed = False
    rpc.session = MagicMock()
    rpc.nodes = MagicMock()
    rpc.nodes.pool_manager = MagicMock()
    rpc.nodes.working_nodes_count = 2
    rpc.url = "https://api.hive.blog"

    rpc.close()

    with pytest.raises(RPCClosed):
        rpc.rpcconnect()
    with pytest.raises(RPCClosed):
        rpc.next()
    with pytest.raises(RPCClosed):
        rpc.request_send(b"{}")
    with pytest.raises(RPCClosed):
        rpc.rpcexec({"jsonrpc": "2.0", "method": "condenser_api.get_dynamic_global_properties", "params": [], "id": 1})


def test_async_graphene_rpc_aclose_is_hard_close():
    """AsyncGrapheneRPC.aclose must hard-close (not only drop the session)."""
    rpc = AsyncGrapheneRPC.__new__(AsyncGrapheneRPC)
    rpc._closed = False
    rpc.url = "https://api.hive.blog"
    session = AsyncMock()
    rpc.session = session
    rpc._failover_session = session
    pool_mgr = MagicMock()
    nodes = MagicMock()
    nodes.pool_manager = pool_mgr
    rpc.nodes = nodes

    asyncio.run(rpc.aclose())

    assert rpc.closed is True
    assert rpc.session is None
    assert rpc.url is None
    pool_mgr.close.assert_called_once_with()
    session.aclose.assert_awaited_once()
    assert "_failover_session" not in rpc.__dict__

    with pytest.raises(RPCClosed):
        rpc.rpcconnect()
    with pytest.raises(RPCClosed):
        asyncio.run(
            rpc.rpcexec_async(
                {
                    "jsonrpc": "2.0",
                    "method": "condenser_api.get_dynamic_global_properties",
                    "params": [],
                    "id": 1,
                }
            )
        )


def test_graphene_rpc_close_is_idempotent():
    rpc = GrapheneRPC.__new__(GrapheneRPC)
    rpc._closed = False
    rpc.session = None
    rpc.nodes = MagicMock()
    rpc.nodes.pool_manager = MagicMock()

    rpc.close()
    rpc.close()
    assert rpc.closed is True


def test_blockchain_instance_close_releases_sync_and_async_resources():
    instance = BlockChainInstance.__new__(BlockChainInstance)
    rpc = MagicMock()
    client = MagicMock()
    instance.rpc = rpc
    instance.client = client
    async_client = AsyncMock()
    instance.async_client = async_client
    pool_manager = MagicMock()
    instance.pool_manager = pool_manager

    instance.close()

    rpc.close.assert_called_once_with()
    client.close.assert_called_once_with()
    asyncio.run(async_client.aclose())
    pool_manager.close.assert_called_once_with()
    assert instance.rpc is None
    assert instance.client is None
    assert instance.async_client is None
    assert instance.pool_manager is None


def test_blockchain_instance_aclose_releases_async_rpc_resources():
    instance = BlockChainInstance.__new__(BlockChainInstance)
    rpc = MagicMock()
    rpc.aclose = AsyncMock()
    client = MagicMock()
    async_client = AsyncMock()
    pool_manager = MagicMock()
    instance.rpc = rpc
    instance.client = client
    instance.async_client = async_client
    instance.pool_manager = pool_manager

    asyncio.run(instance.aclose())

    rpc.aclose.assert_awaited_once_with()
    client.close.assert_called_once_with()
    async_client.aclose.assert_awaited_once_with()
    pool_manager.close.assert_called_once_with()


def test_nodes_next_without_pool_manager_raises_clear_error():
    nodes = Nodes(["https://a.example", "https://b.example"], num_retries=1, num_retries_call=1)
    nodes.pool_manager = None
    with pytest.raises(WorkingNodeMissing, match="pool manager is not available"):
        next(nodes)


def test_default_monitor_interval_is_disabled():
    pm = NodePoolManager(["https://api.hive.blog", "https://api2.hive.blog"])
    assert pm.monitor_interval == 0.0
    assert pm._monitor_thread is None
    pm.close()


def test_explicit_monitor_interval_starts_thread():
    pm = NodePoolManager(
        ["https://api.hive.blog", "https://api2.hive.blog"],
        monitor_interval=30.0,
    )
    assert pm.monitor_interval == 30.0
    assert pm._monitor_thread is not None
    assert pm._monitor_thread.is_alive()
    pm.close()
    assert pm._monitor_thread is None or not pm._monitor_thread.is_alive()
