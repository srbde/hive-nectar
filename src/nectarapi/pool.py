import asyncio
import logging
import threading
import time
from urllib.parse import urlparse

import httpx2

log = logging.getLogger(__name__)


class RPCNode:
    def __init__(self, url: str) -> None:
        self.url = url
        parsed = urlparse(url)
        self.scheme = parsed.scheme or "https"
        self.host = parsed.hostname or ""
        self.port = parsed.port
        self.penalty = 0.0
        self.healthy = True
        self.error_cnt = 0
        self.error_cnt_call = 0
        self.rate_limited_until = 0.0
        self.head_block_number = 0
        self.latency = 0.0

    def __repr__(self) -> str:
        return f"<RPCNode {self.url} penalty={self.penalty:.1f} healthy={self.healthy}>"


class NodePoolManager:
    def __init__(
        self, node_urls: list[str], max_lag: int = 15, monitor_interval: float | None = None
    ) -> None:
        if not node_urls:
            node_urls = ["https://api.hive.blog"]
        self.nodes = [RPCNode(url) for url in node_urls]
        self.max_lag = max_lag
        self.lock = threading.RLock()
        self._active_node = self.nodes[0]
        self._recalculate_best_node()

        # Default off: background NodePoolMonitor probes open sockets and keep
        # threads alive for the life of each multi-node client. Long-running
        # apps that construct many short-lived Hive/RPC instances leak FDs when
        # the default was 30s. Opt in with monitor_interval>0 (e.g. 30).
        if monitor_interval is None:
            self.monitor_interval = 0.0
        else:
            self.monitor_interval = float(monitor_interval)

        self._stop_event = threading.Event()
        self._monitor_thread = None
        if self.monitor_interval > 0:
            self.start_monitoring()

    def start_monitoring(self) -> None:
        with self.lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True, name="NodePoolMonitor"
            )
            self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        with self.lock:
            self._stop_event.set()
            monitor_thread = self._monitor_thread
        if monitor_thread is not None and monitor_thread is not threading.current_thread():
            monitor_thread.join()
        with self.lock:
            if self._monitor_thread is monitor_thread:
                self._monitor_thread = None

    def close(self) -> None:
        self.stop_monitoring()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.update_pool()
            except Exception as e:
                log.debug(f"Error in NodePoolManager background monitor: {e}")
            if self._stop_event.wait(self.monitor_interval):
                break

    def get_active_node(self) -> RPCNode:
        with self.lock:
            if any(
                node.rate_limited_until and node.rate_limited_until <= time.monotonic()
                for node in self.nodes
            ):
                self._recalculate_best_node()
            return self._active_node

    async def get_active_node_async(self) -> RPCNode:
        # Re-use synchronous getter as lock is a standard threading RLock (fast/non-blocking for access)
        return self.get_active_node()

    def mark_node_failed(self, node: RPCNode) -> None:
        with self.lock:
            node.healthy = False
            node.error_cnt += 1
            node.penalty = float("inf")
            self._recalculate_best_node()

    def mark_node_rate_limited(self, node: RPCNode, retry_after: float) -> None:
        """Temporarily remove a rate-limited node from active selection."""
        with self.lock:
            node.rate_limited_until = time.monotonic() + max(0.0, retry_after)
            node.healthy = False
            node.penalty = float("inf")
            self._recalculate_best_node()

    async def mark_node_failed_async(self, node: RPCNode) -> None:
        self.mark_node_failed(node)

    def _recalculate_best_node(self) -> None:
        with self.lock:
            now = time.monotonic()
            for node in self.nodes:
                if node.rate_limited_until and node.rate_limited_until <= now:
                    node.rate_limited_until = 0.0
                    node.healthy = True
                    node.penalty = 0.0

            # Recalculate block drift D relative to max block number observed
            max_block = max([n.head_block_number for n in self.nodes if n.healthy] or [0])
            for n in self.nodes:
                if not n.healthy:
                    n.penalty = float("inf")
                    continue
                drift = max(0, max_block - n.head_block_number)
                if drift > self.max_lag:
                    n.penalty = n.latency + 100000.0
                    n.healthy = False
                else:
                    n.penalty = n.latency + (drift * 100)
                    n.healthy = True

            # Sort by lowest penalty
            healthy_sorted = sorted([n for n in self.nodes if n.healthy], key=lambda x: x.penalty)
            if healthy_sorted:
                self._active_node = healthy_sorted[0]
            else:
                # All nodes are currently marked unhealthy.
                # Do NOT reset health flags here — the GrapheneRPC retry budget
                # (num_retries) must be allowed to expire naturally so that
                # NumRetriesReached is eventually raised.  Instead, pick the
                # node with the lowest (finite or inf) penalty so requests have
                # somewhere to go, and let the transport keep raising exceptions
                # which accumulate in the caller's error counter.
                log.warning(
                    "All nodes marked failed in pool; picking least-bad node for next attempt."
                )
                all_sorted = sorted(self.nodes, key=lambda x: x.penalty)
                self._active_node = all_sorted[0]

    def probe_node_health(self, client: httpx2.Client, node: RPCNode) -> None:
        start = time.monotonic()
        try:
            response = client.post(
                node.url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "condenser_api.get_dynamic_global_properties",
                    "params": [],
                },
                timeout=3.0,
            )
            latency = (time.monotonic() - start) * 1000
            node.latency = latency
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "head_block_number" in data["result"]:
                    node.head_block_number = int(data["result"]["head_block_number"])
                    node.healthy = True
                    node.error_cnt_call = 0
                    return
            raise ValueError("Invalid response format or status")
        except Exception as e:
            log.debug(f"Health probe failed for {node.url}: {e}")
            node.healthy = False
            node.penalty = float("inf")

    async def probe_node_health_async(self, client: httpx2.AsyncClient, node: RPCNode) -> None:
        start = time.monotonic()
        try:
            response = await client.post(
                node.url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "condenser_api.get_dynamic_global_properties",
                    "params": [],
                },
                timeout=3.0,
            )
            latency = (time.monotonic() - start) * 1000
            node.latency = latency
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "head_block_number" in data["result"]:
                    node.head_block_number = int(data["result"]["head_block_number"])
                    node.healthy = True
                    node.error_cnt_call = 0
                    return
            raise ValueError("Invalid response format or status")
        except Exception as e:
            log.debug(f"Async health probe failed for {node.url}: {e}")
            node.healthy = False
            node.penalty = float("inf")

    def update_pool(self) -> None:
        with httpx2.Client(timeout=3.0) as client:
            threads = []
            for node in self.nodes:
                t = threading.Thread(target=self.probe_node_health, args=(client, node))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        self._recalculate_best_node()

    async def update_pool_async(self) -> None:
        async with httpx2.AsyncClient(timeout=3.0) as client:
            tasks = [self.probe_node_health_async(client, node) for node in self.nodes]
            await asyncio.gather(*tasks, return_exceptions=True)
        self._recalculate_best_node()
