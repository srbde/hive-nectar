import asyncio
from unittest.mock import AsyncMock, MagicMock

from nectar.blockchaininstance.core import BlockChainInstance
from nectarapi.graphenerpc import GrapheneRPC


def test_graphene_rpc_close_releases_only_per_instance_session():
    rpc = GrapheneRPC.__new__(GrapheneRPC)
    rpc.session = session = MagicMock()
    rpc._failover_session = session

    rpc.close()

    session.close.assert_called_once_with()
    assert rpc.session is None
    assert "_failover_session" not in rpc.__dict__


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
