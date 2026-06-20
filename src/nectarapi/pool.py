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

        import sys

        if monitor_interval is None:
            if "pytest" in sys.modules or "unittest" in sys.modules:
                self.monitor_interval = 0.0
            else:
                self.monitor_interval = 30.0
        else:
            self.monitor_interval = monitor_interval

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

    async def mark_node_failed_async(self, node: RPCNode) -> None:
        self.mark_node_failed(node)

    def _recalculate_best_node(self) -> None:
        with self.lock:
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
