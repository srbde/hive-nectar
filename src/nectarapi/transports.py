import logging

import httpx2

from .pool import NodePoolManager

log = logging.getLogger(__name__)


class FailoverSyncTransport(httpx2.BaseTransport):
    def __init__(self, pool_manager: NodePoolManager, **kwargs) -> None:
        self.pool_manager = pool_manager
        self.underlying_transport = httpx2.HTTPTransport(**kwargs)

    def close(self) -> None:
        self.underlying_transport.close()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        attempts = 0
        max_attempts = len(self.pool_manager.nodes)
        last_exc = None
        while attempts < max_attempts:
            best_node = self.pool_manager.get_active_node()
            new_url = request.url.copy_with(
                scheme=best_node.scheme, host=best_node.host, port=best_node.port
            )
            request.url = new_url
            if "host" in request.headers:
                request.headers["host"] = new_url.netloc.decode("ascii")

            try:
                response = self.underlying_transport.handle_request(request)
                if response.status_code >= 500:
                    log.warning(
                        f"Node {best_node.url} returned status {response.status_code}. "
                        "Marking as failed and retrying."
                    )
                    self.pool_manager.mark_node_failed(best_node)
                    attempts += 1
                    continue
                return response
            except httpx2.RequestError as exc:
                log.warning(
                    f"Request failed for node {best_node.url}: {exc}. "
                    "Marking as failed and retrying."
                )
                self.pool_manager.mark_node_failed(best_node)
                attempts += 1
                last_exc = exc

        if last_exc:
            raise last_exc
        else:
            raise httpx2.RequestError("All nodes in the pool failed to respond.", request=request)


class FailoverAsyncTransport(httpx2.AsyncBaseTransport):
    def __init__(self, pool_manager: NodePoolManager, **kwargs) -> None:
        self.pool_manager = pool_manager
        self.underlying_transport = httpx2.AsyncHTTPTransport(**kwargs)

    async def aclose(self) -> None:
        await self.underlying_transport.aclose()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        attempts = 0
        max_attempts = len(self.pool_manager.nodes)
        last_exc = None
        while attempts < max_attempts:
            best_node = await self.pool_manager.get_active_node_async()
            new_url = request.url.copy_with(
                scheme=best_node.scheme, host=best_node.host, port=best_node.port
            )
            request.url = new_url
            if "host" in request.headers:
                request.headers["host"] = new_url.netloc.decode("ascii")

            try:
                response = await self.underlying_transport.handle_async_request(request)
                if response.status_code >= 500:
                    log.warning(
                        f"Async Node {best_node.url} returned status {response.status_code}. "
                        "Marking as failed and retrying."
                    )
                    await self.pool_manager.mark_node_failed_async(best_node)
                    attempts += 1
                    continue
                return response
            except httpx2.RequestError as exc:
                log.warning(
                    f"Async request failed for node {best_node.url}: {exc}. "
                    "Marking as failed and retrying."
                )
                await self.pool_manager.mark_node_failed_async(best_node)
                attempts += 1
                last_exc = exc

        if last_exc:
            raise last_exc
        else:
            raise httpx2.RequestError("All nodes in the pool failed to respond.", request=request)
