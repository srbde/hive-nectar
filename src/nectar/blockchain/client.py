import hashlib
import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from typing import Any, cast

from nectar.block import Block, BlockHeader
from nectar.blockchain.concurrency import FUTURES_MODULE, Pool
from nectar.exceptions import (
    BatchedCallsNotSupported,
    BlockDoesNotExistsException,
    BlockWaitTimeExceeded,
    OfflineHasNoRPCException,
)
from nectar.instance import shared_blockchain_instance
from nectar.utils import addTzInfo
from nectarapi.exceptions import UnknownTransaction

log = logging.getLogger(__name__)

if FUTURES_MODULE == "futures":
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
    except ImportError:
        pass


class Blockchain:
    """This class allows to access the blockchain and read data
    from it

    :param Blockchain blockchain_instance: Blockchain instance
    :param str mode: (default) Irreversible block (``irreversible``) or
        actual head block (``head``)
    :param int max_block_wait_repetition: maximum wait repetition for next block
        where each repetition is block_interval long (default is 3)

    This class let's you deal with blockchain related data and methods.
    Read blockchain related data:

    .. testsetup::

        from nectar.blockchain import Blockchain
        chain = Blockchain()

    Read current block and blockchain info

    .. testcode::

        print(chain.get_current_block())
        print(chain.blockchain.info())

    Monitor for new blocks. When ``stop`` is not set, monitoring will never stop.

    .. testcode::

        blocks = []
        current_num = chain.get_current_block_num()
        for block in chain.blocks(start=current_num - 99, stop=current_num):
            blocks.append(block)
        len(blocks)

    .. testoutput::

        100

    or each operation individually:

    .. testcode::

        ops = []
        current_num = chain.get_current_block_num()
        for operation in chain.ops(start=current_num - 99, stop=current_num):
            ops.append(operation)

    """

    def __init__(
        self,
        blockchain_instance: Any = None,
        mode: str = "irreversible",
        max_block_wait_repetition: int | None = None,
        data_refresh_time_seconds: int = 900,
        **kwargs,
    ) -> None:
        """
        Initialize the Blockchain helper.

        Sets the underlying blockchain connection (uses shared instance if none provided), configures mode to map to the underlying RPC key ("last_irreversible_block_num" or "head_block_number"), sets max_block_wait_repetition (default 3), and reads the chain's block interval.

        Parameters:
            mode (str): "irreversible" to operate against the last irreversible block, or "head" to operate against the chain head.
            max_block_wait_repetition (int, optional): Number of times to retry waiting for a block before giving up; defaults to 3.

        Raises:
            ValueError: If `mode` is not "irreversible" or "head".
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if mode == "irreversible":
            self.mode = "last_irreversible_block_num"
        elif mode == "head":
            self.mode = "head_block_number"
        else:
            raise ValueError("invalid value for 'mode'!")
        if max_block_wait_repetition:
            self.max_block_wait_repetition = max_block_wait_repetition
        else:
            self.max_block_wait_repetition = 3
        self.block_interval = self.blockchain.get_block_interval()

    def is_irreversible_mode(self) -> bool:
        return self.mode == "last_irreversible_block_num"

    def is_transaction_existing(self, transaction_id: str) -> bool:
        """Returns true, if the transaction_id is valid"""
        try:
            self.get_transaction(transaction_id)
            return True
        except UnknownTransaction:
            return False

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Returns a transaction from the blockchain

        :param str transaction_id: transaction_id
        """
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        ret = self.blockchain.rpc.get_transaction({"id": transaction_id})
        return ret

    def get_transaction_hex(self, transaction: dict[str, Any]) -> str:
        """Returns a hexdump of the serialized binary form of a transaction.

        :param dict transaction: transaction
        """
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        ret = self.blockchain.rpc.get_transaction_hex({"trx": transaction})["hex"]
        return ret

    def get_current_block_num(self) -> int:
        """This call returns the current block number

        .. note:: The block number returned depends on the ``mode`` used
                  when instantiating from this class.
        """
        props = self.blockchain.get_dynamic_global_properties(False)
        if props is None:
            raise ValueError("Could not receive dynamic_global_properties!")
        if self.mode not in props:
            raise ValueError(self.mode + " is not in " + str(props))
        return int(props.get(self.mode))

    def get_current_block(self, only_ops: bool = False, only_virtual_ops: bool = False) -> Block:
        """This call returns the current block

        :param bool only_ops: Returns block with operations only, when set to True (default: False)
        :param bool only_virtual_ops: Includes only virtual operations (default: False)

        .. note:: The block number returned depends on the ``mode`` used
                  when instantiating from this class.
        """
        return Block(
            self.get_current_block_num(),
            only_ops=only_ops,
            only_virtual_ops=only_virtual_ops,
            blockchain_instance=self.blockchain,
        )

    def get_estimated_block_num(
        self,
        date: datetime | date | datetime_time | None,
        estimateForwards: bool = False,
        accurate: bool = True,
    ) -> int:
        """This call estimates the block number based on a given date

        :param datetime date: block time for which a block number is estimated

        .. note:: The block number returned depends on the ``mode`` used
                  when instantiating from this class.

        .. code-block:: python

            >>> from nectar.blockchain import Blockchain
            >>> from datetime import datetime
            >>> blockchain = Blockchain()
            >>> block_num = blockchain.get_estimated_block_num(datetime(2019, 6, 18, 5 ,8, 27))
            >>> block_num == 33898182
            True

        """
        last_block = self.get_current_block()
        date = addTzInfo(date)
        # Ensure we have a datetime object for arithmetic operations
        if date is None or not isinstance(date, datetime):
            raise ValueError("date must be a datetime object after addTzInfo processing")
        block_number: int = 1
        if estimateForwards:
            block_offset = 10
            first_block = BlockHeader(block_offset, blockchain_instance=self.blockchain)
            time_diff = date - first_block.time()
            block_number = math.floor(
                time_diff.total_seconds() / self.block_interval + block_offset
            )
        else:
            time_diff = last_block.time() - date
            if last_block.identifier is not None:
                block_number = math.floor(
                    last_block.identifier - time_diff.total_seconds() / self.block_interval
                )
        if block_number < 1:
            block_number = 1

        if accurate:
            if last_block.identifier is not None and block_number > int(last_block.identifier):
                block_number = int(last_block.identifier)
            block_time_diff = timedelta(seconds=10)

            last_block_time_diff_seconds = 10
            second_last_block_time_diff_seconds = 10

            while (
                block_time_diff.total_seconds() > self.block_interval
                or block_time_diff.total_seconds() < -self.block_interval
            ):
                block = BlockHeader(int(block_number), blockchain_instance=self.blockchain)
                second_last_block_time_diff_seconds = last_block_time_diff_seconds
                last_block_time_diff_seconds = block_time_diff.total_seconds()
                block_time_diff = date - block.time()
                if (
                    second_last_block_time_diff_seconds == block_time_diff.total_seconds()
                    and second_last_block_time_diff_seconds < 10
                ):
                    return int(block_number)
                delta: int = int(block_time_diff.total_seconds() // self.block_interval)
                if delta == 0 and block_time_diff.total_seconds() < 0:
                    delta = -1
                elif delta == 0 and block_time_diff.total_seconds() > 0:
                    delta = 1
                block_number += delta
                if block_number < 1:
                    break
                if last_block.identifier is not None and block_number > int(last_block.identifier):
                    break

        return int(block_number)

    def block_time(self, block_num: int) -> datetime:
        """Returns a datetime of the block with the given block
        number.

        :param int block_num: Block number
        """
        return Block(block_num, blockchain_instance=self.blockchain).time()

    def block_timestamp(self, block_num: int) -> int:
        """Returns the timestamp of the block with the given block
        number as integer.

        :param int block_num: Block number
        """
        block_time = Block(block_num, blockchain_instance=self.blockchain).time()
        return int(time.mktime(block_time.timetuple()))

    @property
    def participation_rate(self) -> float:
        """Returns the witness participation rate in a range from 0 to 1"""
        return (
            bin(
                int(
                    self.blockchain.get_dynamic_global_properties(use_stored_data=False)[
                        "recent_slots_filled"
                    ]
                )
            ).count("1")
            / 128
        )

    def blocks(
        self,
        start: int | None = None,
        stop: int | None = None,
        max_batch_size: int | None = None,
        threading: bool = False,
        thread_num: int = 8,
        only_ops: bool = False,
        only_virtual_ops: bool = False,
    ) -> Any:
        """
        Yield Block objects from `start` up to `stop` (or the chain head).

        This generator retrieves blocks from the connected blockchain instance and yields them as Block objects. It supports three retrieval modes:
        - Single-threaded sequential fetching (default).
        - Threaded parallel fetching across multiple blockchain instances when `threading=True`.
        - Batched RPC calls for appbase-compatible nodes when `max_batch_size` is set (cannot be combined with `threading`).

        Parameters:
            start (int, optional): First block number to fetch. If omitted, defaults to the current block.
            stop (int, optional): Last block number to fetch. If omitted, the generator follows the chain head indefinitely.
            max_batch_size (int, optional): Use batched RPC calls (appbase only). Cannot be used with `threading`.
            threading (bool): If True, fetch blocks in parallel using `thread_num` workers.
            thread_num (int): Number of worker threads to use when `threading=True`.
            only_ops (bool): If True, blocks will contain only regular operations (no block metadata).
                Mutually exclusive with `only_virtual_ops=True`.
            only_virtual_ops (bool): If True, yield only virtual operations.

        Yields:
            Block: A Block object for each fetched block (may contain only ops or only virtual ops depending on flags).

        Exceptions:
            OfflineHasNoRPCException: Raised if batched mode is requested while offline (no RPC available).
            BatchedCallsNotSupported: Raised if the node does not support batched calls when `max_batch_size` is used.

        Notes:
            - For instant (non-irreversible) confirmations, initialize the Blockchain with mode="head"; otherwise this method will wait for irreversible blocks.
            - `max_batch_size` requires appbase-compatible RPC; threaded mode creates additional blockchain instances for parallel RPC calls.
        """
        # Let's find out how often blocks are generated!
        current_block = self.get_current_block()
        current_block_num = current_block.block_num
        if not start and current_block_num is not None:
            start = current_block_num
        head_block_reached = False
        pool: Any = None
        if threading and FUTURES_MODULE is not None:
            pool = ThreadPoolExecutor(max_workers=thread_num)
        elif threading:
            pool = Pool(thread_num, batch_mode=True)
        if threading:
            blockchain_instance = [self.blockchain]
            nodelist = self.blockchain.rpc.nodes.export_working_nodes()
            for i in range(thread_num - 1):
                blockchain_instance.append(
                    self.blockchain.__class__(
                        node=nodelist,
                        num_retries=self.blockchain.rpc.num_retries,
                        num_retries_call=self.blockchain.rpc.num_retries_call,
                        timeout=self.blockchain.rpc.timeout,
                    )
                )
        # We are going to loop indefinitely
        latest_block = 0
        while True:
            if stop:
                head_block = stop
            else:
                current_block_num = self.get_current_block_num()
                head_block = current_block_num
            if threading and not head_block_reached and start is not None:
                if pool is None:
                    raise RuntimeError("Threading is enabled but no pool was initialized")
                pool_any = cast(Any, pool)
                latest_block = start - 1
                result_block_nums = []
                for blocknum in range(start, head_block + 1, thread_num):
                    # futures = []
                    i = 0
                    if FUTURES_MODULE is not None:
                        futures = []
                    block_num_list = []
                    # freeze = self.blockchain.rpc.nodes.freeze_current_node
                    num_retries = self.blockchain.rpc.nodes.num_retries
                    # self.blockchain.rpc.nodes.freeze_current_node = True
                    self.blockchain.rpc.nodes.num_retries = thread_num
                    error_cnt = self.blockchain.rpc.nodes.node.error_cnt
                    while i < thread_num and blocknum + i <= head_block:
                        block_num_list.append(blocknum + i)
                        results = []
                        if FUTURES_MODULE is not None:
                            futures.append(
                                pool_any.submit(
                                    Block,
                                    blocknum + i,
                                    only_ops=only_ops,
                                    only_virtual_ops=only_virtual_ops,
                                    blockchain_instance=blockchain_instance[i],
                                )
                            )
                        else:
                            pool_any.enqueue(
                                Block,
                                blocknum + i,
                                only_ops=only_ops,
                                only_virtual_ops=only_virtual_ops,
                                blockchain_instance=blockchain_instance[i],
                            )
                        i += 1
                    if FUTURES_MODULE is not None:
                        try:
                            results = [r.result() for r in as_completed(futures)]
                        except Exception as e:
                            log.error(str(e))
                    else:
                        pool_any.run(True)
                        pool_any.join()
                        for result in pool_any.results():
                            results.append(result)
                        pool_any.abort()
                    self.blockchain.rpc.nodes.num_retries = num_retries
                    # self.blockchain.rpc.nodes.freeze_current_node = freeze
                    new_error_cnt = self.blockchain.rpc.nodes.node.error_cnt
                    self.blockchain.rpc.nodes.node.error_cnt = error_cnt
                    if new_error_cnt > error_cnt:
                        self.blockchain.rpc.nodes.node.error_cnt += 1
                    #    self.blockchain.rpc.next()

                    checked_results = []
                    for b in results:
                        if b.block_num is not None and int(b.block_num) not in result_block_nums:
                            b["id"] = b.block_num
                            b.identifier = b.block_num
                            checked_results.append(b)
                            result_block_nums.append(int(b.block_num))

                    missing_block_num = list(set(block_num_list).difference(set(result_block_nums)))
                    while len(missing_block_num) > 0:
                        for blocknum in missing_block_num:
                            try:
                                block = Block(
                                    blocknum,
                                    only_ops=only_ops,
                                    only_virtual_ops=only_virtual_ops,
                                    blockchain_instance=self.blockchain,
                                )
                                block_num_value = block.block_num
                                if block_num_value is None:
                                    log.debug(
                                        "Skipping missing block with no block_num: %s", blocknum
                                    )
                                    continue
                                block["id"] = block_num_value
                                block.identifier = block_num_value
                                checked_results.append(block)
                                result_block_nums.append(int(block_num_value))
                            except Exception as e:
                                log.error(str(e))
                        missing_block_num = list(
                            set(block_num_list).difference(set(result_block_nums))
                        )
                    from operator import itemgetter

                    blocks = sorted(checked_results, key=itemgetter("id"))
                    for b in blocks:
                        block_num_value = b.block_num
                        if block_num_value is None:
                            log.debug("Skipping yielded block with no block_num: %s", b)
                            continue
                        if latest_block < int(block_num_value):
                            latest_block = int(block_num_value)
                        yield b

                if latest_block <= head_block:
                    for blocknum in range(latest_block + 1, head_block + 1):
                        if blocknum not in result_block_nums:
                            block = Block(
                                blocknum,
                                only_ops=only_ops,
                                only_virtual_ops=only_virtual_ops,
                                blockchain_instance=self.blockchain,
                            )
                            result_block_nums.append(blocknum)
                            yield block
            elif (
                max_batch_size is not None
                and start is not None
                and (head_block - start) >= max_batch_size
                and not head_block_reached
            ):
                if not self.blockchain.is_connected():
                    raise OfflineHasNoRPCException("No RPC available in offline mode!")
                self.blockchain.rpc.set_next_node_on_empty_reply(False)
                if start is not None:
                    latest_block = start - 1
                    for blocknumblock in range(start, head_block + 1, max_batch_size):
                        batch_count = min(max_batch_size, head_block - blocknumblock + 1)
                        if only_virtual_ops:
                            batch_blocks = []
                            for blocknum in range(blocknumblock, blocknumblock + batch_count):
                                ops_resp = self.blockchain.rpc.get_ops_in_block(
                                    {"block_num": blocknum, "only_virtual": True},
                                )
                                ops = (
                                    ops_resp.get("ops", [])
                                    if isinstance(ops_resp, dict)
                                    else ops_resp
                                )
                                if not ops:
                                    continue
                                block_dict = {
                                    "block": blocknum,
                                    "timestamp": ops[0]["timestamp"],
                                    "operations": ops,
                                }
                                batch_blocks.append(block_dict)
                        else:
                            resp = self.blockchain.rpc.get_block_range(
                                {"starting_block_num": blocknumblock, "count": batch_count},
                            )
                            batch_blocks = (
                                resp.get("blocks", []) if isinstance(resp, dict) else resp
                            )

                        if not batch_blocks:
                            raise BatchedCallsNotSupported(
                                f"{self.blockchain.rpc.url} Doesn't support batched calls"
                            )

                        for raw_block in batch_blocks:
                            block_obj = Block(
                                raw_block,
                                only_ops=only_ops,
                                only_virtual_ops=only_virtual_ops,
                                blockchain_instance=self.blockchain,
                            )
                            block_num_value = block_obj.block_num
                            if block_num_value is None:
                                log.debug("Skipping block with missing block_num: %s", raw_block)
                                continue
                            block_obj["id"] = block_num_value
                            block_obj.identifier = block_num_value
                            if latest_block < int(block_num_value):
                                latest_block = int(block_num_value)
                            yield block_obj
            else:
                # Blocks from start until head block
                if start is not None:
                    for blocknum in range(start, head_block + 1):
                        # Get full block
                        block = self.wait_for_and_get_block(
                            blocknum,
                            only_ops=only_ops,
                            only_virtual_ops=only_virtual_ops,
                            block_number_check_cnt=5,
                            last_current_block_num=current_block_num,
                        )
                        yield block
            # Set new start
            start = head_block + 1
            head_block_reached = True

            if stop and start > stop:
                return

            # Sleep for one block
            time.sleep(self.block_interval)

    def wait_for_and_get_block(
        self,
        block_number: int,
        blocks_waiting_for: int | None = None,
        only_ops: bool = False,
        only_virtual_ops: bool = False,
        block_number_check_cnt: int = -1,
        last_current_block_num: int | None = None,
    ) -> Block | None:
        """Get the desired block from the chain, if the current head block is smaller (for both head and irreversible)
        then we wait, but a maxmimum of blocks_waiting_for * max_block_wait_repetition time before failure.

        :param int block_number: desired block number
        :param int blocks_waiting_for: difference between block_number and current head and defines
            how many blocks we are willing to wait, positive int (default: None)
        :param bool only_ops: Returns blocks with operations only, when set to True (default: False)
        :param bool only_virtual_ops: Includes only virtual operations (default: False)
        :param int block_number_check_cnt: limit the number of retries when greater than -1
        :param int last_current_block_num: can be used to reduce the number of get_current_block_num() api calls

        """
        if last_current_block_num is None:
            last_current_block_num = self.get_current_block_num()
        elif last_current_block_num - block_number < 50:
            last_current_block_num = self.get_current_block_num()

        if not blocks_waiting_for:
            blocks_waiting_for = max(1, block_number - last_current_block_num)

            repetition = 0
            # can't return the block before the chain has reached it (support future block_num)
            while last_current_block_num < block_number:
                repetition += 1
                time.sleep(self.block_interval)
                if last_current_block_num - block_number < 50:
                    last_current_block_num = self.get_current_block_num()
                if repetition > blocks_waiting_for * self.max_block_wait_repetition:
                    raise BlockWaitTimeExceeded(
                        "Already waited %d s"
                        % (
                            blocks_waiting_for
                            * self.max_block_wait_repetition
                            * self.block_interval
                        )
                    )
        # block has to be returned properly
        repetition = 0
        cnt = 0
        block = None
        while (
            block is None or block.block_num is None or int(block.block_num) != block_number
        ) and (block_number_check_cnt < 0 or cnt < block_number_check_cnt):
            try:
                block = Block(
                    block_number,
                    only_ops=only_ops,
                    only_virtual_ops=only_virtual_ops,
                    blockchain_instance=self.blockchain,
                )
                cnt += 1
            except BlockDoesNotExistsException:
                block = None
                if repetition > blocks_waiting_for * self.max_block_wait_repetition:
                    raise BlockWaitTimeExceeded(
                        "Already waited %d s"
                        % (
                            blocks_waiting_for
                            * self.max_block_wait_repetition
                            * self.block_interval
                        )
                    )
                repetition += 1
                time.sleep(self.block_interval)

        return block

    def ops(
        self,
        start: int | None = None,
        stop: int | None = None,
        only_virtual_ops: bool = False,
        **kwargs: Any,
    ) -> None:
        """Blockchain.ops() is deprecated. Please use Blockchain.stream() instead."""
        import warnings

        warnings.warn(
            "Blockchain.ops() is deprecated. Please use Blockchain.stream() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError("Use Blockchain.stream() instead.")

    def ops_statistics(
        self,
        start: int,
        stop: int | None = None,
        add_to_ops_stat: dict[str, int] | None = None,
        with_virtual_ops: bool = True,
        verbose: bool = False,
    ) -> dict[str, int] | None:
        """Generates statistics for all operations (including virtual operations) starting from
        ``start``.

        :param int start: Starting block
        :param int stop: Stop at this block, if set to None, the current_block_num is taken
        :param dict add_to_ops_stat: if set, the result is added to add_to_ops_stat
        :param bool verbose: if True, the current block number and timestamp is printed

        This call returns a dict with all possible operations and their occurrence.

        """
        if add_to_ops_stat is None:
            import nectarbase.operationids

            ops_stat = nectarbase.operationids.operations.copy()
            for key in ops_stat:
                ops_stat[key] = 0
        else:
            ops_stat = add_to_ops_stat.copy()
        current_block = self.get_current_block_num()
        if start > current_block:
            return
        if stop is None:
            stop = current_block
        for block in self.blocks(start=start, stop=stop, only_ops=False, only_virtual_ops=False):
            if verbose:
                print(block["identifier"] + " " + block["timestamp"])
            ops_stat = block.ops_statistics(add_to_ops_stat=ops_stat)
        if with_virtual_ops:
            for block in self.blocks(start=start, stop=stop, only_ops=True, only_virtual_ops=True):
                if verbose:
                    print(block["identifier"] + " " + block["timestamp"])
                ops_stat = block.ops_statistics(add_to_ops_stat=ops_stat)
        return ops_stat

    def stream(
        self, opNames: list[str] | None = None, raw_ops: bool = False, *args: Any, **kwargs: Any
    ) -> Any:
        """
        Yield blockchain operations filtered by type, normalizing several node event formats into a consistent output.

        Parameters:
            opNames (list): Operation type names to filter for (e.g., ['transfer', 'comment']). If empty, all operations are yielded.
            raw_ops (bool): If True, yield raw operation tuples with minimal metadata; if False (default), yield a flattened dict with operation fields and metadata.
            *args, **kwargs: Passed through to self.blocks(...) (e.g., start, stop, max_batch_size, threading, thread_num, only_ops, only_virtual_ops).

        Yields:
            dict: When raw_ops is False, yields a dictionary with at least:
                - 'type': operation name
                - operation fields (e.g., 'from', 'to', 'amount', ...)
                - '_id': deterministic operation hash
                - 'timestamp': block timestamp
                - 'block_num': block number
                - 'trx_num': transaction index within the block
                - 'trx_id': transaction id

            dict: When raw_ops is True, yields a compact dictionary:
                - 'block_num': block number
                - 'trx_num': transaction index
                - 'op': [op_type, op_payload]
                - 'timestamp': block timestamp

        Notes:
            - The method accepts the same control parameters as blocks(...) via kwargs. The block stream determines timestamps and block-related metadata.
            - Operation events from different node formats (lists, legacy dicts, appbase-style dicts) are normalized by this method before yielding.
        """
        if opNames is None:
            opNames = []
        for block in self.blocks(**kwargs):
            block_num_val = (
                getattr(block, "block_num", None)
                or block.get("block")
                or block.get("block_num")
                or block.get("id")
                or block.get("identifier", 0)
            )
            timestamp_val = block.get("timestamp")

            if "transactions" in block:
                transactions = block["transactions"]
                tx_ids = block.get("transaction_ids", [])
                for trx_nr, trx in enumerate(transactions):
                    if "operations" not in trx:
                        continue
                    for event in trx["operations"]:
                        trx_id = tx_ids[trx_nr] if trx_nr < len(tx_ids) else ""
                        op_type = ""
                        op = {}
                        if isinstance(event, list):
                            op_type, op = event
                            op_hash_input = event
                        elif isinstance(event, dict) and "type" in event and "value" in event:
                            op_type = event["type"]
                            if op_type.endswith("_operation"):
                                op_type = op_type[:-10]
                            op = event["value"]
                            op_hash_input = event
                        elif (
                            "op" in event
                            and isinstance(event["op"], dict)
                            and "type" in event["op"]
                            and "value" in event["op"]
                        ):
                            op_type = event["op"]["type"]
                            if op_type.endswith("_operation"):
                                op_type = op_type[:-10]
                            op = event["op"]["value"]
                            trx_id = event.get("trx_id", trx_id)
                            op_hash_input = event["op"]
                        elif "op" in event and isinstance(event["op"], list):
                            op_type, op = event["op"]
                            trx_id = event.get("trx_id", trx_id)
                            op_hash_input = event["op"]
                            timestamp_val = event.get("timestamp", timestamp_val)
                        else:
                            continue

                        if (not opNames or op_type in opNames) and block_num_val:
                            if raw_ops:
                                yield {
                                    "block_num": block_num_val,
                                    "trx_num": trx_nr,
                                    "op": [op_type, op],
                                    "timestamp": timestamp_val,
                                }
                            else:
                                updated_op = {"type": op_type}
                                updated_op.update(op.copy())
                                updated_op.update(
                                    {
                                        "_id": self.hash_op(op_hash_input),
                                        "timestamp": timestamp_val,
                                        "block_num": block_num_val,
                                        "trx_num": trx_nr,
                                        "trx_id": trx_id,
                                    }
                                )
                                yield updated_op
            elif "operations" in block:
                for event in block["operations"]:
                    trx_nr = event.get("trx_in_block", 0)
                    trx_id = event.get("trx_id", "")
                    op_type = ""
                    op = {}
                    op_hash_input = None
                    if "op" in event and isinstance(event["op"], list):
                        op_type, op = event["op"]
                        op_hash_input = event["op"]
                    elif (
                        "op" in event
                        and isinstance(event["op"], dict)
                        and "type" in event["op"]
                        and "value" in event["op"]
                    ):
                        op_type = event["op"]["type"]
                        if op_type.endswith("_operation"):
                            op_type = op_type[:-10]
                        op = event["op"]["value"]
                        op_hash_input = event["op"]
                    else:
                        continue
                    timestamp_val = event.get("timestamp", timestamp_val)
                    block_num_event = event.get("block", block_num_val)
                    if (not opNames or op_type in opNames) and block_num_event:
                        if raw_ops:
                            yield {
                                "block_num": block_num_event,
                                "trx_num": trx_nr,
                                "op": [op_type, op],
                                "timestamp": timestamp_val,
                            }
                        else:
                            updated_op = {"type": op_type}
                            updated_op.update(op.copy())
                            updated_op.update(
                                {
                                    "_id": self.hash_op(op_hash_input),
                                    "timestamp": timestamp_val,
                                    "block_num": block_num_event,
                                    "trx_num": trx_nr,
                                    "trx_id": trx_id,
                                }
                            )
                            yield updated_op

    def awaitTxConfirmation(
        self, transaction: dict[str, Any], limit: int = 10
    ) -> dict[str, Any] | None:
        """Returns the transaction as seen by the blockchain after being
        included into a block

        :param dict transaction: transaction to wait for
        :param int limit: (optional) number of blocks to wait for the transaction (default: 10)

        .. note:: If you want instant confirmation, you need to instantiate
                  class:`nectar.blockchain.Blockchain` with
                  ``mode="head"``, otherwise, the call will wait until
                  confirmed in an irreversible block.

        .. note:: This method returns once the blockchain has included a
                  transaction with the **same signature**. Even though the
                  signature is not usually used to identify a transaction,
                  it still cannot be forfeited and is derived from the
                  transaction contented and thus identifies a transaction
                  uniquely.
        """
        counter = 0
        for block in self.blocks():
            counter += 1
            for tx in block["transactions"]:
                if sorted(tx["signatures"]) == sorted(transaction["signatures"]):
                    return tx
            if counter > limit:
                raise Exception("The operation has not been added after %d blocks!" % (limit))

    @staticmethod
    def hash_op(event: dict[str, Any] | list[Any]) -> str:
        """This method generates a hash of blockchain operation."""
        if isinstance(event, dict) and "type" in event and "value" in event:
            op_type = event["type"]
            if len(op_type) > 10 and op_type[len(op_type) - 10 :] == "_operation":
                op_type = op_type[:-10]
            op = event["value"]
            event = [op_type, op]
        data = json.dumps(event, sort_keys=True)
        return hashlib.sha1(bytes(data, "utf-8")).hexdigest()

    def get_all_accounts(
        self,
        start: str = "",
        stop: str = "",
        steps: int | float = 1e3,
        limit: int = -1,
        **kwargs: Any,
    ) -> Any:
        """Yields account names between start and stop.

        :param str start: Start at this account name
        :param str stop: Stop at this account name
        :param int steps: Obtain ``steps`` ret with a single call from RPC
        """
        cnt = 1
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        if start == "":
            lastname = None
        else:
            lastname = start
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        while True:
            ret = self.blockchain.rpc.list_accounts(
                {"start": lastname, "limit": steps, "order": "by_name"}
            )["accounts"]
            for account in ret:
                if isinstance(account, dict):
                    account_name = account["name"]
                else:
                    account_name = account
                if account_name != lastname:
                    yield account_name
                    cnt += 1
                    if account_name == stop or (limit > 0 and cnt > limit):
                        return
            if lastname == account_name:
                return
            lastname = account_name
            if len(ret) < steps:
                return

    def get_account_count(self) -> int:
        """Returns the number of accounts"""
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        ret = self.blockchain.rpc.get_account_count()
        return ret

    def get_account_reputations(
        self,
        start: str = "",
        stop: str = "",
        steps: int | float = 1e3,
        limit: int = -1,
        **kwargs: Any,
    ) -> Any:
        """Yields account reputation between start and stop.

        :param str start: Start at this account name
        :param str stop: Stop at this account name
        :param int steps: Obtain ``steps`` ret with a single call from RPC
        """
        cnt = 1
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        if start == "":
            lastname = None
        else:
            lastname = start
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        batch_limit = min(int(steps), 1000)
        first_batch = True
        while True:
            resp = self.blockchain.rpc.list_accounts(
                {"start": lastname, "limit": batch_limit, "order": "by_name"}
            )
            accounts = resp.get("accounts", []) if isinstance(resp, dict) else resp or []
            for account in accounts:
                account_name = account["name"]
                reputation = int(account.get("reputation", 0))
                if first_batch or account_name != lastname:
                    yield {"account": account_name, "reputation": reputation}
                    cnt += 1
                    if account_name == stop or (limit > 0 and cnt > limit):
                        return
            if not accounts:
                return
            lastname = accounts[-1]["name"]
            first_batch = False
            if len(accounts) < batch_limit or (stop and lastname == stop):
                return

    def get_similar_account_names(self, name: str, limit: int = 5) -> list[str] | None:
        """
        Return a list of accounts with names similar to the given name.

        Performs an RPC call to fetch accounts starting at `name`. If the underlying node uses the
        appbase API this returns the raw `accounts` list from the `list_accounts` response (list of
        account objects/dicts). If using the legacy API this returns the list of account names
        returned by `lookup_accounts`. If the local blockchain connection is offline, returns None.

        Parameters:
            name (str): Prefix or starting account name to search for.
            limit (int): Maximum number of accounts to return.

        Returns:
            list or None: A list of account names or account objects (depending on RPC), or None if offline.
        """
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        account = self.blockchain.rpc.list_accounts(
            {"start": name, "limit": limit, "order": "by_name"}
        )
        if bool(account):
            return account["accounts"]

    def find_rc_accounts(
        self, name: str | list[str]
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """
        Return resource credit (RC) parameters for one or more accounts.

        If given a single account name (str), returns the RC parameters for that account as a dict.
        If given a list of account names, returns a list of RC-parameter dicts in the same order.
        Returns None when the underlying blockchain RPC is not connected or if the RPC returns no data.

        Parameters:
            name (str | list): An account name or a list of account names.

        Returns:
            dict | list | None: RC parameters for the account(s), or None if offline or no result.
        """
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if isinstance(name, list):
            account = self.blockchain.rpc.find_rc_accounts({"accounts": name})
            if bool(account):
                return account["rc_accounts"]
        else:
            account = self.blockchain.rpc.find_rc_accounts({"accounts": [name]})
            if bool(account):
                return account["rc_accounts"][0]

    def list_change_recovery_account_requests(
        self, start: str | list[str] = "", limit: int = 1000, order: str = "by_account"
    ) -> list[dict[str, Any]] | None:
        """
        Return pending change_recovery_account requests from the blockchain.

        If the local blockchain connection is offline, returns None.

        Parameters:
            start (str or list): Starting point for the listing.
                - For order="by_account": an account name (string).
                - For order="by_effective_date": a two-item list [effective_on, account_to_recover]
                  e.g. ['2018-12-18T01:46:24', 'bott'].
            limit (int): Maximum number of results to return (default and max: 1000).
            order (str): Index to iterate: "by_account" (default) or "by_effective_date".

        Returns:
            list or None: A list of change_recovery_account request entries, or None if offline.
        """
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        requests = self.blockchain.rpc.list_change_recovery_account_requests(
            {"start": start, "limit": limit, "order": order}
        )
        if bool(requests):
            return requests["requests"]

    def find_change_recovery_account_requests(
        self, accounts: str | list[str]
    ) -> list[dict[str, Any]] | None:
        """
        Find pending change_recovery_account requests for one or more accounts.

        Accepts a single account name or a list of account names and queries the connected node for pending
        change_recovery_account requests. Returns the list of matching request entries, or None if the
        local blockchain instance is not connected or the RPC returned no data.

        Parameters:
            accounts (str | list): Account name or list of account names to search for.

        Returns:
            list | None: List of change_recovery_account request objects for the given account(s), or
            None if offline or no requests were returned.
        """
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if isinstance(accounts, str):
            accounts = [accounts]
        requests = self.blockchain.rpc.find_change_recovery_account_requests({"accounts": accounts})
        if bool(requests):
            return requests["requests"]
