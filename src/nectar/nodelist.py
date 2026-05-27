import json
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx2

log = logging.getLogger(__name__)

# Static fallback nodes in case beacon is unavailable
STATIC_NODES = [
    "https://api.hive.blog",
    "https://api.openhive.network",
    "https://api.syncad.com",
    "https://api.deathwing.me",
    "https://api.c0ff33a.uk",
    "https://hive-api.3speak.tv",
    "https://hiveapi.actifit.io",
    "https://rpc.mahdiyari.info",
    "https://techcoderx.com",
    "https://anyx.io",
]

# PeakD beacon API URL is https://beacon.peakd.com/api/nodes
# devapi.v4v.app is a faster mirror with much less constrained rate limits
# maintained by the v4v.app team

BEACON_URLS = ["https://beacon.v4v.app", "https://beacon.peakd.com/api/nodes"]
REQUEST_TIMEOUT = 10  # seconds
CACHE_DURATION = 300  # 5 minutes cache

# Global cache for node data
_cached_nodes: Optional[List[Dict[str, Any]]] = None
_cache_timestamp: float = 0
_cache_lock = threading.Lock()

CACHE_FILE = Path(tempfile.gettempdir()) / "nectar_nodes_cache.json"


def extract_nodes_from_raw(raw: Any, source: str) -> Optional[List[Dict[str, Any]]]:
    if isinstance(raw, list):
        nodes: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                nodes.append(item)
            else:
                log.warning(f"Skipping non-dict entry from {source}: %r", item)
        return nodes
    else:
        log.warning(f"{source} returned unexpected data type: %s", type(raw))
        return None


def fetch_beacon_nodes() -> Optional[List[Dict[str, Any]]]:
    """Fetch node list from PeakD beacon API with caching.

    Returns:
        List of node dictionaries from beacon API, or None if fetch fails
    """
    global _cached_nodes, _cache_timestamp

    current_time = time.time()

    # Return cached data if still valid (memory)
    with _cache_lock:
        if _cached_nodes is not None and current_time - _cache_timestamp < CACHE_DURATION:
            log.debug("Using cached beacon nodes (memory)")
            return _cached_nodes

    # Try to load from disk cache if memory cache is empty or expired
    if CACHE_FILE.exists():
        try:
            mtime = CACHE_FILE.stat().st_mtime
            if current_time - mtime < CACHE_DURATION:
                with open(CACHE_FILE, "r") as f:
                    raw = json.load(f)
                # Ensure cached data is a list of dicts and coerce to the expected type
                nodes = extract_nodes_from_raw(raw, "disk cache")
                if nodes is not None:
                    with _cache_lock:
                        _cached_nodes = nodes
                        _cache_timestamp = mtime
                    log.debug("Using cached beacon nodes (disk)")
                    return nodes
        except (IOError, json.JSONDecodeError) as e:
            log.warning(f"Failed to read disk cache: {e}")

    log.debug("Fetching fresh nodes from beacon API")

    for beacon_url in BEACON_URLS:
        try:
            log.debug(f"Fetching fresh nodes from beacon API: {beacon_url}")
            response = httpx2.get(
                beacon_url,
                headers={"Accept": "*/*"},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.text
            raw = json.loads(data)

            # Validate that the beacon returned a list of node dicts
            nodes = extract_nodes_from_raw(raw, "beacon API")
            if nodes is not None:
                # Cache the successful result
                _cached_nodes = nodes
                _cache_timestamp = current_time
                # Write to disk cache
                try:
                    with open(CACHE_FILE, "w") as f:
                        json.dump(nodes, f)
                except (IOError, OSError) as e:
                    log.warning(f"Failed to write to disk cache: {e}")
                return nodes
            # else: try next beacon URL
        except (httpx2.RequestError, httpx2.HTTPStatusError, json.JSONDecodeError, ValueError) as e:
            log.warning(f"Failed to fetch nodes from beacon API {beacon_url}: {e}")

        except Exception as e:
            log.error(f"Unexpected error fetching nodes from beacon API {beacon_url}: {e}")

    # Return cached data even if expired, as fallback
    if _cached_nodes is not None:
        log.info("Using expired cached nodes as fallback")
        return _cached_nodes
    return None


def clear_beacon_cache() -> None:
    """Clear the cached beacon node data.

    This forces the next NodeList() instantiation or update_nodes() call
    to fetch fresh data from the beacon API.
    """
    global _cached_nodes, _cache_timestamp
    with _cache_lock:
        _cached_nodes = None
        _cache_timestamp = 0

    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except OSError as e:
            log.warning(f"Failed to remove disk cache: {e}")

    log.debug("Beacon node cache cleared")


class NodeList(list):
    """Simplified Hive node list using PeakD beacon API.

    Fetches real-time node information from PeakD beacon API with static fallback.

    .. code-block:: python

        from nectar.nodelist import NodeList
        n = NodeList()
        nodes_urls = n.get_nodes()
    """

    def __init__(self):
        """Initialize NodeList with nodes from beacon API or static fallback."""
        super().__init__()
        self._refresh_nodes()

    def _refresh_nodes(self) -> None:
        """Refresh node list from beacon API or use static fallback."""
        beacon_nodes = fetch_beacon_nodes()

        if beacon_nodes:
            # Convert beacon format to our internal format
            nodes = []
            for node in beacon_nodes:
                # Only include nodes with decent performance (score > 0)
                if node.get("score", 0) > 0:
                    nodes.append(
                        {
                            "url": node["endpoint"],
                            "version": node.get("version", "unknown"),
                            "type": "appbase",  # All beacon nodes are appbase
                            "owner": node.get("name", "unknown"),
                            "hive": True,
                            "score": node.get("score", 0),
                        }
                    )

            # Sort by score (highest first)
            nodes.sort(key=lambda x: x["score"], reverse=True)
            super().__init__(nodes)
            log.info(f"Loaded {len(nodes)} nodes from PeakD beacon API")
        else:
            # Use static fallback
            nodes = [
                {
                    "url": url,
                    "version": "unknown",
                    "type": "appbase",
                    "owner": "static",
                    "hive": True,
                    "score": 50,
                }
                for url in STATIC_NODES
            ]
            super().__init__(nodes)
            log.warning(f"Using static fallback nodes ({len(nodes)} nodes)")

    def get_nodes(
        self,
        hive: bool = True,
        dev: bool = False,
        testnet: bool = False,
        testnetdev: bool = False,
        wss: bool = True,
        https: bool = True,
        not_working: bool = False,
        normal: bool = False,
        appbase: bool = True,
    ) -> List[str]:
        """Return a list of node URLs filtered and sorted by score.

        Args:
            hive: Filter for Hive nodes only (default: True)
            dev: Include dev nodes (not applicable with beacon)
            testnet: Include testnet nodes (not applicable with beacon)
            testnetdev: Include testnet dev nodes (not applicable with beacon)
            wss: Include WebSocket nodes (default: True)
            https: Include HTTPS nodes (default: True)
            not_working: Include nodes with negative scores (default: False)
            normal: Include normal nodes (deprecated, default: False)
            appbase: Include appbase nodes (default: True)

        Returns:
            List of node URLs sorted by score (highest first)
        """
        filtered_nodes = []

        # Determine allowed types based on flags (OR logic)
        allowed_types = set()
        if appbase:
            allowed_types.add("appbase")
        if normal:
            allowed_types.add("normal")
        if dev:
            allowed_types.add("appbase-dev")
        if testnet:
            allowed_types.add("testnet")
        if testnetdev:
            allowed_types.add("testnet-dev")

        for node in self:
            # Filter by score
            if node["score"] < 0 and not not_working:
                continue

            # Filter by Hive
            if hive and not node["hive"]:
                continue

            # Filter by protocol
            if not https and node["url"].startswith("https"):
                continue
            if not wss and node["url"].startswith("wss"):
                continue

            # Filter by type (OR logic)
            if allowed_types and node["type"] not in allowed_types:
                continue

            filtered_nodes.append(node)

        # Sort by score (highest first) and return URLs
        filtered_nodes.sort(key=lambda x: x["score"], reverse=True)
        return [node["url"] for node in filtered_nodes]

    def get_hive_nodes(
        self,
        testnet: bool = False,
        not_working: bool = False,
        wss: bool = True,
        https: bool = True,
    ) -> List[str]:
        """Return a list of Hive node URLs filtered and ordered by score.

        Args:
            testnet: Include testnet nodes (default: False)
            not_working: Include nodes with negative scores (default: False)
            wss: Include WebSocket nodes (default: True)
            https: Include HTTPS nodes (default: True)

        Returns:
            List of Hive node URLs sorted by score
        """
        return self.get_nodes(
            hive=True,
            testnet=testnet,
            not_working=not_working,
            wss=wss,
            https=https,
            appbase=True,
            normal=False,
        )

    def get_testnet(self, testnet: bool = True, testnetdev: bool = False) -> List[str]:
        """Return a list of testnet node URLs (currently unavailable).

        Note: The PeakD beacon API does not provide testnet nodes. This method
        currently returns an empty list. Use mainnet nodes for testing or
        manually configure testnet endpoints.

        Args:
            testnet: Include testnet nodes (default: True)
            testnetdev: Include testnet dev nodes (default: False)

        Returns:
            List of testnet node URLs
        """
        log.warning("Testnet nodes are not available from beacon API")
        return self.get_nodes(
            normal=False,
            appbase=False,
            testnet=testnet,
            testnetdev=testnetdev,
        )

    def update_nodes(self, weights: Any = None, blockchain_instance: Any = None) -> None:
        """Refresh nodes from beacon API.

        This method replaces the complex update logic with a simple refresh
        from the beacon API and clears the cache to force fresh data.

        Args:
            weights: Ignored (beacon provides its own scoring)
            blockchain_instance: Ignored (beacon API is independent)
        """
        clear_beacon_cache()
        self._refresh_nodes()

    def update(self, node_list: List[str]) -> None:
        """Update node list (not implemented with beacon API).

        Args:
            node_list: List of node URLs (ignored with beacon API)
        """
        log.info("NodeList.update() is deprecated with beacon API - using beacon data instead")
        self._refresh_nodes()

    def get_node_answer_time(
        self, node_list: Optional[List[str]] = None, verbose: bool = False
    ) -> List[Dict[str, float]]:
        """Get node response times (deprecated with beacon API).

        The beacon API already provides performance scoring, so this method
        returns the beacon scores instead of measuring response times.

        Args:
            node_list: List of node URLs to check (ignored, uses all nodes)
            verbose: Log node information (default: False)

        Returns:
            List of dictionaries with 'url' and 'delay_ms' keys
        """
        log.info("get_node_answer_time() using beacon scores instead of measuring response times")

        result = []
        for node in self:
            # Convert beacon score (0-100) to a fake delay for compatibility
            # Higher score = lower delay
            fake_delay_ms = (100 - node["score"]) * 10  # Simple conversion
            result.append({"url": node["url"], "delay_ms": fake_delay_ms})

            if verbose:
                log.info(
                    f"node {node['url']} beacon score: {node['score']}, fake delay: {fake_delay_ms:.2f}ms"
                )

        return sorted(result, key=lambda x: x["delay_ms"])
