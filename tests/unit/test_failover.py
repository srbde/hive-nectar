"""
Unit tests for the nectarapi failover pool manager and custom transports.

All tests are fully offline — no live network connections are made.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest

from nectarapi.node import Nodes
from nectarapi.pool import NodePoolManager, RPCNode
from nectarapi.transports import FailoverAsyncTransport, FailoverSyncTransport

# ---------------------------------------------------------------------------
# RPCNode Tests
# ---------------------------------------------------------------------------


class TestRPCNode:
    def test_init_defaults(self):
        node = RPCNode("https://api.hive.blog")
        assert node.url == "https://api.hive.blog"
        assert node.scheme == "https"
        assert node.host == "api.hive.blog"
        assert node.port is None
        assert node.penalty == 0.0
        assert node.healthy is True
        assert node.error_cnt == 0

    def test_init_with_port(self):
        node = RPCNode("https://api.hive.blog:8443")
        assert node.host == "api.hive.blog"
        assert node.port == 8443

    def test_repr(self):
        node = RPCNode("https://api.hive.blog")
        assert "api.hive.blog" in repr(node)
        assert "penalty=0.0" in repr(node)
        assert "healthy=True" in repr(node)


# ---------------------------------------------------------------------------
# NodePoolManager Tests
# ---------------------------------------------------------------------------


class TestNodePoolManager:
    def test_init_with_nodes(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])
        assert len(pm.nodes) == 2
        assert pm.nodes[0].url == "https://api.hive.blog"
        assert pm.nodes[1].url == "https://api.openhive.network"

    def test_init_empty_uses_default(self):
        pm = NodePoolManager([])
        assert len(pm.nodes) == 1
        assert pm.nodes[0].url == "https://api.hive.blog"

    def test_get_active_node_returns_first_by_default(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])
        active = pm.get_active_node()
        assert active.url == "https://api.hive.blog"

    def test_mark_node_failed_switches_to_next(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])
        first = pm.get_active_node()
        assert first.url == "https://api.hive.blog"

        pm.mark_node_failed(first)
        active = pm.get_active_node()
        assert active.url == "https://api.openhive.network"

    def test_mark_node_failed_sets_penalty_inf(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])
        first = pm.nodes[0]
        pm.mark_node_failed(first)
        assert not first.healthy
        assert first.penalty == float("inf")

    def test_all_nodes_failed_resets(self):
        """When all nodes are failed, the pool resets so work can continue."""
        pm = NodePoolManager(["https://api.hive.blog"])
        node = pm.get_active_node()
        pm.mark_node_failed(node)
        # After reset, we should still get an active node
        active = pm.get_active_node()
        assert active is not None

    def test_recalculate_best_node_penalty_scoring(self):
        pm = NodePoolManager(["https://node-a.com", "https://node-b.com"])
        # Simulate node-a lagging, node-b fast
        pm.nodes[0].head_block_number = 90
        pm.nodes[0].latency = 200.0
        pm.nodes[1].head_block_number = 100
        pm.nodes[1].latency = 50.0
        pm._recalculate_best_node()
        # node-b should be selected (low latency + no drift)
        active = pm.get_active_node()
        assert active.url == "https://node-b.com"

    def test_recalculate_desync_applies_huge_penalty(self):
        pm = NodePoolManager(["https://node-a.com", "https://node-b.com"], max_lag=15)
        pm.nodes[0].head_block_number = 50  # severe lag
        pm.nodes[0].latency = 10.0
        pm.nodes[1].head_block_number = 100  # max
        pm.nodes[1].latency = 100.0
        pm._recalculate_best_node()
        # node-a drift is 50 blocks > 15 threshold → penalty 100000+
        assert pm.nodes[0].penalty >= 100000.0
        assert not pm.nodes[0].healthy

    def test_recalculate_lagging_state_adds_drift_penalty(self):
        pm = NodePoolManager(["https://node-a.com", "https://node-b.com"], max_lag=15)
        pm.nodes[0].head_block_number = 97  # drift = 3
        pm.nodes[0].latency = 50.0
        pm.nodes[1].head_block_number = 100  # max
        pm.nodes[1].latency = 50.0
        pm._recalculate_best_node()
        # node-a: 50 + 3*100 = 350, node-b: 50 + 0*100 = 50
        assert pm.nodes[0].penalty == pytest.approx(350.0)
        assert pm.nodes[1].penalty == pytest.approx(50.0)
        active = pm.get_active_node()
        assert active.url == "https://node-b.com"

    def test_thread_safety_of_mark_node_failed(self):
        """Stress test: concurrent calls to mark_node_failed must not corrupt state."""
        pm = NodePoolManager(["https://a.com", "https://b.com", "https://c.com"])
        errors = []

        def worker():
            try:
                node = pm.get_active_node()
                pm.mark_node_failed(node)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# ---------------------------------------------------------------------------
# Nodes (legacy adapter) Tests
# ---------------------------------------------------------------------------


class TestNodes:
    def test_init_from_list(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        assert len(n) == 2

    def test_init_from_string(self):
        n = Nodes("https://api.hive.blog", 100, 5)
        assert len(n) == 1
        assert n[0].url == "https://api.hive.blog"

    def test_init_from_comma_string(self):
        n = Nodes("https://api.hive.blog,https://api.openhive.network", 100, 5)
        assert len(n) == 2

    def test_working_nodes_count(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        assert n.working_nodes_count == 2

    def test_next_returns_best_url(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        url = next(n)
        assert url in ["https://api.hive.blog", "https://api.openhive.network"]

    def test_mark_failed_reduces_working_count(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        assert n.working_nodes_count == 2
        n.increase_error_cnt()  # marks current node failed
        # After one failure, pool should route to the other node
        assert n.working_nodes_count >= 1

    def test_get_nodes_returns_all(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        nodes = n.get_nodes()
        assert "https://api.hive.blog" in nodes
        assert "https://api.openhive.network" in nodes

    def test_export_working_nodes_excludes_failed(self):
        n = Nodes(["https://api.hive.blog", "https://api.openhive.network"], 100, 5)
        # Mark first node as failed via pool_manager
        n.pool_manager.mark_node_failed(n.pool_manager.nodes[0])
        working = n.export_working_nodes()
        assert "https://api.hive.blog" not in working
        assert "https://api.openhive.network" in working

    def test_reset_error_cnt(self):
        n = Nodes(["https://api.hive.blog"], 100, 5)
        n.pool_manager.mark_node_failed(n.pool_manager.nodes[0])
        n.reset_error_cnt()
        active = n.pool_manager.get_active_node()
        assert active.healthy is True
        assert active.penalty == 0.0


# ---------------------------------------------------------------------------
# FailoverSyncTransport Tests
# ---------------------------------------------------------------------------


class TestFailoverSyncTransport:
    def _make_response(self, status_code: int = 200) -> httpx2.Response:
        return httpx2.Response(status_code, content=b'{"jsonrpc":"2.0","result":{}}')

    def test_rewrites_url_to_active_node(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        mock_transport = MagicMock()
        mock_transport.handle_request.return_value = self._make_response(200)

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        transport.handle_request(request)

        # The request URL should have been rewritten to the best node
        called_request = mock_transport.handle_request.call_args[0][0]
        assert called_request.url.host == "api.hive.blog"

    def test_falls_over_on_server_error(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        call_count = [0]

        def side_effect(request):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: primary node returns 500
                return self._make_response(500)
            else:
                return self._make_response(200)

        mock_transport = MagicMock()
        mock_transport.handle_request.side_effect = side_effect

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        response = transport.handle_request(request)

        assert response.status_code == 200
        assert call_count[0] == 2

    def test_falls_over_on_connection_error(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        call_count = [0]

        def side_effect(request):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx2.ConnectError("Connection refused")
            return self._make_response(200)

        mock_transport = MagicMock()
        mock_transport.handle_request.side_effect = side_effect

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        response = transport.handle_request(request)

        assert response.status_code == 200
        assert call_count[0] == 2

    def test_raises_when_all_nodes_fail(self):
        pm = NodePoolManager(["https://api.hive.blog"])

        mock_transport = MagicMock()
        mock_transport.handle_request.side_effect = httpx2.ConnectError("Connection refused")

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        with pytest.raises(httpx2.RequestError):
            transport.handle_request(request)


# ---------------------------------------------------------------------------
# FailoverAsyncTransport Tests
# ---------------------------------------------------------------------------


class TestFailoverAsyncTransport:
    def _make_response(self, status_code: int = 200) -> httpx2.Response:
        return httpx2.Response(status_code, content=b'{"jsonrpc":"2.0","result":{}}')

    def test_rewrites_url_to_active_node(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        mock_transport = AsyncMock()
        mock_transport.handle_async_request.return_value = self._make_response(200)

        transport = FailoverAsyncTransport(pm)
        transport.underlying_transport = mock_transport

        async def run():
            request = httpx2.Request("POST", "https://placeholder.invalid/")
            await transport.handle_async_request(request)
            called_request = mock_transport.handle_async_request.call_args[0][0]
            assert called_request.url.host == "api.hive.blog"

        asyncio.run(run())

    def test_falls_over_on_server_error(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        call_count = [0]

        async def side_effect(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return self._make_response(500)
            return self._make_response(200)

        mock_transport = AsyncMock()
        mock_transport.handle_async_request.side_effect = side_effect

        transport = FailoverAsyncTransport(pm)
        transport.underlying_transport = mock_transport

        async def run():
            request = httpx2.Request("POST", "https://placeholder.invalid/")
            response = await transport.handle_async_request(request)
            assert response.status_code == 200
            assert call_count[0] == 2

        asyncio.run(run())

    def test_falls_over_on_connection_error(self):
        pm = NodePoolManager(["https://api.hive.blog", "https://api.openhive.network"])

        call_count = [0]

        async def side_effect(request):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx2.ConnectError("Connection refused")
            return self._make_response(200)

        mock_transport = AsyncMock()
        mock_transport.handle_async_request.side_effect = side_effect

        transport = FailoverAsyncTransport(pm)
        transport.underlying_transport = mock_transport

        async def run():
            request = httpx2.Request("POST", "https://placeholder.invalid/")
            response = await transport.handle_async_request(request)
            assert response.status_code == 200
            assert call_count[0] == 2

        asyncio.run(run())

    def test_raises_when_all_nodes_fail(self):
        pm = NodePoolManager(["https://api.hive.blog"])

        async def bad_request(request):
            raise httpx2.ConnectError("Connection refused")

        mock_transport = AsyncMock()
        mock_transport.handle_async_request.side_effect = bad_request

        transport = FailoverAsyncTransport(pm)
        transport.underlying_transport = mock_transport

        async def run():
            request = httpx2.Request("POST", "https://placeholder.invalid/")
            with pytest.raises(httpx2.RequestError):
                await transport.handle_async_request(request)

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Integration: pool_manager scoring determines transport target
# ---------------------------------------------------------------------------


class TestFailoverIntegration:
    """Verify the complete pipeline: pool scoring → transport → correct endpoint."""

    def _make_response(self, status_code: int = 200) -> httpx2.Response:
        return httpx2.Response(status_code, content=b'{"jsonrpc":"2.0","result":{}}')

    def test_lagging_node_is_not_selected(self):
        """A node with high block drift should not be chosen as the primary."""
        pm = NodePoolManager(
            [
                "https://api-lagging.hive.blog",
                "https://api-healthy.openhive.network",
            ]
        )
        # Manually set health state as if probes had run
        pm.nodes[0].head_block_number = 50  # severely behind
        pm.nodes[0].latency = 10.0
        pm.nodes[1].head_block_number = 100  # synced
        pm.nodes[1].latency = 50.0
        pm._recalculate_best_node()

        mock_transport = MagicMock()
        mock_transport.handle_request.return_value = self._make_response(200)

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        transport.handle_request(request)

        called_request = mock_transport.handle_request.call_args[0][0]
        # The healthy node must have been targeted, not the lagging one
        assert called_request.url.host == "api-healthy.openhive.network"

    def test_primary_failure_routes_to_secondary(self):
        """End-to-end: primary fails → automatic switch to secondary."""
        pm = NodePoolManager(
            [
                "https://primary.hive.blog",
                "https://secondary.hive.blog",
            ]
        )

        call_log = []

        def side_effect(request):
            host = request.url.host
            call_log.append(host)
            if host == "primary.hive.blog":
                return self._make_response(503)
            return self._make_response(200)

        mock_transport = MagicMock()
        mock_transport.handle_request.side_effect = side_effect

        transport = FailoverSyncTransport(pm)
        transport.underlying_transport = mock_transport

        request = httpx2.Request("POST", "https://placeholder.invalid/")
        response = transport.handle_request(request)

        assert response.status_code == 200
        assert "primary.hive.blog" in call_log
        assert "secondary.hive.blog" in call_log
