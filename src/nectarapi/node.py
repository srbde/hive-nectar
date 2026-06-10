import logging
import re
import time
from typing import Any, Union

from .exceptions import CallRetriesReached, NumRetriesReached

log = logging.getLogger(__name__)


class Node:
    def __init__(self, url: str) -> None:
        self.url = url
        self.error_cnt = 0
        self.error_cnt_call = 0

    def __repr__(self) -> str:
        return self.url


class Nodes(list):
    """Stores Node URLs and error counts, backed by a NodePoolManager for smart failover."""

    def __init__(
        self,
        urls: Union[str, "Nodes", list[Any], tuple, set, None],
        num_retries: int,
        num_retries_call: int,
    ) -> None:
        super().__init__()
        self.num_retries = num_retries
        self.num_retries_call = num_retries_call
        self.current_node_index = -1
        self.freeze_current_node = False
        self.pool_manager = None  # Set before __next__ is ever called
        self.set_node_urls(urls)

    def set_node_urls(self, urls: Union[str, "Nodes", list[Any], tuple, set, None]) -> None:
        if isinstance(urls, str):
            url_list = re.split(r",|;", urls)
            if not url_list:
                url_list = [urls]
        elif isinstance(urls, Nodes):
            # Use list slice to avoid calling our custom __iter__/__next__
            url_list = [urls[i].url for i in range(len(urls))]
        elif isinstance(urls, (list, tuple, set)):
            url_list = list(urls)
        elif urls is not None:
            url_list = [urls]
        else:
            url_list = []

        self.clear()
        self.extend([Node(x) for x in url_list])
        self.current_node_index = -1
        self.freeze_current_node = False

        from .pool import NodePoolManager

        # Build url list directly from the list elements without using our custom iterator
        raw_urls = [self[i].url for i in range(len(self))]
        self.pool_manager = NodePoolManager(raw_urls)

    def __iter__(self) -> "Nodes":  # type: ignore[override]
        return self

    def __next__(self) -> str:
        if self.freeze_current_node:
            return self.url
        if len(self) == 0:
            raise StopIteration

        best_node = self.pool_manager.get_active_node()
        # Update current_node_index for compatibility
        for idx in range(len(self)):
            if self[idx].url == best_node.url:
                self.current_node_index = idx
                break
        return best_node.url

    next = __next__

    def export_working_nodes(self) -> list[str]:
        if self.pool_manager is None:
            return []
        return [n.url for n in self.pool_manager.nodes if n.healthy]

    def get_nodes(self) -> list[str]:
        if self.pool_manager is None:
            return [self[i].url for i in range(len(self))]
        return [n.url for n in self.pool_manager.nodes]

    def __repr__(self) -> str:
        return str(self.export_working_nodes())

    @property
    def working_nodes_count(self) -> int:
        if self.pool_manager is None:
            return len(self)
        if self.freeze_current_node:
            i = self.current_node_index if self.current_node_index >= 0 else 0
            if i < len(self.pool_manager.nodes) and self.pool_manager.nodes[i].healthy:
                return 1
            return 0
        return sum(1 for n in self.pool_manager.nodes if n.healthy)

    @property
    def url(self) -> str:
        if len(self) == 0:
            return ""
        if self.pool_manager is None:
            i = max(self.current_node_index, 0)
            return self[i].url if i < len(self) else ""
        return self.pool_manager.get_active_node().url

    @property
    def node(self) -> Node:
        if self.pool_manager is None:
            i = max(self.current_node_index, 0)
            return self[i] if self else Node("")
        active_url = self.pool_manager.get_active_node().url
        for i in range(len(self)):
            if self[i].url == active_url:
                return self[i]
        return self[0] if self else Node("")

    @property
    def error_cnt(self) -> int:
        # Read from the Node list element directly — this counter is never
        # reset by the pool manager, so it reliably tracks lifetime failures
        # for the GrapheneRPC num_retries budget.
        n = self.node
        return n.error_cnt

    @property
    def error_cnt_call(self) -> int:
        return self.node.error_cnt_call

    @property
    def num_retries_call_reached(self) -> bool:
        return self.error_cnt_call >= self.num_retries_call

    def disable_node(self) -> None:
        """Disable current node by marking it failed."""
        n = self.node
        n.error_cnt = self.num_retries + 1  # guarantee it looks exhausted
        if self.pool_manager:
            self.pool_manager.mark_node_failed(self.pool_manager.get_active_node())

    def increase_error_cnt(self) -> None:
        """Increase node error count for current node."""
        # Increment the persistent counter on the Node list element first
        n = self.node
        n.error_cnt += 1
        # Then propagate the failure into the pool for routing decisions
        if self.pool_manager:
            self.pool_manager.mark_node_failed(self.pool_manager.get_active_node())

    def increase_error_cnt_call(self) -> None:
        """Increase call error count for current node."""
        if self.pool_manager:
            active_node = self.pool_manager.get_active_node()
            active_node.error_cnt_call += 1
            if active_node.error_cnt_call >= self.num_retries_call:
                self.pool_manager.mark_node_failed(active_node)

    def reset_error_cnt_call(self) -> None:
        """Set call error count for current node to zero."""
        if self.pool_manager:
            active_node = self.pool_manager.get_active_node()
            active_node.error_cnt_call = 0

    def reset_error_cnt(self) -> None:
        """Set node error count for current node to zero."""
        if self.pool_manager:
            active_node = self.pool_manager.get_active_node()
            active_node.healthy = True
            active_node.penalty = 0.0
            active_node.error_cnt = 0

    def sleep_and_check_retries(
        self,
        errorMsg: str | None = None,
        sleep: bool = True,
        call_retry: bool = False,
        showMsg: bool = True,
    ) -> None:
        """Sleep and check if num_retries is reached. Raises if budget exhausted."""
        first_or_last_retry = (
            self.error_cnt_call == 1 or self.error_cnt_call == self.num_retries_call
        )

        if errorMsg:
            log.warning(f"Error: {errorMsg}")

        if call_retry:
            cnt = self.error_cnt_call
            if self.num_retries_call >= 0 and cnt > self.num_retries_call:
                raise CallRetriesReached()
        else:
            cnt = self.error_cnt  # persistent per-node counter, never reset by pool
            if self.num_retries >= 0 and cnt > self.num_retries:
                raise NumRetriesReached()

        if showMsg and first_or_last_retry:
            if call_retry:
                log.warning(
                    "Retry RPC Call on node: %s (%d/%d)" % (self.url, cnt, self.num_retries_call)
                )
            else:
                log.warning(
                    "Lost connection or internal error on node: %s (%d/%d)"
                    % (self.url, cnt, self.num_retries)
                )

        if not sleep:
            return
        if cnt < 1:
            sleeptime = 0
        elif cnt < 10:
            sleeptime = (cnt - 1) * 1.5 + 0.5
        else:
            sleeptime = 10
        if sleeptime:
            log.warning("Retrying in %d seconds" % sleeptime)
            time.sleep(sleeptime)
