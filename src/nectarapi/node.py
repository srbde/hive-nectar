import logging
import re
import time
from typing import Any, List, Optional, Union

from .exceptions import CallRetriesReached, NumRetriesReached

log = logging.getLogger(__name__)


class Node:
    def __init__(self, url: str) -> None:
        self.url = url
        self.error_cnt = 0
        self.error_cnt_call = 0

    def __repr__(self) -> str:
        return self.url


class Nodes(list[Node]):
    """Stores Node URLs and error counts"""

    def __init__(
        self,
        urls: Union[str, "Nodes", List[Any], tuple, set, None],
        num_retries: int,
        num_retries_call: int,
    ) -> None:
        self.set_node_urls(urls)
        self.num_retries = num_retries
        self.num_retries_call = num_retries_call

    def set_node_urls(self, urls: Union[str, "Nodes", List[Any], tuple, set, None]) -> None:
        if isinstance(urls, str):
            url_list = re.split(r",|;", urls)
            if url_list is None:
                url_list = [urls]
        elif isinstance(urls, Nodes):
            url_list = [urls[i].url for i in range(len(urls))]
        elif isinstance(urls, (list, tuple, set)):
            url_list = urls
        elif urls is not None:
            url_list = [urls]
        else:
            url_list = []
        super().__init__([Node(x) for x in url_list])
        self.current_node_index = -1
        self.freeze_current_node = False

    def __iter__(self) -> "Nodes":  # type: ignore[override]
        # Iterator with rotation handled by __next__
        return self

    def __next__(self) -> str:
        if self.freeze_current_node:
            return self.url
        if len(self) == 0:
            raise StopIteration
        for _ in range(len(self)):
            self.current_node_index += 1
            if self.current_node_index >= len(self) or self.current_node_index < 0:
                self.current_node_index = 0
            node = self[self.current_node_index]
            if self.num_retries < 0 or node.error_cnt <= self.num_retries:
                return node.url
        raise StopIteration

    next = __next__  # Python 2

    def export_working_nodes(self) -> List[str]:
        nodes_list = []
        for i in range(len(self)):
            if self.num_retries < 0 or self[i].error_cnt <= self.num_retries:
                nodes_list.append(self[i].url)
        return nodes_list

    def get_nodes(self) -> List[str]:
        """Return the list of configured node URLs (including those currently marked errored)."""
        return [self[i].url for i in range(len(self))]

    def __repr__(self) -> str:
        nodes_list = self.export_working_nodes()
        return str(nodes_list)

    @property
    def working_nodes_count(self) -> int:
        n = 0
        if self.freeze_current_node:
            i = self.current_node_index
            if self.current_node_index < 0:
                i = 0
            if self.num_retries < 0 or self[i].error_cnt <= self.num_retries:
                n += 1
            return n
        for i in range(len(self)):
            if self.num_retries < 0 or self[i].error_cnt <= self.num_retries:
                n += 1
        return n

    @property
    def url(self) -> str:
        if self.node is None:
            return ""
        return self.node.url

    @property
    def node(self) -> Node:
        if self.current_node_index < 0:
            return self[0]
        return self[self.current_node_index]

    @property
    def error_cnt(self) -> int:
        if self.node is None:
            return 0
        return self.node.error_cnt

    @property
    def error_cnt_call(self) -> int:
        if self.node is None:
            return 0
        return self.node.error_cnt_call

    @property
    def num_retries_call_reached(self) -> bool:
        return self.error_cnt_call >= self.num_retries_call

    def disable_node(self) -> None:
        """Disable current node"""
        if self.node is not None and self.num_retries_call >= 0:
            self.node.error_cnt_call = self.num_retries_call

    def increase_error_cnt(self) -> None:
        """Increase node error count for current node"""
        if self.node is not None:
            self.node.error_cnt += 1

    def increase_error_cnt_call(self) -> None:
        """Increase call error count for current node"""
        if self.node is not None:
            self.node.error_cnt_call += 1

    def reset_error_cnt_call(self) -> None:
        """Set call error count for current node to zero"""
        if self.node is not None:
            self.node.error_cnt_call = 0

    def reset_error_cnt(self) -> None:
        """Set node error count for current node to zero"""
        if self.node is not None:
            self.node.error_cnt = 0

    def sleep_and_check_retries(
        self,
        errorMsg: Optional[str] = None,
        sleep: bool = True,
        call_retry: bool = False,
        showMsg: bool = True,
    ) -> None:
        """
        Sleep and check if num_retries is reached. If num_retries is reached, raise NumRetriesReached or CallRetriesReached.
        Only logs first and last retry messages if showMsg is True.


        :param errorMsg: Optional error message to log
        :param sleep: Whether to sleep before retrying
        :param call_retry: Whether this is a retry for a call error (as opposed to a connection error)
        :param showMsg: Whether to show retry messages only on the first and last retry


        """
        first_or_last_retry = (
            self.error_cnt_call == 1 or self.error_cnt_call == self.num_retries_call
        )

        if errorMsg:
            log.warning("Error: {}".format(errorMsg))
        if call_retry:
            cnt = self.error_cnt_call
            if self.num_retries_call >= 0 and self.error_cnt_call > self.num_retries_call:
                raise CallRetriesReached()
        else:
            cnt = self.error_cnt
            if self.num_retries >= 0 and self.error_cnt > self.num_retries:
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
