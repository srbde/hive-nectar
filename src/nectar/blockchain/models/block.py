from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from nectar.blockchainobject import BlockchainObject
from nectar.exceptions import BlockDoesNotExistsException
from nectar.instance import shared_blockchain_instance
from nectar.utils import formatTimeString, parse_time


class Block(BlockchainObject):
    """Read a single block from the chain

    :param int block: block number
    :param Hive blockchain_instance: Hive
        instance
    :param bool lazy: Use lazy loading
    :param bool only_ops: Includes only operations, when set to True (default: False)
    :param bool only_virtual_ops: Includes only virtual operations (default: False)

    Instances of this class are dictionaries that come with additional
    methods (see below) that allow dealing with a block and its
    corresponding functions.

    When only_virtual_ops is set to True, only_ops is always set to True.

    In addition to the block data, the block number is stored as self["id"] or self.identifier.

    .. code-block:: python

        >>> from nectar.block import Block
        >>> block = Block(1)
        >>> print(block)
        <Block 1>

    .. note:: This class comes with its own caching function to reduce the
              load on the API server. Instances of this class can be
              refreshed with ``Account.refresh()``.

    """

    def __init__(
        self,
        block: int | float | dict,
        only_ops: bool = False,
        only_virtual_ops: bool = False,
        full: bool = True,
        lazy: bool = False,
        blockchain_instance: Any = None,
        **kwargs,
    ) -> None:
        """
        Initialize a Block object representing a single blockchain block.

        block may be an integer (block number), a float (will be converted to int), or a dict containing block data (which will be parsed). Controls:
        - only_ops: load only operations from the block.
        - only_virtual_ops: load only virtual operations.
        - full: if True, populate full block data; if False, keep a minimal representation.
        - lazy: if True, defer fetching full data until needed.

        If no identifier is present after initialization, the block's identifier is set to its numeric block number.
        """
        self.full = full
        self.lazy = lazy
        self.only_ops = only_ops
        self.only_virtual_ops = only_virtual_ops
        if isinstance(block, float):
            block = int(block)
        elif isinstance(block, dict):
            block = self._parse_json_data(block)
        super().__init__(
            block,
            lazy=lazy,
            full=full,
            blockchain_instance=blockchain_instance,
            **kwargs,
        )
        if self.identifier is None:
            self.identifier = self.get(self.id_item)

    def _parse_json_data(self, block: dict) -> dict:
        parse_times = [
            "timestamp",
        ]
        for p in parse_times:
            if p in block and isinstance(block.get(p), str):
                block[p] = parse_time(block.get(p, "1970-01-01T00:00:00"))
        if "transactions" in block:
            for i in range(len(block["transactions"])):
                if "expiration" in block["transactions"][i] and isinstance(
                    block["transactions"][i]["expiration"], str
                ):
                    block["transactions"][i]["expiration"] = parse_time(
                        block["transactions"][i]["expiration"]
                    )
        elif "operations" in block:
            for i in range(len(block["operations"])):
                if "timestamp" in block["operations"][i] and isinstance(
                    block["operations"][i]["timestamp"], str
                ):
                    block["operations"][i]["timestamp"] = parse_time(
                        block["operations"][i]["timestamp"]
                    )
        return block

    def json(self) -> dict:
        output = self.copy()
        parse_times = [
            "timestamp",
        ]
        for p in parse_times:
            if p in output:
                p_date = output.get(p, datetime(1970, 1, 1, 0, 0))
                if isinstance(p_date, (datetime, date)):
                    output[p] = formatTimeString(p_date)
                else:
                    output[p] = p_date

        if "transactions" in output:
            for i in range(len(output["transactions"])):
                if "expiration" in output["transactions"][i] and isinstance(
                    output["transactions"][i]["expiration"], (datetime, date)
                ):
                    output["transactions"][i]["expiration"] = formatTimeString(
                        output["transactions"][i]["expiration"]
                    )
        elif "operations" in output:
            for i in range(len(output["operations"])):
                if "timestamp" in output["operations"][i] and isinstance(
                    output["operations"][i]["timestamp"], (datetime, date)
                ):
                    output["operations"][i]["timestamp"] = formatTimeString(
                        output["operations"][i]["timestamp"]
                    )

        ret = json.loads(str(json.dumps(output)))
        output = self._parse_json_data(output)
        return ret

    def refresh(self) -> None:
        """Even though blocks never change, you freshly obtain its contents
        from an API with this method
        """
        if self.identifier is None:
            return
        if not self.blockchain.is_connected():
            return
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if self.only_ops or self.only_virtual_ops:
            ops_ops = self.blockchain.rpc.get_ops_in_block(
                {"block_num": self.identifier, "only_virtual": self.only_virtual_ops}
            )
            ops = ops_ops["ops"] if ops_ops is not None else []
            timestamp = ops[0]["timestamp"] if ops else "1970-01-01T00:00:00"
            block = {
                "block": self.identifier,
                "timestamp": timestamp,
                "operations": ops,
            }
        else:
            block = self.blockchain.rpc.get_block({"block_num": self.identifier})
            if block and "block" in block:
                block = block["block"]
        if not block:
            message = f"Block {self.identifier} does not exist or is not available from {self.blockchain.rpc.url}"
            raise BlockDoesNotExistsException(message)
        block = self._parse_json_data(block)
        super().__init__(block, lazy=self.lazy, full=self.full, blockchain_instance=self.blockchain)

    @property
    def block_num(self) -> int | None:
        """Returns the block number"""
        if "block_id" in self:
            return int(self["block_id"][:8], base=16)
        elif "block" in self:
            return int(self["block"])
        else:
            return None

    def time(self) -> datetime:
        """Return a datetime instance for the timestamp of this block"""
        return self["timestamp"]

    @property
    def transactions(self) -> list[dict[str, Any]]:
        """Returns all transactions as list"""
        if self.only_ops or self.only_virtual_ops:
            return list()
        trxs = []
        if "transactions" not in self:
            return []
        trx_id = 0
        for trx in self["transactions"]:
            trx_new = {"transaction_id": self["transaction_ids"][trx_id]}
            trx_new.update(trx.copy())
            trx_new.update({"block_num": self.block_num, "transaction_num": trx_id})
            trxs.append(trx_new)
            trx_id += 1
        return trxs

    @property
    def operations(self) -> list[Any]:
        """Returns all block operations as list"""

        def _normalize_op_type(op_type: Any) -> Any:
            if isinstance(op_type, int):
                try:
                    from nectarbase.operationids import getOperationNameForId

                    return getOperationNameForId(op_type)
                except Exception:
                    return op_type
            return op_type

        if (self.only_ops or self.only_virtual_ops) and "operations" in self:
            ops = self["operations"]
            # Normalize get_ops_in_block format (which wraps op in "op" key)
            normalized_ops = []
            for x in ops:
                if isinstance(x, dict) and "op" in x:
                    # Wrapper found: get_ops_in_block format
                    raw_op = x["op"]
                    if isinstance(raw_op, list):
                        op_dict = {
                            "type": _normalize_op_type(raw_op[0]),
                            "value": raw_op[1],
                        }
                    elif isinstance(raw_op, dict):
                        op_dict = raw_op.copy()
                        if "type" in op_dict:
                            op_dict["type"] = _normalize_op_type(op_dict["type"])
                    else:
                        continue  # Should not happen

                    # Inject metadata from wrapper
                    if "trx_id" in x:
                        op_dict["transaction_id"] = x["trx_id"]
                    if "timestamp" in x:
                        op_dict["timestamp"] = x["timestamp"]
                    if "block" in x:
                        op_dict["block_num"] = x["block"]

                    normalized_ops.append(op_dict)
                elif isinstance(x, (list, tuple)) and len(x) >= 2:
                    normalized_ops.append({"type": _normalize_op_type(x[0]), "value": x[1]})
                elif isinstance(x, dict) and "type" in x and "value" in x:
                    op_dict = x.copy()
                    op_dict["type"] = _normalize_op_type(op_dict["type"])
                    normalized_ops.append(op_dict)
                else:
                    # Legacy or direct format?
                    normalized_ops.append(x)
            return normalized_ops
        ops = []
        trxs = []
        if "transactions" in self:
            trxs = self["transactions"]

        for tx_idx, tx in enumerate(trxs):
            if "operations" not in tx:
                continue

            # Get transaction_id if available (it is usually in a separate list in the block)
            current_trx_id = None
            if "transaction_ids" in self and len(self["transaction_ids"]) > tx_idx:
                current_trx_id = self["transaction_ids"][tx_idx]
            # Provide fallback if it was somehow already in tx (e.g. from different API)
            elif "transaction_id" in tx:
                current_trx_id = tx["transaction_id"]

            for op in tx["operations"]:
                # Replace op id by op name when numeric
                if isinstance(op, (list, tuple)) and len(op) > 0:
                    op[0] = _normalize_op_type(op[0])
                if isinstance(op, list):
                    if self.only_ops or self.only_virtual_ops:
                        op_dict = {"type": op[0], "value": op[1]}
                        # Inject formatting that helpers.py expects
                        if current_trx_id:
                            op_dict["transaction_id"] = current_trx_id

                        if "block_num" in tx:
                            op_dict["block_num"] = tx["block_num"]
                        elif self.block_num:
                            op_dict["block_num"] = self.block_num

                        op_dict["timestamp"] = self.time()
                        ops.append(op_dict)
                    else:
                        ops.append(list(op))
                elif isinstance(op, dict):
                    # If op is already a dictionary, we still need to inject metadata if we are in only_ops mode
                    if self.only_ops or self.only_virtual_ops:
                        op_dict = op.copy()
                        if "type" in op_dict:
                            op_dict["type"] = _normalize_op_type(op_dict["type"])

                        # In some cases op might be {"op": {"type": ..., "value": ...}} ??
                        # But loop above handles raw operations list.
                        # Assuming op is {"type": ..., "value": ...} or similar structure

                        if current_trx_id and "transaction_id" not in op_dict:
                            op_dict["transaction_id"] = current_trx_id

                        if "block_num" not in op_dict:
                            if "block_num" in tx:
                                op_dict["block_num"] = tx["block_num"]
                            elif self.block_num:
                                op_dict["block_num"] = self.block_num

                        if "timestamp" not in op_dict:
                            op_dict["timestamp"] = self.time()
                        ops.append(op_dict)
                    else:
                        ops.append(op.copy())
                else:
                    ops.append(op.copy())
        return ops

    @property
    def json_transactions(self) -> list[dict[str, Any]]:
        """Returns all transactions as list, all dates are strings."""
        if self.only_ops or self.only_virtual_ops:
            return list()
        trxs = []
        if "transactions" not in self:
            return []
        trx_id = 0
        for trx in self["transactions"]:
            trx_new = {"transaction_id": self["transaction_ids"][trx_id]}
            trx_new.update(trx.copy())
            trx_new.update({"block_num": self.block_num, "transaction_num": trx_id})
            if "expiration" in trx:
                p_date = trx.get("expiration", datetime(1970, 1, 1, 0, 0))
                if isinstance(p_date, (datetime, date)):
                    trx_new.update({"expiration": formatTimeString(p_date)})

            trxs.append(trx_new)
            trx_id += 1
        return trxs

    @property
    def json_operations(self) -> list[Any]:
        """Returns all block operations as list, all dates are strings."""
        if self.only_ops or self.only_virtual_ops:
            return self["operations"]
        ops = []
        for tx in self["transactions"]:
            for op in tx["operations"]:
                if "operations" not in tx:
                    continue
                # Replace op id by op name when numeric
                if isinstance(op, (list, tuple)) and len(op) > 0 and isinstance(op[0], int):
                    try:
                        from nectarbase.operationids import getOperationNameForId

                        op[0] = getOperationNameForId(op[0])
                    except Exception:
                        pass
                if isinstance(op, list):
                    op_new = list(op)
                else:
                    op_new = op.copy()
                if "timestamp" in op:
                    p_date = op.get("timestamp", datetime(1970, 1, 1, 0, 0))
                    if isinstance(p_date, (datetime, date)):
                        if isinstance(op_new, dict):
                            op_new.update({"timestamp": formatTimeString(p_date)})
                        else:
                            # Handle list case - find timestamp in list and update it
                            for i, item in enumerate(op_new):
                                if isinstance(item, dict) and "timestamp" in item:
                                    op_new[i] = {
                                        **item,
                                        "timestamp": formatTimeString(p_date),
                                    }
                                    break
                ops.append(op_new)
        return ops

    def ops_statistics(self, add_to_ops_stat: dict[str, int] | None = None) -> dict[str, int]:
        """Returns a statistic with the occurrence of the different operation types"""
        if add_to_ops_stat is None:
            import nectarbase.operationids

            ops_stat = nectarbase.operationids.operations.copy()
            for key in ops_stat:
                if isinstance(key, int):
                    ops_stat[key] = 0
        else:
            ops_stat = add_to_ops_stat.copy()
        for op in self.operations:
            if "op" in op:
                op = op["op"]
            if isinstance(op, dict) and "type" in op:
                op_type = op["type"]
                if len(op_type) > 10 and op_type[len(op_type) - 10 :] == "_operation":
                    op_type = op_type[:-10]
            else:
                op_type = op[0]
            if op_type in ops_stat:
                ops_stat[op_type] += 1
        return ops_stat


class BlockHeader(BlockchainObject):
    """Read a single block header from the chain

    :param int block: block number
    :param Hive blockchain_instance: Hive
        instance
    :param bool lazy: Use lazy loading

    In addition to the block data, the block number is stored as self["id"] or self.identifier.

    .. code-block:: python

        >>> from nectar.block import BlockHeader
        >>> block = BlockHeader(1)
        >>> print(block)
        <BlockHeader 1>

    """

    def __init__(
        self,
        block: int | float | dict,
        full: bool = True,
        lazy: bool = False,
        blockchain_instance: Any = None,
        **kwargs,
    ) -> None:
        """
        Initialize a BlockHeader.

        One-line summary:
            Create a BlockHeader wrapper for a block header, optionally in lazy or full mode.

        Parameters:
            block (int | float | dict): Block number (floats are converted to int) or a header dict.
            full (bool): If True, populate the object with full header data; otherwise keep a minimal representation.
            lazy (bool): If True, delay API fetching until data is accessed.

        Notes:
            If no blockchain_instance is provided, the module's shared blockchain instance is used.
        """
        self.full = full
        self.lazy = lazy
        if isinstance(block, float):
            block = int(block)
        super().__init__(
            block,
            lazy=lazy,
            full=full,
            blockchain_instance=blockchain_instance,
            **kwargs,
        )

    def refresh(self) -> None:
        """Even though blocks never change, you freshly obtain its contents
        from an API with this method
        """
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        block = self.blockchain.rpc.get_block_header({"block_num": self.identifier})
        if block is not None and "header" in block:
            block = block["header"]
        if not block:
            raise BlockDoesNotExistsException(str(self.identifier))
        block = self._parse_json_data(block)
        super().__init__(block, lazy=self.lazy, full=self.full, blockchain_instance=self.blockchain)

    def time(self) -> datetime:
        """Return a datetime instance for the timestamp of this block"""
        return self["timestamp"]

    @property
    def block_num(self) -> int:
        """Returns the block number"""
        if self.identifier is None:
            raise ValueError("Block identifier is not set")
        if isinstance(self.identifier, int):
            return self.identifier
        # Try to convert string or other types to int
        return int(self.identifier)

    def _parse_json_data(self, block: dict) -> dict:
        parse_times = [
            "timestamp",
        ]
        for p in parse_times:
            if p in block and isinstance(block.get(p), str):
                block[p] = parse_time(block.get(p, "1970-01-01T00:00:00"))
        return block

    def json(self) -> dict:
        output = self.copy()
        parse_times = [
            "timestamp",
        ]
        for p in parse_times:
            if p in output:
                p_date = output.get(p, datetime(1970, 1, 1, 0, 0))
                if isinstance(p_date, (datetime, date)):
                    output[p] = formatTimeString(p_date)
                else:
                    output[p] = p_date
        return json.loads(str(json.dumps(output)))


class Blocks(list):
    """Obtain a list of blocks

    :param list name_list: list of accounts to fetch
    :param int count: (optional) maximum number of accounts
        to fetch per call, defaults to 100
    :param Hive blockchain_instance: Hive() instance to use when
        accessing RPC
    """

    def __init__(
        self,
        starting_block_num: int,
        count: int = 1000,
        lazy: bool = False,
        full: bool = True,
        only_ops: bool = False,
        only_virtual_ops: bool = False,
        blockchain_instance: Any = None,
        **kwargs,
    ) -> None:
        """
        Initialize a Blocks collection by fetching a contiguous range of blocks from the chain and populating the list with Block objects.

        If a blockchain_instance is provided it is used; otherwise the shared blockchain instance is used. If the chosen instance is not connected, the initializer returns early and the Blocks object remains empty.

        Parameters:
            starting_block_num (int): First block number to retrieve.
            count (int, optional): Number of consecutive blocks to fetch. Defaults to 1000.
            lazy (bool, optional): If True, create Block objects in lazy mode (defer full parsing). Defaults to False.
            full (bool, optional): If True, create Block objects with full data loaded (subject to lazy). Defaults to True.
            only_ops (bool, optional): If True, blocks will contain only regular operations (no block metadata). Defaults to False.
            only_virtual_ops (bool, optional): If True, blocks will contain only virtual operations. Defaults to False.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if not self.blockchain.is_connected():
            return
        blocks = []

        self.blockchain.rpc.set_next_node_on_empty_reply(False)

        blocks = self.blockchain.rpc.get_block_range(
            {"starting_block_num": starting_block_num, "count": count}
        )["blocks"]

        super().__init__(
            [
                Block(
                    x,
                    lazy=lazy,
                    full=full,
                    only_ops=only_ops,
                    only_virtual_ops=only_virtual_ops,
                    blockchain_instance=self.blockchain,
                    **kwargs,
                )
                for x in blocks
            ]
        )
