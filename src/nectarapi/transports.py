import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx2

from .pool import NodePoolManager, RPCNode

log = logging.getLogger(__name__)
DEFAULT_RATE_LIMIT_COOLDOWN = 30.0


def _retry_after_seconds(response: httpx2.Response) -> float:
    """Return the Retry-After delay, falling back to a short cooldown."""
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return DEFAULT_RATE_LIMIT_COOLDOWN
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_RATE_LIMIT_COOLDOWN


def _format_request_error(exc: BaseException) -> str:
    """Human-readable exception text (httpx errors often have empty str())."""
    text = str(exc).strip()
    name = type(exc).__name__
    if text:
        return f"{name}: {text}"
    # Common empty-message cases: timeouts, connect errors without detail
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and str(cause).strip():
        return f"{name}: {type(cause).__name__}: {str(cause).strip()}"
    return f"{name} (no error detail)"


def _pool_snapshot(pool_manager: NodePoolManager) -> str:
    """Short pool state for log lines after mark/failover."""
    nodes = list(pool_manager.nodes)
    healthy = [n.url for n in nodes if n.healthy]
    unhealthy = [n.url for n in nodes if not n.healthy]
    try:
        active = pool_manager.get_active_node().url
    except Exception:
        active = "?"
    return (
        f"active_now={active} "
        f"healthy={len(healthy)}/{len(nodes)} "
        f"unhealthy={unhealthy if unhealthy else '[]'}"
    )


def _log_node_failover(
    *,
    kind: str,
    failed_url: str,
    reason: str,
    attempt: int,
    max_attempts: int,
    pool_manager: NodePoolManager,
    next_node: RPCNode | None = None,
) -> None:
    """
    Log a clear failover event.

    ``kind``: e.g. 'http_status', 'request_error'
    ``attempt`` is 1-based for display (attempt just finished).
    """
    next_url = next_node.url if next_node is not None else pool_manager.get_active_node().url
    same = next_url == failed_url
    if same:
        outcome = (
            "next_active is the SAME node (pool may be all-failed / least-bad pick; "
            "background health probes can re-enable nodes later)"
        )
    else:
        outcome = f"failing over to {next_url}"

    log.warning(
        "RPC failover [%s] attempt %s/%s: marked %s unhealthy (%s); %s | %s",
        kind,
        attempt,
        max_attempts,
        failed_url,
        reason,
        outcome,
        _pool_snapshot(pool_manager),
    )


class FailoverSyncTransport(httpx2.BaseTransport):
    def __init__(self, pool_manager: NodePoolManager, **kwargs) -> None:
        self.pool_manager = pool_manager
        self.underlying_transport = httpx2.HTTPTransport(**kwargs)

    def close(self) -> None:
        self.underlying_transport.close()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        attempts = 0
        max_attempts = len(self.pool_manager.nodes)
        last_exc: BaseException | None = None
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
                # 429 rate-limits and 5xx are node-local: fail over immediately.
                # Without this, 429 is returned to GrapheneRPC which burns the
                # whole pool via least-bad retries on the same rate-limited node.
                if response.status_code == 429 or response.status_code >= 500:
                    failed_url = best_node.url
                    reason = f"HTTP {response.status_code}"
                    if response.status_code == 429:
                        retry_after = _retry_after_seconds(response)
                        response.close()
                        self.pool_manager.mark_node_rate_limited(best_node, retry_after)
                    else:
                        response.close()
                        self.pool_manager.mark_node_failed(best_node)
                    attempts += 1
                    _log_node_failover(
                        kind="http_status",
                        failed_url=failed_url,
                        reason=reason,
                        attempt=attempts,
                        max_attempts=max_attempts,
                        pool_manager=self.pool_manager,
                    )
                    continue
                return response
            except httpx2.RequestError as exc:
                failed_url = best_node.url
                reason = _format_request_error(exc)
                self.pool_manager.mark_node_failed(best_node)
                attempts += 1
                last_exc = exc
                _log_node_failover(
                    kind="request_error",
                    failed_url=failed_url,
                    reason=reason,
                    attempt=attempts,
                    max_attempts=max_attempts,
                    pool_manager=self.pool_manager,
                )

        log.error(
            "RPC failover exhausted: all %s pool nodes failed for this request | %s",
            max_attempts,
            _pool_snapshot(self.pool_manager),
        )
        if last_exc:
            raise last_exc
        raise httpx2.RequestError(
            f"All {max_attempts} nodes in the pool failed to respond.",
            request=request,
        )


class FailoverAsyncTransport(httpx2.AsyncBaseTransport):
    def __init__(self, pool_manager: NodePoolManager, **kwargs) -> None:
        self.pool_manager = pool_manager
        self.underlying_transport = httpx2.AsyncHTTPTransport(**kwargs)

    async def aclose(self) -> None:
        await self.underlying_transport.aclose()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        attempts = 0
        max_attempts = len(self.pool_manager.nodes)
        last_exc: BaseException | None = None
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
                if response.status_code == 429 or response.status_code >= 500:
                    failed_url = best_node.url
                    reason = f"HTTP {response.status_code}"
                    if response.status_code == 429:
                        retry_after = _retry_after_seconds(response)
                        await response.aclose()
                        self.pool_manager.mark_node_rate_limited(best_node, retry_after)
                    else:
                        await response.aclose()
                        await self.pool_manager.mark_node_failed_async(best_node)
                    attempts += 1
                    _log_node_failover(
                        kind="http_status",
                        failed_url=failed_url,
                        reason=reason,
                        attempt=attempts,
                        max_attempts=max_attempts,
                        pool_manager=self.pool_manager,
                    )
                    continue
                return response
            except httpx2.RequestError as exc:
                failed_url = best_node.url
                reason = _format_request_error(exc)
                await self.pool_manager.mark_node_failed_async(best_node)
                attempts += 1
                last_exc = exc
                _log_node_failover(
                    kind="request_error",
                    failed_url=failed_url,
                    reason=reason,
                    attempt=attempts,
                    max_attempts=max_attempts,
                    pool_manager=self.pool_manager,
                )

        log.error(
            "Async RPC failover exhausted: all %s pool nodes failed for this request | %s",
            max_attempts,
            _pool_snapshot(self.pool_manager),
        )
        if last_exc:
            raise last_exc
        raise httpx2.RequestError(
            f"All {max_attempts} nodes in the pool failed to respond.",
            request=request,
        )
