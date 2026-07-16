from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest

from nectarapi.graphenerpc import AsyncGrapheneRPC
from nectarapi.noderpc import AsyncNodeRPC


class TestAsyncRPC:
    @pytest.mark.anyio
    async def test_async_graphene_rpc_init_and_call(self):
        # Instantiate AsyncGrapheneRPC with mock endpoint
        rpc = AsyncGrapheneRPC(["https://api.hive.blog"], autoconnect=False)
        rpc.rpcconnect()

        # Mock the session's post call
        mock_response = MagicMock(spec=httpx2.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"head_block_number": 12345},
        }
        mock_response.text = '{"jsonrpc": "2.0", "id": 1, "result": {"head_block_number": 12345}}'

        rpc.session = AsyncMock(spec=httpx2.AsyncClient)
        rpc.session.post.return_value = mock_response

        # Perform the call via __getattr__
        res = await rpc.get_dynamic_global_properties()
        assert res == {"head_block_number": 12345}

        # Check call arguments
        rpc.session.post.assert_called_once()
        called_url = rpc.session.post.call_args[0][0]
        assert called_url == "https://api.hive.blog"

    @pytest.mark.anyio
    async def test_async_node_rpc_failover(self):
        # NodeRPC with multiple nodes to trigger FailoverAsyncTransport setup
        rpc = AsyncNodeRPC(
            ["https://node-a.com", "https://node-b.com"],
            autoconnect=False,
            num_retries=2,
            num_retries_call=1,
        )
        rpc.rpcconnect()

        # Mock session to raise connection error on first call, succeed on second
        mock_response = MagicMock(spec=httpx2.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "success",
        }
        mock_response.text = '{"jsonrpc": "2.0", "id": 1, "result": "success"}'

        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx2.ConnectError("Connection refused")
            return mock_response

        rpc.session = AsyncMock(spec=httpx2.AsyncClient)
        rpc.session.post.side_effect = mock_post

        res = await rpc.get_config()
        assert res == "success"
        assert call_count == 2
