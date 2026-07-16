from __future__ import annotations

import ast
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any

from nectar.account import Account
from nectar.amount import Amount
from nectar.constants import (
    CURVE_CONSTANT,
    CURVE_CONSTANT_X4,
    HIVE_1_PERCENT,
    HIVE_100_PERCENT,
    HIVE_RC_REGEN_TIME,
    HIVE_VOTE_REGENERATION_SECONDS,
    SQUARED_CURVE_CONSTANT,
)
from nectar.exceptions import AccountDoesNotExistsException, AccountExistsException
from nectar.price import Price
from nectar.storage import get_default_config_store
from nectar.transactionbuilder import TransactionBuilder
from nectar.utils import (
    derive_permlink,
    remove_from_dict,
    resolve_authorperm,
    sanitize_permlink,
)
from nectar.version import version as nectar_version
from nectar.wallet import Wallet
from nectarapi.noderpc import NodeRPC
from nectarbase import operations
from nectargraphenebase.account import PrivateKey, PublicKey
from nectargraphenebase.chains import known_chains

log = logging.getLogger(__name__)

RPC_NOT_ESTABLISHED = "RPC connection not established"


class BlockChainInstance:
    """Connect to a Graphene network.

    :param str node: Node to connect to *(optional)*
    :param str rpcuser: RPC user *(optional)*
    :param str rpcpassword: RPC password *(optional)*
    :param bool nobroadcast: Do **not** broadcast a transaction!
        *(optional)*
    :param bool unsigned: Do **not** sign a transaction! *(optional)*
    :param bool debug: Enable Debugging *(optional)*
    :param keys: Predefine the wif keys to shortcut the
        wallet database *(optional)*
    :type keys: array, dict, string
    :param wif: Predefine the wif keys to shortcut the
            wallet database *(optional)*
    :type wif: array, dict, string
    :param bool offline: Boolean to prevent connecting to network (defaults
        to ``False``) *(optional)*
    :param int expiration: Delay in seconds until transactions are supposed
        to expire *(optional)* (default is 300)
    :param str blocking: Wait for broadcasted transactions to be included
        in a block and return full transaction (can be "head" or
        "irreversible")
    :param bool bundle: Do not broadcast transactions right away, but allow
        to bundle operations. It is not possible to send out more than one
        vote operation and more than one comment operation in a single broadcast *(optional)*
    :param dict custom_chains: custom chain which should be added to the known chains

    Three wallet operation modes are possible:

    * **Wallet Database**: Here, the nectar libraries load the keys from the
      locally stored wallet SQLite database (see ``storage.py``).
      To use this mode, simply call ``Hive()`` without the
      ``keys`` parameter
    * **Providing Keys**: Here, you can provide the keys for
      your accounts manually. All you need to do is add the wif
      keys for the accounts you want to use as a simple array
      using the ``keys`` parameter to ``Hive()``.
    * **Force keys**: This more is for advanced users and
      requires that you know what you are doing. Here, the
      ``keys`` parameter is a dictionary that overwrite the
      ``active``, ``owner``, ``posting`` or ``memo`` keys for
      any account. This mode is only used for *foreign*
      signatures!

    If no node is provided, it will connect to the default Hive nodes.
    Default settings can be changed with:

    .. code-block:: python

        hive = Hive(<host>)

    where ``<host>`` starts with ``https://``, ``ws://`` or ``wss://``.

    The purpose of this class is to simplify interaction with
    Hive.

    The idea is to have a class that allows to do this:

    .. code-block:: python

        >>> from nectar import Hive
        >>> hive = Hive()
        >>> print(hive.get_blockchain_version())  # doctest: +SKIP

    This class also deals with edits, votes and reading content.

    Example for adding a custom chain:

    .. code-block:: python

        from nectar import Hive
        hv = Hive(node=["https://mytstnet.com"], custom_chains={"MYTESTNET":
            {'chain_assets': [{'asset': 'HBD', 'id': 0, 'precision': 3, 'symbol': 'HBD'},
                              {'asset': 'HIVE', 'id': 1, 'precision': 3, 'symbol': 'HIVE'},
                              {'asset': 'VESTS', 'id': 2, 'precision': 6, 'symbol': 'VESTS'}],
             'chain_id': '79276aea5d4877d9a25892eaa01b0adf019d3e5cb12a97478df3298ccdd01674',
             'min_version': '0.0.0',
             'prefix': 'MTN'}
            }
        )

    """

    def __init__(
        self,
        node: str | list[str] | None = None,
        rpcuser: str | None = None,
        rpcpassword: str | None = None,
        debug: bool = False,
        data_refresh_time_seconds: int = 900,
        **kwargs,
    ) -> None:
        """
        Initialize the BlockChainInstance, set up connection (unless offline), load configuration, initialize caches and transaction buffers, and create the Wallet and optional ledger signing support.

        Parameters:
            node (str): RPC node URL to connect to (optional; ignored if offline).
            rpcuser (str), rpcpassword (str): Optional RPC credentials for the node.
            data_refresh_time_seconds (int): Default cache refresh interval in seconds.
            debug (bool): Enable debug mode.
            **kwargs: Additional options (commonly used keys)
                - offline (bool): If True, skip connecting to a node.
                - nobroadcast (bool): If True, do not broadcast transactions.
                - unsigned (bool): If True, do not sign transactions.
                - expiration (int): Transaction expiration delay in seconds.
                - bundle (bool): If True, enable bundling of operations instead of immediate broadcast.
                - blocking (str|bool): Wait mode for broadcasts ("head" or "irreversible").
                - custom_chains (dict): Custom chain definitions.
                - use_ledger (bool): If True, enable Ledger Nano signing.
                - path (str): BIP32 path to derive pubkey from when using Ledger.
                - config_store: Configuration store object (defaults to the global default).
        """

        self.rpc = None
        self.client = None
        self.async_client = None
        self.pool_manager = None
        self.debug = debug

        self.offline = bool(kwargs.get("offline", False))
        self.nobroadcast = bool(kwargs.get("nobroadcast", False))
        self.unsigned = bool(kwargs.get("unsigned", False))
        # Default transaction expiration window (seconds). Increased from 30s to 300s for better tolerance to node clock skew/network latency.
        self.expiration = int(kwargs.get("expiration", 300))
        self.bundle = bool(kwargs.get("bundle", False))
        self.blocking = kwargs.get("blocking", False)
        self.custom_chains = kwargs.get("custom_chains", {})
        self.use_ledger = bool(kwargs.get("use_ledger", False))
        self.path = kwargs.get("path", None)

        # Store config for access through other Classes
        self.config = kwargs.get("config_store", get_default_config_store(node=node, **kwargs))
        if self.path is None:
            self.path = self.config["default_path"]

        if not self.offline:
            if node:
                # Type assertion: we know node is not None here
                assert node is not None
                self.connect(
                    node=node,
                    rpcuser=rpcuser or "",
                    rpcpassword=rpcpassword or "",
                    **kwargs,
                )
            else:
                self.connect(
                    node="",
                    rpcuser=rpcuser or "",
                    rpcpassword=rpcpassword or "",
                    **kwargs,
                )

        self.clear_data()
        self.data_refresh_time_seconds = data_refresh_time_seconds
        # self.refresh_data()

        # txbuffers/propbuffer are initialized and cleared
        self.clear()

        self.wallet = Wallet(blockchain_instance=self, **kwargs)

    # -------------------------------------------------------------------------
    # Basic Calls
    # -------------------------------------------------------------------------
    def connect(
        self,
        node: str | list[str] = "",
        rpcuser: str = "",
        rpcpassword: str = "",
        **kwargs,
    ) -> None:
        """
        Connect to a Hive node and initialize the internal RPC client.

        If node is empty, the method will attempt to use the configured default nodes; if none are available a ValueError is raised.
        If rpcuser or rpcpassword are not provided, values are read from self.config when present. The config key "use_tor" (if set) will be used to enable Tor for the connection.
        Any additional keyword arguments are forwarded to the NodeRPC constructor.

        Parameters:
            node (str | list): Node URL or list of node URLs to connect to. If omitted, default nodes are used.
            rpcuser (str): Optional RPC username; falls back to self.config["rpcuser"] when not supplied.
            rpcpassword (str): Optional RPC password; falls back to self.config["rpcpassword"] when not supplied.

        Raises:
            ValueError: If no node is provided and no default nodes are configured.
        """
        if not node:
            node = self.get_default_nodes()
            if not bool(node):
                raise ValueError("A Hive node needs to be provided!")

        if not rpcuser and "rpcuser" in self.config:
            rpcuser = self.config["rpcuser"]

        if not rpcpassword and "rpcpassword" in self.config:
            rpcpassword = self.config["rpcpassword"]

        if "use_tor" in self.config:
            use_tor = self.config["use_tor"]
        else:
            use_tor = False

        self.rpc = NodeRPC(node, rpcuser, rpcpassword, use_tor=use_tor, **kwargs)

        import httpx2

        node_list = node if isinstance(node, list) else ([node] if node else [])
        if not node_list and self.rpc and hasattr(self.rpc, "nodes"):
            node_list = self.rpc.nodes.get_nodes()

        if len(node_list) > 1:
            from nectarapi.pool import NodePoolManager
            from nectarapi.transports import FailoverAsyncTransport, FailoverSyncTransport

            self.pool_manager = NodePoolManager(node_list)
            if self.rpc and hasattr(self.rpc, "nodes"):
                self.rpc.nodes.pool_manager = self.pool_manager
            self.sync_transport = FailoverSyncTransport(
                self.pool_manager, proxy="socks5h://localhost:9050" if use_tor else None
            )
            self.async_transport = FailoverAsyncTransport(
                self.pool_manager, proxy="socks5h://localhost:9050" if use_tor else None
            )
            self.client = httpx2.Client(transport=self.sync_transport)
            self.async_client = httpx2.AsyncClient(transport=self.async_transport)
        else:
            self.client = httpx2.Client()
            self.async_client = httpx2.AsyncClient()

    def is_connected(self) -> bool:
        """Returns if rpc is connected"""
        # Consider the instance connected only if an RPC client exists AND
        # it has an active URL set by rpcconnect(). Previously, this returned
        # True when self.rpc was merely instantiated but without a selected
        # working node (i.e., self.rpc.url was None), which caused downstream
        # RPC calls to raise RPCConnection("RPC is not connected!").
        return self.rpc is not None and bool(getattr(self.rpc, "url", None))

    def __repr__(self) -> str:
        if self.offline:
            return "<%s offline=True>" % (self.__class__.__name__)
        elif self.rpc is not None and self.rpc.url and len(self.rpc.url) > 0:
            return "<{} node={}, nobroadcast={}>".format(
                self.__class__.__name__,
                str(self.rpc.url),
                str(self.nobroadcast),
            )
        else:
            return f"<{self.__class__.__name__}, nobroadcast={str(self.nobroadcast)}>"

    def clear_data(self) -> None:
        """
        Reset the internal cache of blockchain-derived data.

        This clears stored values used to cache node-dependent blockchain parameters (dynamic global properties, feed history,
        hardfork properties, network info, witness schedule, config, reward funds) and their per-key refresh timestamps. It does
        not affect network connection, wallet state, transaction buffers, or other non-cache attributes.
        """
        self.data = {
            "last_refresh": None,
            "last_node": None,
            "last_refresh_dynamic_global_properties": None,
            "dynamic_global_properties": None,
            "feed_history": None,
            "get_feed_history": None,
            "last_refresh_feed_history": None,
            "hardfork_properties": None,
            "last_refresh_hardfork_properties": None,
            "network": None,
            "last_refresh_network": None,
            "witness_schedule": None,
            "last_refresh_witness_schedule": None,
            "config": None,
            "last_refresh_config": None,
            "reward_funds": None,
            "last_refresh_reward_funds": None,
        }

    def refresh_data(
        self,
        chain_property: str,
        force_refresh: bool = False,
        data_refresh_time_seconds: int | None = None,
    ) -> None:
        """
        Refresh and cache a specific blockchain data category in self.data.

        This updates the cached value for the given chain_property (one of:
        "dynamic_global_properties", "feed_history", "hardfork_properties",
        "witness_schedule", "config", "reward_funds"). If the cached value was
        refreshed recently (within self.data_refresh_time_seconds) and force_refresh
        is False, the method will skip the RPC call. When online, timestamps
        (last_refresh_*) and last_node are updated to reflect the refresh.

        Parameters:
            chain_property (str): The cache key to refresh; must be one of the supported properties.
            force_refresh (bool): If True, bypass the time-based refresh guard and force an update.
            data_refresh_time_seconds (float | None): If provided, set a new minimal refresh interval
                (in seconds) before evaluating whether to skip refreshing.

        Raises:
            ValueError: If chain_property is not one of the supported keys.
        """
        # if self.offline:
        #    return
        if data_refresh_time_seconds is not None:
            self.data_refresh_time_seconds = data_refresh_time_seconds
        if chain_property == "dynamic_global_properties":
            if not self.offline:
                if (
                    self.data["last_refresh_dynamic_global_properties"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc)
                        - self.data["last_refresh_dynamic_global_properties"]
                    ).total_seconds() < self.data_refresh_time_seconds:
                        return
                self.data["last_refresh_dynamic_global_properties"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            self.data["dynamic_global_properties"] = self.get_dynamic_global_properties(False)
        elif chain_property == "feed_history":
            if not self.offline:
                if (
                    self.data["last_refresh_feed_history"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc) - self.data["last_refresh_feed_history"]
                    ).total_seconds() < self.data_refresh_time_seconds:
                        return

                self.data["last_refresh_feed_history"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            try:
                self.data["feed_history"] = self.get_feed_history(False)
            except Exception:
                self.data["feed_history"] = None
            self.data["get_feed_history"] = self.data["feed_history"]
        elif chain_property == "hardfork_properties":
            if not self.offline:
                if (
                    self.data["last_refresh_hardfork_properties"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc) - self.data["last_refresh_hardfork_properties"]
                    ).total_seconds() < self.data_refresh_time_seconds:
                        return

                self.data["last_refresh_hardfork_properties"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            try:
                self.data["hardfork_properties"] = self.get_hardfork_properties(False)
            except Exception:
                self.data["hardfork_properties"] = None
        elif chain_property == "witness_schedule":
            if not self.offline:
                if (
                    self.data["last_refresh_witness_schedule"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc) - self.data["last_refresh_witness_schedule"]
                    ).total_seconds() < 3:
                        return
                self.data["last_refresh_witness_schedule"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            self.data["witness_schedule"] = self.get_witness_schedule(False)
        elif chain_property == "config":
            if not self.offline:
                if (
                    self.data["last_refresh_config"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc) - self.data["last_refresh_config"]
                    ).total_seconds() < self.data_refresh_time_seconds:
                        return
                self.data["last_refresh_config"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            self.data["config"] = self.get_config(False)
            self.data["network"] = self.get_network(False, config=self.data["config"])
        elif chain_property == "reward_funds":
            if not self.offline:
                if (
                    self.data["last_refresh_reward_funds"] is not None
                    and not force_refresh
                    and self.rpc is not None
                    and self.data["last_node"] == self.rpc.url
                ):
                    if (
                        datetime.now(timezone.utc) - self.data["last_refresh_reward_funds"]
                    ).total_seconds() < self.data_refresh_time_seconds:
                        return

                self.data["last_refresh_reward_funds"] = datetime.now(timezone.utc)
                self.data["last_refresh"] = datetime.now(timezone.utc)
                if self.rpc is not None:
                    self.data["last_node"] = self.rpc.url
            self.data["reward_funds"] = self.get_reward_funds(False)
        else:
            raise ValueError("%s is not unknown" % str(chain_property))

    def get_dynamic_global_properties(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """This call returns the *dynamic global properties*

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
            empty or old, refresh_data() is used.

        """
        if use_stored_data:
            self.refresh_data("dynamic_global_properties")
            return self.data["dynamic_global_properties"]
        if self.rpc is None:
            return None
        self.rpc.set_next_node_on_empty_reply(True)
        return self.rpc.get_dynamic_global_properties()

    def get_reserve_ratio(self) -> dict[str, Any] | None:
        """This call returns the *reserve ratio*"""
        if self.rpc is None:
            return None
        self.rpc.set_next_node_on_empty_reply(True)

        props = self.get_dynamic_global_properties()
        # conf = self.get_config()
        if props is None:
            return {
                "id": 0,
                "average_block_size": None,
                "current_reserve_ratio": None,
                "max_virtual_bandwidth": None,
            }
        try:
            reserve_ratio = {
                "id": 0,
                "average_block_size": props["average_block_size"],
                "current_reserve_ratio": props["current_reserve_ratio"],
                "max_virtual_bandwidth": props["max_virtual_bandwidth"],
            }
        except Exception:
            reserve_ratio = {
                "id": 0,
                "average_block_size": None,
                "current_reserve_ratio": None,
                "max_virtual_bandwidth": None,
            }
        return reserve_ratio

    def get_feed_history(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns the feed_history

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
            empty or old, refresh_data() is used.

        """
        if use_stored_data:
            self.refresh_data("feed_history")
            return self.data["feed_history"]
        if self.rpc is None:
            return None
        self.rpc.set_next_node_on_empty_reply(True)
        return self.rpc.get_feed_history()

    def get_reward_funds(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Get details for a reward fund.

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
            empty or old, refresh_data() is used.

        """
        if use_stored_data:
            self.refresh_data("reward_funds")
            return self.data["reward_funds"]

        if self.rpc is None:
            return None
        ret = None
        self.rpc.set_next_node_on_empty_reply(True)
        funds = self.rpc.get_reward_funds()
        if funds is not None:
            funds = funds["funds"]
        else:
            return None
        if len(funds) > 0:
            funds = funds[0]
            ret = funds
        else:
            ret = None
        return ret

    def get_current_median_history(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns the current median price

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
                                     empty or old, refresh_data() is used.
        """
        if use_stored_data:
            self.refresh_data("feed_history")
            if self.data["get_feed_history"]:
                return self.data["get_feed_history"]["current_median_history"]
            else:
                return None
        if self.rpc is None:
            return None
        ret = None
        self.rpc.set_next_node_on_empty_reply(True)
        ret = self.rpc.get_feed_history()["current_median_history"]
        return ret

    def get_hardfork_properties(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns Hardfork and live_time of the hardfork

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
                                     empty or old, refresh_data() is used.
        """
        if use_stored_data:
            self.refresh_data("hardfork_properties")
            return self.data["hardfork_properties"]
        if self.rpc is None:
            return None
        ret = None
        self.rpc.set_next_node_on_empty_reply(True)
        ret = self.rpc.get_hardfork_properties()
        return ret

    def get_network(
        self, use_stored_data: bool = True, config: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Identify the network

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
                                     empty or old, refresh_data() is used.

        :returns: Network parameters
        :rtype: dictionary
        """
        if use_stored_data:
            self.refresh_data("config")
            return self.data["network"]

        if self.rpc is None:
            return None
        try:
            return self.rpc.get_network(props=config)
        except Exception:
            return known_chains["HIVE"]

    def get_median_price(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns the current median history price as Price"""
        median_price = self.get_current_median_history(use_stored_data=use_stored_data)
        if median_price is None:
            return None
        a = Price(
            None,
            base=Amount(median_price["base"], blockchain_instance=self),
            quote=Amount(median_price["quote"], blockchain_instance=self),
            blockchain_instance=self,
        )
        return a.as_base(self.backed_token_symbol)

    def get_block_interval(self, use_stored_data: bool = True) -> int:
        """Returns the block interval in seconds"""
        props = self.get_config(use_stored_data=use_stored_data)
        block_interval = 3
        if props is None:
            return block_interval
        for key in props:
            if key[-14:] == "BLOCK_INTERVAL":
                block_interval = props[key]

        return block_interval

    def get_blockchain_version(self, use_stored_data: bool = True) -> str | dict[str, Any]:
        """Returns the blockchain version"""
        props = self.get_config(use_stored_data=use_stored_data)
        blockchain_version = "0.0.0"
        if props is None:
            return blockchain_version
        for key in props:
            if key[-18:] == "BLOCKCHAIN_VERSION":
                blockchain_version = props[key]
        return blockchain_version

    def get_blockchain_name(self, use_stored_data: bool = True) -> str:
        """Returns the blockchain version"""
        props = self.get_config(use_stored_data=use_stored_data)
        blockchain_name = ""
        if props is None:
            return blockchain_name
        for key in props:
            if key[-18:] == "BLOCKCHAIN_VERSION":
                blockchain_name = key.split("_")[0].lower()
        return blockchain_name

    def get_dust_threshold(self, use_stored_data: bool = True) -> float:
        """Returns the vote dust threshold"""
        props = self.get_config(use_stored_data=use_stored_data)
        dust_threshold = 0
        if props is None:
            return dust_threshold
        for key in props:
            if key[-20:] == "VOTE_DUST_THRESHOLD":
                dust_threshold = props[key]
        return dust_threshold

    def get_resource_params(self) -> dict[str, Any]:
        """Returns the resource parameter"""
        if self.rpc is None:
            raise RuntimeError(RPC_NOT_ESTABLISHED)
        return self.rpc.get_resource_params()["resource_params"]

    def get_resource_pool(self) -> dict[str, Any]:
        """Returns the resource pool"""
        if self.rpc is None:
            raise RuntimeError(RPC_NOT_ESTABLISHED)
        return self.rpc.get_resource_pool()["resource_pool"]

    def get_rc_cost(self, resource_count: dict[str, int]) -> int:
        """
        Compute the total Resource Credits (RC) cost for a set of resource usages.

        This queries the current resource pool, price curve parameters, and dynamic global properties to compute the RC cost for each resource type in `resource_count` and returns their sum. If the RC regeneration rate is zero, returns 0.

        Parameters:
            resource_count (dict): Mapping of resource type keys to requested usage counts. Counts are interpreted in resource-specific units and will be scaled by the resource's `resource_unit` parameter.

        Returns:
            int: Total RC cost (rounded as produced by internal cost calculation).
        """
        pools = self.get_resource_pool()
        params = self.get_resource_params()
        dyn_param = self.get_dynamic_global_properties()
        if dyn_param is None:
            return 0
        rc_regen = int(Amount(dyn_param["total_vesting_shares"], blockchain_instance=self)) / (
            HIVE_RC_REGEN_TIME / self.get_block_interval()
        )
        total_cost = 0
        if rc_regen == 0:
            return total_cost
        for resource_type in resource_count:
            curve_params = params[resource_type]["price_curve_params"]
            current_pool = int(pools[resource_type]["pool"])
            count = resource_count[resource_type]
            count *= params[resource_type]["resource_dynamics_params"]["resource_unit"]
            cost = self._compute_rc_cost(curve_params, current_pool, int(count), int(rc_regen))
            total_cost += cost
        return total_cost

    def _compute_rc_cost(
        self,
        curve_params: dict[str, Any],
        current_pool: int,
        resource_count: int,
        rc_regen: int,
    ) -> int:
        """Helper function for computing the RC costs"""
        num = int(rc_regen)
        num *= int(curve_params["coeff_a"])
        num = int(num) >> int(curve_params["shift"])
        num += 1
        num *= int(resource_count)
        denom = int(curve_params["coeff_b"])
        if int(current_pool) > 0:
            denom += int(current_pool)
        num_denom = num / denom
        return int(num_denom) + 1

    def _max_vote_denom(self, use_stored_data: bool = True) -> int:
        # get props
        """
        Compute the maximum vote denominator used to scale voting power consumption.

        This reads the current `vote_power_reserve_rate` from dynamic global properties
        (and may use cached data when `use_stored_data` is True) and multiplies it by
        HIVE_VOTE_REGENERATION_SECONDS to produce the denominator used in vote power
        calculations.

        Parameters:
            use_stored_data (bool): If True, allow using cached dynamic global properties
                rather than fetching fresh values from the node.

        Returns:
            int: The computed maximum vote denominator.
        """
        global_properties = self.get_dynamic_global_properties(use_stored_data=use_stored_data)
        if global_properties is None:
            return HIVE_VOTE_REGENERATION_SECONDS  # fallback value
        vote_power_reserve_rate = global_properties["vote_power_reserve_rate"]
        max_vote_denom = vote_power_reserve_rate * HIVE_VOTE_REGENERATION_SECONDS
        return max_vote_denom

    def _calc_resulting_vote(
        self, current_power: int, weight: int, power: int = HIVE_100_PERCENT
    ) -> int:
        # determine voting power used
        """
        Calculate the internal "used power" for a vote given current voting power and vote percentage.

        This converts a voter's remaining voting_power and a requested vote_pct (both expressed on the same internal scale where HIVE_100_PERCENT represents 100%) into the integer unit the chain uses for vote consumption. The computation uses the absolute value of vote_pct, scales by a 24-hour factor (60*60*24), then normalizes by the chain's maximum vote denominator (retrieved via _max_vote_denom) with upward rounding.

        Parameters:
            current_power (int): Current voting power expressed in the node's internal units (HIVE_100_PERCENT == full power).
            weight (int): Vote weight in the node's internal units.
            power (int): Power parameter (defaults to HIVE_100_PERCENT).

        Returns:
            int: The computed used voting power in the chain's internal units.
        """
        used_power = int((current_power * abs(weight)) / HIVE_100_PERCENT * (60 * 60 * 24))
        max_vote_denom = self._max_vote_denom(use_stored_data=True)
        used_power = int((used_power + max_vote_denom - 1) / max_vote_denom)
        return used_power

    def _calc_vote_claim(self, effective_vote_rshares: int, post_rshares: int) -> int | float:
        post_rshares_normalized = post_rshares + CURVE_CONSTANT
        post_rshares_after_vote_normalized = post_rshares + effective_vote_rshares + CURVE_CONSTANT
        post_rshares_curve = (
            post_rshares_normalized * post_rshares_normalized - SQUARED_CURVE_CONSTANT
        ) / (post_rshares + CURVE_CONSTANT_X4)
        post_rshares_curve_after_vote = (
            post_rshares_after_vote_normalized * post_rshares_after_vote_normalized
            - SQUARED_CURVE_CONSTANT
        ) / (post_rshares + effective_vote_rshares + CURVE_CONSTANT_X4)
        vote_claim = post_rshares_curve_after_vote - post_rshares_curve
        return vote_claim

    def _calc_revert_vote_claim(self, vote_claim: int, post_rshares: int) -> int | float:
        post_rshares_normalized = post_rshares + CURVE_CONSTANT
        post_rshares_curve = (
            post_rshares_normalized * post_rshares_normalized - SQUARED_CURVE_CONSTANT
        ) / (post_rshares + CURVE_CONSTANT_X4)
        post_rshares_curve_after_vote = vote_claim + post_rshares_curve

        a = 1
        b = -post_rshares_curve_after_vote + 2 * post_rshares_normalized
        c = (
            post_rshares_normalized * post_rshares_normalized - SQUARED_CURVE_CONSTANT
        ) - post_rshares_curve_after_vote * (post_rshares + CURVE_CONSTANT_X4)
        # (effective_vote_rshares * effective_vote_rshares) + effective_vote_rshares * (-post_rshares_curve_after_vote + 2 * post_rshares_normalized) + ((post_rshares_normalized * post_rshares_normalized - SQUARED_CURVE_CONSTANT)  - post_rshares_curve_after_vote * (post_rshares + CURVE_CONSTANT_X4)) = 0

        x1 = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
        x2 = (-b - math.sqrt(b * b - 4 * a * c)) / (2 * a)
        if x1 >= 0:
            return x1
        else:
            return x2

    def vests_to_rshares(
        self,
        vests: float | int | Amount,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        subtract_dust_threshold: bool = True,
        use_stored_data: bool = True,
        post_rshares: int = 0,
    ) -> int | float:
        """
        Convert vesting shares to reward r-shares used for voting.

        Calculates the signed r-shares produced by a vote from a given amount of vesting shares, taking into account current voting power and vote percentage. Optionally subtracts the chain's dust threshold so small votes become zero.

        Parameters:
            vests (float|int): Vesting shares (in VESTS units) to convert.
            voting_power (int, optional): Voter's current voting power, where 100% == 10000. Defaults to HIVE_100_PERCENT.
            vote_pct (int, optional): Intended vote strength, where 100% == 10000. Can be negative for downvotes. Defaults to HIVE_100_PERCENT.
            subtract_dust_threshold (bool, optional): If True, subtract the chain's dust threshold from the absolute r-shares and return 0 when the result is at-or-below the threshold. Defaults to True.
            use_stored_data (bool, optional): If True, prefer cached chain parameters when computing vote cost; otherwise fetch fresh values from the node. Defaults to True.

        Returns:
            int: Signed r-shares corresponding to the provided vesting shares and vote parameters. Returns 0 if the computed r-shares are at-or-below the dust threshold when subtraction is enabled.
        """
        if isinstance(vests, Amount):
            vests = float(vests)
        used_power = self._calc_resulting_vote(
            current_power=voting_power, weight=vote_pct, power=HIVE_100_PERCENT
        )
        # calculate vote rshares
        rshares = int(math.copysign(vests * 1e6 * used_power / HIVE_100_PERCENT, vote_pct))
        if subtract_dust_threshold:
            if abs(rshares) <= self.get_dust_threshold(use_stored_data=use_stored_data):
                return 0
            rshares -= math.copysign(
                self.get_dust_threshold(use_stored_data=use_stored_data), vote_pct
            )
        # Apply curve adjustment relative to existing post rshares
        rshares = self._calc_vote_claim(int(rshares), post_rshares)
        return rshares

    def token_power_to_vests(
        self,
        token_power: float,
        timestamp: datetime | None = None,
        use_stored_data: bool = True,
    ) -> float:
        """Converts TokenPower to vests

        :param float token_power: Token power to convert
        :param datetime timestamp: (Optional) Can be used to calculate
            the conversion rate from the past
        """
        raise Exception("not implemented")

    def vests_to_token_power(
        self,
        vests: float | Amount,
        timestamp: int | None = None,
        use_stored_data: bool = True,
    ) -> float:
        """Converts vests to TokenPower

        :param amount.Amount vests/float vests: Vests to convert
        :param int timestamp: (Optional) Can be used to calculate
            the conversion rate from the past

        """
        raise Exception("not implemented")

    def get_token_per_mvest(
        self, time_stamp: int | datetime | None = None, use_stored_data: bool = True
    ) -> float:
        """Returns the MVEST to TOKEN ratio

        :param int time_stamp: (optional) if set, return an estimated
            TOKEN per MVEST ratio for the given time stamp. If unset the
            current ratio is returned (default). (can also be a datetime object)
        """
        raise Exception("not implemented")

    def rshares_to_token_backed_dollar(
        self,
        rshares: int,
        not_broadcasted_vote: bool = False,
        use_stored_data: bool = True,
    ) -> float:
        """Calculates the current HBD value of a vote"""
        raise Exception("not implemented")

    def token_power_to_token_backed_dollar(
        self,
        token_power: float,
        post_rshares: int = 0,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        not_broadcasted_vote: bool = True,
        use_stored_data: bool = True,
    ) -> float:
        """
        Estimate the token-backed-dollar (HBD-like) value that a vote from the given token power would yield.

        Calculates the expected payout (in the blockchain's backed token units) that a vote of `vote_pct` from an account
        with `voting_power` and `token_power` would contribute to a post with `post_rshares`. The estimate accounts for
        the vote rshares mechanics and the reduction of the reward pool when a not-yet-broadcast vote is included.

        Parameters:
            token_power (float): Voter's token power (in vest/token-equivalent units used by the chain).
            post_rshares (int, optional): Current rshares of the post being voted on. Defaults to 0.
            voting_power (int, optional): Voter's current voting power where 100% == HIVE_100_PERCENT (default full power).
            vote_pct (int, optional): Vote percentage where 100% == HIVE_100_PERCENT (default full vote).
            not_broadcasted_vote (bool, optional): If True, treat the vote as not yet broadcast (reduces available reward pool accordingly).
            use_stored_data (bool, optional): If True, prefer cached chain parameters; otherwise fetch fresh values.

        Returns:
            float: Estimated payout denominated in the backed token (e.g., HBD).

        Raises:
            Exception: Not implemented (function is a placeholder).
        """
        raise Exception("not implemented")

    def get_chain_properties(self, use_stored_data: bool = True) -> dict[str, Any]:
        """
        Return the witness-elected chain properties (median_props) used by the network.

        When cached data is allowed (use_stored_data=True) this reads from the instance cache
        (populated by refresh_data). Otherwise it fetches the latest witness schedule and
        returns its `median_props` object.

        Parameters:
            use_stored_data (bool): If True, return cached properties when available; if False,
                force fetching the current witness schedule.

        Returns:
            dict: The `median_props` mapping, e.g.:
                {
                    'account_creation_fee': '30.000 HIVE',
                    'maximum_block_size': 65536,
                    'hbd_interest_rate': 250
                }
        """
        if use_stored_data:
            self.refresh_data("witness_schedule")
            witness_schedule = self.data.get("witness_schedule")
            if witness_schedule:
                return witness_schedule["median_props"]
            return {}
        else:
            witness_schedule = self.get_witness_schedule(use_stored_data)
            return witness_schedule["median_props"] if witness_schedule else {}

    def get_witness_schedule(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Return witness elected chain properties"""
        if use_stored_data:
            self.refresh_data("witness_schedule")
            return self.data["witness_schedule"]

        if self.rpc is None:
            return None
        self.rpc.set_next_node_on_empty_reply(True)
        return self.rpc.get_witness_schedule()

    def get_config(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns internal chain configuration.

        :param bool use_stored_data: If True, the cached value is returned
        """
        if use_stored_data:
            self.refresh_data("config")
            config = self.data["config"]
        else:
            if self.rpc is None:
                return None
            self.rpc.set_next_node_on_empty_reply(True)
            config = self.rpc.get_config()
        return config

    @property
    def chain_params(self) -> dict[str, Any]:
        if self.offline or self.rpc is None:
            return known_chains["HIVE"]
        else:
            network = self.get_network()
            return network if network is not None else known_chains["HIVE"]

    @property
    def hardfork(self) -> int:
        if self.offline or self.rpc is None:
            versions = known_chains["HIVE"]["min_version"]
        else:
            hf_prop = self.get_hardfork_properties()
            if hf_prop and "current_hardfork_version" in hf_prop:
                versions = hf_prop["current_hardfork_version"]
            else:
                versions = self.get_blockchain_version()
        # Ensure versions is a string before splitting
        if isinstance(versions, dict):
            versions = versions.get("HIVE_BLOCKCHAIN_VERSION", "0.0.0")
        return int(str(versions).split(".")[1])

    @property
    def prefix(self) -> str:
        return self.chain_params["prefix"]

    @property
    def is_hive(self) -> bool:
        """
        Return True if the connected chain appears to be Hive.

        Checks the cached chain configuration and returns True when the key "HIVE_CHAIN_ID"
        is present; returns False if configuration is unavailable or the key is absent.
        """
        config = self.get_config(use_stored_data=True)
        if config is None:
            return False
        return "HIVE_CHAIN_ID" in config

    @property
    def is_steem(self) -> bool:
        """Deprecated compatibility flag; always False in Hive-only nectar."""
        return False

    def set_default_account(self, account: str) -> None:
        """
        Set the instance default account.

        If given an account name or an Account object, validate/resolve it (an Account is
        constructed with this blockchain instance) and store the account identifier in
        the instance configuration under "default_account". This makes the account the
        implicit default for subsequent operations that omit an explicit account.

        Parameters:
            account (str | Account): Account name or Account object to set as default.

        Notes:
            The Account constructor is invoked for validation; errors from account
            resolution/lookup may propagate.
        """
        Account(account, blockchain_instance=self)
        self.config["default_account"] = account

    def switch_blockchain(self, blockchain: str, update_nodes: bool = False) -> None:
        """
        Switch the instance to the specified blockchain (Hive only).

        If the requested blockchain is already the configured default and update_nodes is False, this is a no-op.
        When update_nodes is True, the node list is refreshed via NodeList.update_nodes() and the default nodes
        are replaced with the Hive node list. The instance's config["default_chain"] is updated and, if the
        instance is not offline, a reconnect is attempted.

        Parameters:
            blockchain (str): Target blockchain; must be "hive".
            update_nodes (bool): If True, refresh and replace the known node list before switching.
        """
        assert blockchain in ["hive"]
        if blockchain == self.config["default_chain"] and not update_nodes:
            return
        from nectar.nodelist import NodeList

        nodelist = NodeList()
        if update_nodes:
            nodelist.update_nodes()
        if blockchain == "hive":
            self.set_default_nodes(nodelist.get_hive_nodes())
        self.config["default_chain"] = blockchain
        if not self.offline:
            self.connect(node="")

    def set_password_storage(self, password_storage: str) -> None:
        """Set the password storage mode.

        When set to "no", the password has to be provided each time.
        When set to "environment" the password is taken from the
        UNLOCK variable

        When set to "keyring" the password is taken from the
        python keyring module. A wallet password can be stored with
        python -m keyring set nectar wallet password

        :param str password_storage: can be "no",
            "keyring" or "environment"

        """
        self.config["password_storage"] = password_storage

    def set_default_nodes(self, nodes: list[str] | str) -> None:
        """Set the default nodes to be used"""
        if bool(nodes):
            if isinstance(nodes, list):
                nodes = str(nodes)
            self.config["node"] = nodes
        else:
            self.config.delete("node")

    def get_default_nodes(self) -> list[str]:
        """Returns the default nodes"""
        if "node" in self.config:
            nodes = self.config["node"]
        elif "nodes" in self.config:
            nodes = self.config["nodes"]
        elif "node" in self.config.defaults:
            nodes = self.config["node"]
        elif "default_nodes" in self.config and bool(self.config["default_nodes"]):
            nodes = self.config["default_nodes"]
        else:
            nodes = []
        if isinstance(nodes, str) and nodes[0] == "[" and nodes[-1] == "]":
            nodes = ast.literal_eval(nodes)
        return nodes

    def move_current_node_to_front(self) -> None:
        """Returns the default node list, until the first entry
        is equal to the current working node url
        """
        node = self.get_default_nodes()
        if len(node) < 2:
            return
        if not isinstance(node, list):
            return
        offline = self.offline
        while not offline and self.rpc is not None and node[0] != self.rpc.url and len(node) > 1:
            node = node[1:] + [node[0]]
        self.set_default_nodes(node)

    def set_default_vote_weight(self, vote_weight: int) -> None:
        """Set the default vote weight to be used"""
        self.config["default_vote_weight"] = vote_weight

    def finalizeOp(
        self, ops: Any, account: Account | str, permission: str, **kwargs
    ) -> dict[str, Any]:
        """This method obtains the required private keys if present in
        the wallet, finalizes the transaction, signs it and
        broadacasts it

        :param ops: The operation (or list of operations) to
            broadcast
        :type ops: list, GrapheneObject
        :param Account account: The account that authorizes the
            operation
        :param string permission: The required permission for
            signing (active, owner, posting)
        :param TransactionBuilder append_to: This allows to provide an instance of
            TransactionBuilder (see :func:`BlockChainInstance.new_tx()`) to specify
            where to put a specific operation.

        .. note:: ``append_to`` is exposed to every method used in the
            BlockChainInstance class

        .. note::   If ``ops`` is a list of operation, they all need to be
                    signable by the same key! Thus, you cannot combine ops
                    that require active permission with ops that require
                    posting permission. Neither can you use different
                    accounts for different operations!

        .. note:: This uses :func:`BlockChainInstance.txbuffer` as instance of
            :class:`nectar.transactionbuilder.TransactionBuilder`.
            You may want to use your own txbuffer

        .. note:: when doing sign + broadcast, the trx_id is added to the returned dict

        """
        if self.offline:
            return {}
        if "append_to" in kwargs and kwargs["append_to"]:
            # Append to the append_to and return
            append_to = kwargs["append_to"]
            parent = append_to.get_parent()
            if not isinstance(append_to, (TransactionBuilder)):
                raise AssertionError()
            append_to.appendOps(ops)
            # Add the signer to the buffer so we sign the tx properly
            parent.appendSigner(account, permission)
            # This returns as we used append_to, it does NOT broadcast, or sign
            return append_to.get_parent()
            # Go forward to see what the other options do ...
        else:
            # Append to the default buffer
            self.txbuffer.appendOps(ops)

        # Add signing information, signer, sign and optionally broadcast
        if self.unsigned:
            # In case we don't want to sign anything
            self.txbuffer.addSigningInformation(account, permission)
            return self.txbuffer
        elif self.bundle:
            # In case we want to add more ops to the tx (bundle)
            self.txbuffer.appendSigner(account, permission)
            return self.txbuffer.json()
        else:
            # default behavior: sign + broadcast
            self.txbuffer.appendSigner(account, permission)
            ret_sign = self.txbuffer.sign()
            ret = self.txbuffer.broadcast()
            if ret_sign is not None:
                ret["trx_id"] = ret_sign.id
            return ret

    def sign(
        self,
        tx: dict[str, Any] | None = None,
        wifs: list[str] | str | None = None,
        reconstruct_tx: bool = True,
    ) -> dict[str, Any]:
        """
        Sign a transaction using provided WIFs or the wallet's missing signatures and return the signed transaction.

        If tx is provided, it is wrapped in a TransactionBuilder; otherwise the instance's current txbuffer is used. Provided wifs (single string or list) are appended before missing required signatures are added. If reconstruct_tx is False and the transaction already contains signatures, it will not be reconstructed.

        Parameters:
            tx (dict, optional): A transaction object to sign. If omitted, the active txbuffer is used.
            wifs (str | list[str], optional): One or more WIF private keys to use for signing. If not provided, keys from the wallet for any missing signatures are used.
            reconstruct_tx (bool, optional): If False, do not reconstruct an already-built transaction; existing signatures are preserved. Defaults to True.

        Returns:
            dict: The signed transaction JSON with an added "trx_id" field containing the transaction id.
        """
        if wifs is None:
            wifs = []
        if tx:
            txbuffer = TransactionBuilder(tx=tx, blockchain_instance=self)
        else:
            txbuffer = self.txbuffer
        txbuffer.appendWif(wifs)
        txbuffer.appendMissingSignatures()
        ret_sign = txbuffer.sign(reconstruct_tx=reconstruct_tx)
        ret = txbuffer.json()
        ret["trx_id"] = ret_sign.id
        return ret

    def broadcast(self, tx: dict[str, Any] | None = None, trx_id: bool = True) -> dict[str, Any]:
        """Broadcast a transaction to the Hive network

        :param tx tx: Signed transaction to broadcast
        :param bool trx_id: when True, the trx_id will be included into the return dict.

        """
        if tx:
            # If tx is provided, we broadcast the tx
            return TransactionBuilder(tx=tx, blockchain_instance=self).broadcast(trx_id=trx_id)
        else:
            return self.txbuffer.broadcast()

    def info(self, use_stored_data: bool = True) -> dict[str, Any] | None:
        """Returns the global properties"""
        return self.get_dynamic_global_properties(use_stored_data=use_stored_data)

    # -------------------------------------------------------------------------
    # Wallet stuff
    # -------------------------------------------------------------------------
    def newWallet(self, pwd: str) -> None:
        """Create a new wallet. This method is basically only calls
        :func:`nectar.wallet.Wallet.create`.

        :param str pwd: Password to use for the new wallet

        :raises WalletExists: if there is already a
            wallet created

        """
        return self.wallet.create(pwd)

    def unlock(self, *args, **kwargs) -> bool | None:
        """Unlock the internal wallet"""
        return self.wallet.unlock(*args, **kwargs)

    # -------------------------------------------------------------------------
    # Transaction Buffers
    # -------------------------------------------------------------------------
    @property
    def txbuffer(self) -> TransactionBuilder:
        """Returns the currently active tx buffer"""
        return self.tx()

    def tx(self) -> TransactionBuilder:
        """Returns the default transaction buffer"""
        return self._txbuffers[0]

    def new_tx(self, *args, **kwargs) -> TransactionBuilder:
        """Let's obtain a new txbuffer

        :returns: id of the new txbuffer
        :rtype: int
        """
        # Remove blockchain_instance from kwargs if it exists to avoid duplicate
        kwargs.pop("blockchain_instance", None)

        # Extract tx parameter if present (first positional argument)
        tx = args[0] if args else None

        # Pass self as blockchain_instance to avoid recursion
        builder = TransactionBuilder(tx, blockchain_instance=self, **kwargs)
        self._txbuffers.append(builder)
        return builder

    def clear(self) -> None:
        self._txbuffers = []
        # Base/Default proposal/tx buffers
        self.new_tx()
        # self.new_proposal()

    # -------------------------------------------------------------------------
    # Account related calls
    # -------------------------------------------------------------------------
    def claim_account(
        self, creator: str | Account | None = None, fee: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """
        Claim a subsidized account slot or pay the account-creation fee.

        When `fee` is "0 <TOKEN>" (default), the claim consumes an account slot paid from RC (resource credits)
        allowing a later call to `create_claimed_account` to create the account. Supplying a nonzero `fee`
        will pay the registration fee in the chain token (e.g., HIVE).

        Parameters:
            creator (str): Account that will pay or consume the claim (defaults to configured `default_account`).
            fee (str, optional): Fee as a string with asset symbol (e.g., "0 HIVE" or "3.000 HIVE"). If omitted, defaults to "0 <token_symbol>".

        Returns:
            The result of finalizeOp for the submitted Claim_account operation (signed/broadcast transaction or unsigned/buffered result, depending on instance configuration).

        Raises:
            ValueError: If no `creator` is provided and no `default_account` is configured.
        """
        fee = fee if fee is not None else "0 %s" % (self.token_symbol)
        if not creator and self.config["default_account"]:
            creator = self.config["default_account"]
        if not creator:
            raise ValueError(
                "Not creator account given. Define it with "
                + "creator=x, or set the default_account using hive-nectar"
            )
        assert creator is not None  # Type checker: creator is guaranteed not None here
        creator = Account(creator, blockchain_instance=self)  # type: ignore[assignment]
        op = {
            "fee": Amount(fee, blockchain_instance=self, json_str=True),
            "creator": creator["name"],
            "prefix": self.prefix,
            "json_str": True,
        }
        op = operations.Claim_account(**op)
        return self.finalizeOp(op, creator, "active", **kwargs)

    def create_claimed_account(
        self,
        account_name: str,
        creator: str | Account | None = None,
        owner_key: str | None = None,
        active_key: str | None = None,
        memo_key: str | None = None,
        posting_key: str | None = None,
        password: str | None = None,
        additional_owner_keys: list[str] | None = None,
        additional_active_keys: list[str] | None = None,
        additional_posting_keys: list[str] | None = None,
        additional_owner_accounts: list[str] | None = None,
        additional_active_accounts: list[str] | None = None,
        additional_posting_accounts: list[str] | None = None,
        storekeys: bool = True,
        store_owner_key: bool = False,
        json_meta: dict[str, Any] | None = None,
        combine_with_claim_account: bool = False,
        fee: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Create new claimed account on Hive

        The brainkey/password can be used to recover all generated keys
        (see :class:`nectargraphenebase.account` for more details.

        By default, this call will use ``default_account`` to
        register a new name ``account_name`` with all keys being
        derived from a new brain key that will be returned. The
        corresponding keys will automatically be installed in the
        wallet.

        .. warning:: Don't call this method unless you know what
                      you are doing! Be sure to understand what this
                      method does and where to find the private keys
                      for your account.

        .. note:: Please note that this imports private keys
                  (if password is present) into the wallet by
                  default when nobroadcast is set to False.
                  However, it **does not import the owner
                  key** for security reasons by default.
                  If you set store_owner_key to True, the
                  owner key is stored.
                  Do NOT expect to be able to recover it from
                  the wallet if you lose your password!

        .. note:: Account creations cost a fee that is defined by
                   the network. If you create an account, you will
                   need to pay for that fee!

        :param str account_name: (**required**) new account name
        :param str json_meta: Optional meta data for the account
        :param str owner_key: Main owner key
        :param str active_key: Main active key
        :param str posting_key: Main posting key
        :param str memo_key: Main memo_key
        :param str password: Alternatively to providing keys, one
                             can provide a password from which the
                             keys will be derived
        :param array additional_owner_keys:  Additional owner public keys
        :param array additional_active_keys: Additional active public keys
        :param array additional_posting_keys: Additional posting public keys
        :param array additional_owner_accounts: Additional owner account
            names
        :param array additional_active_accounts: Additional active account
            names
        :param bool storekeys: Store new keys in the wallet (default:
            ``True``)
        :param bool combine_with_claim_account: When set to True, a
            claim_account operation is additionally broadcasted
        :param str fee: When combine_with_claim_account is set to True,
            this parameter is used for the claim_account operation

        :param str creator: which account should pay the registration fee
                            (defaults to ``default_account``)
        :raises AccountExistsException: if the account already exists on
            the blockchain

        """
        fee = fee if fee is not None else "0 %s" % (self.token_symbol)
        if not creator and self.config["default_account"]:
            creator = self.config["default_account"]
        if not creator:
            raise ValueError(
                "Not creator account given. Define it with "
                + "creator=x, or set the default_account using hive-nectar"
            )
        if password and (owner_key or active_key or memo_key):
            raise ValueError("You cannot use 'password' AND provide keys!")

        try:
            Account(account_name, blockchain_instance=self)
            raise AccountExistsException
        except AccountDoesNotExistsException:
            pass

        creator = Account(creator, blockchain_instance=self)  # type: ignore[assignment]

        " Generate new keys from password"
        from nectargraphenebase.account import PasswordKey

        if password:
            active_key_obj = PasswordKey(account_name, password, role="active", prefix=self.prefix)
            owner_key_obj = PasswordKey(account_name, password, role="owner", prefix=self.prefix)
            posting_key_obj = PasswordKey(
                account_name, password, role="posting", prefix=self.prefix
            )
            memo_key_obj = PasswordKey(account_name, password, role="memo", prefix=self.prefix)
            active_pubkey = active_key_obj.get_public_key()
            owner_pubkey = owner_key_obj.get_public_key()
            posting_pubkey = posting_key_obj.get_public_key()
            memo_pubkey = memo_key_obj.get_public_key()
            active_privkey = active_key_obj.get_private_key()
            posting_privkey = posting_key_obj.get_private_key()
            owner_privkey = owner_key_obj.get_private_key()
            memo_privkey = memo_key_obj.get_private_key()
            # store private keys
            try:
                if storekeys and not self.nobroadcast:
                    if store_owner_key:
                        self.wallet.addPrivateKey(str(owner_privkey))
                    self.wallet.addPrivateKey(str(active_privkey))
                    self.wallet.addPrivateKey(str(memo_privkey))
                    self.wallet.addPrivateKey(str(posting_privkey))
            except ValueError as e:
                log.info(str(e))

        elif owner_key and active_key and memo_key and posting_key:
            active_pubkey = PublicKey(active_key, prefix=self.prefix)
            owner_pubkey = PublicKey(owner_key, prefix=self.prefix)
            posting_pubkey = PublicKey(posting_key, prefix=self.prefix)
            memo_pubkey = PublicKey(memo_key, prefix=self.prefix)
        else:
            raise ValueError("Call incomplete! Provide either a password or public keys!")
        owner = format(owner_pubkey, self.prefix)
        active = format(active_pubkey, self.prefix)
        posting = format(posting_pubkey, self.prefix)
        memo = format(memo_pubkey, self.prefix)

        owner_key_authority = [[owner, 1]]
        active_key_authority = [[active, 1]]
        posting_key_authority = [[posting, 1]]
        owner_accounts_authority = []
        active_accounts_authority = []
        posting_accounts_authority = []

        additional_owner_keys = additional_owner_keys or []
        additional_active_keys = additional_active_keys or []
        additional_posting_keys = additional_posting_keys or []
        additional_owner_accounts = additional_owner_accounts or []
        additional_active_accounts = additional_active_accounts or []
        additional_posting_accounts = additional_posting_accounts or []

        # additional authorities
        for k in additional_owner_keys:
            owner_key_authority.append([k, 1])
        for k in additional_active_keys:
            active_key_authority.append([k, 1])
        for k in additional_posting_keys:
            posting_key_authority.append([k, 1])

        for k in additional_owner_accounts:
            addaccount = Account(k, blockchain_instance=self)
            owner_accounts_authority.append([addaccount["name"], 1])
        for k in additional_active_accounts:
            addaccount = Account(k, blockchain_instance=self)
            active_accounts_authority.append([addaccount["name"], 1])
        for k in additional_posting_accounts:
            addaccount = Account(k, blockchain_instance=self)
            posting_accounts_authority.append([addaccount["name"], 1])
        if combine_with_claim_account:
            op = {
                "fee": Amount(fee, blockchain_instance=self),
                "creator": creator["name"],
                "prefix": self.prefix,
            }
            op = operations.Claim_account(**op)
            ops = [op]
        op = {
            "creator": creator["name"],
            "new_account_name": account_name,
            "owner": {
                "account_auths": owner_accounts_authority,
                "key_auths": owner_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "active": {
                "account_auths": active_accounts_authority,
                "key_auths": active_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "posting": {
                "account_auths": posting_accounts_authority,
                "key_auths": posting_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "memo_key": memo,
            "json_metadata": json_meta or {},
            "prefix": self.prefix,
        }
        op = operations.Create_claimed_account(**op)
        if combine_with_claim_account:
            ops.append(op)
            return self.finalizeOp(ops, creator, "active", **kwargs)
        else:
            return self.finalizeOp(op, creator, "active", **kwargs)

    def create_account(
        self,
        account_name: str,
        creator: str | Account | None = None,
        owner_key=None,
        active_key=None,
        memo_key=None,
        posting_key=None,
        password=None,
        additional_owner_keys=[],
        additional_active_keys=[],
        additional_posting_keys=[],
        additional_owner_accounts=[],
        additional_active_accounts=[],
        additional_posting_accounts=[],
        storekeys=True,
        store_owner_key=False,
        json_meta=None,
        **kwargs,
    ):
        """Create new account on Hive

        The brainkey/password can be used to recover all generated keys
        (see :class:`nectargraphenebase.account` for more details.

        By default, this call will use ``default_account`` to
        register a new name ``account_name`` with all keys being
        derived from a new brain key that will be returned. The
        corresponding keys will automatically be installed in the
        wallet.

        .. warning:: Don't call this method unless you know what
                      you are doing! Be sure to understand what this
                      method does and where to find the private keys
                      for your account.

        .. note:: Please note that this imports private keys
                  (if password is present) into the wallet by
                  default when nobroadcast is set to False.
                  However, it **does not import the owner
                  key** for security reasons by default.
                  If you set store_owner_key to True, the
                  owner key is stored.
                  Do NOT expect to be able to recover it from
                  the wallet if you lose your password!

        .. note:: Account creations cost a fee that is defined by
                   the network. If you create an account, you will
                   need to pay for that fee!

        :param str account_name: (**required**) new account name
        :param str json_meta: Optional meta data for the account
        :param str owner_key: Main owner key
        :param str active_key: Main active key
        :param str posting_key: Main posting key
        :param str memo_key: Main memo_key
        :param str password: Alternatively to providing keys, one
                             can provide a password from which the
                             keys will be derived
        :param array additional_owner_keys:  Additional owner public keys
        :param array additional_active_keys: Additional active public keys
        :param array additional_posting_keys: Additional posting public keys
        :param array additional_owner_accounts: Additional owner account
            names
        :param array additional_active_accounts: Additional active account
            names
        :param bool storekeys: Store new keys in the wallet (default:
            ``True``)

        :param str creator: which account should pay the registration fee
                            (defaults to ``default_account``)
        :raises AccountExistsException: if the account already exists on
            the blockchain

        """
        if not creator and self.config["default_account"]:
            creator = self.config["default_account"]
        if not creator:
            raise ValueError(
                "Not creator account given. Define it with "
                + "creator=x, or set the default_account using hive-nectar"
            )
        if password and (owner_key or active_key or memo_key):
            raise ValueError("You cannot use 'password' AND provide keys!")

        try:
            Account(account_name, blockchain_instance=self)
            raise AccountExistsException
        except AccountDoesNotExistsException:
            pass

        creator = Account(creator, blockchain_instance=self)  # type: ignore[assignment]

        " Generate new keys from password"
        from nectargraphenebase.account import PasswordKey

        if password:
            active_key_obj = PasswordKey(account_name, password, role="active", prefix=self.prefix)
            owner_key_obj = PasswordKey(account_name, password, role="owner", prefix=self.prefix)
            posting_key_obj = PasswordKey(
                account_name, password, role="posting", prefix=self.prefix
            )
            memo_key_obj = PasswordKey(account_name, password, role="memo", prefix=self.prefix)
            active_pubkey = active_key_obj.get_public_key()
            owner_pubkey = owner_key_obj.get_public_key()
            posting_pubkey = posting_key_obj.get_public_key()
            memo_pubkey = memo_key_obj.get_public_key()
            active_privkey = active_key_obj.get_private_key()
            posting_privkey = posting_key_obj.get_private_key()
            owner_privkey = owner_key_obj.get_private_key()
            memo_privkey = memo_key_obj.get_private_key()
            # store private keys
            try:
                if storekeys and not self.nobroadcast:
                    if store_owner_key:
                        self.wallet.addPrivateKey(str(owner_privkey))
                    self.wallet.addPrivateKey(str(active_privkey))
                    self.wallet.addPrivateKey(str(memo_privkey))
                    self.wallet.addPrivateKey(str(posting_privkey))
            except ValueError as e:
                log.info(str(e))

        elif owner_key and active_key and memo_key and posting_key:
            active_pubkey = PublicKey(active_key, prefix=self.prefix)
            owner_pubkey = PublicKey(owner_key, prefix=self.prefix)
            posting_pubkey = PublicKey(posting_key, prefix=self.prefix)
            memo_pubkey = PublicKey(memo_key, prefix=self.prefix)
        else:
            raise ValueError("Call incomplete! Provide either a password or public keys!")
        owner = format(owner_pubkey, self.prefix)
        active = format(active_pubkey, self.prefix)
        posting = format(posting_pubkey, self.prefix)
        memo = format(memo_pubkey, self.prefix)

        owner_key_authority = [[owner, 1]]
        active_key_authority = [[active, 1]]
        posting_key_authority = [[posting, 1]]
        owner_accounts_authority = []
        active_accounts_authority = []
        posting_accounts_authority = []

        # additional authorities
        for k in additional_owner_keys:
            owner_key_authority.append([k, 1])
        for k in additional_active_keys:
            active_key_authority.append([k, 1])
        for k in additional_posting_keys:
            posting_key_authority.append([k, 1])

        for k in additional_owner_accounts:
            addaccount = Account(k, blockchain_instance=self)
            owner_accounts_authority.append([addaccount["name"], 1])
        for k in additional_active_accounts:
            addaccount = Account(k, blockchain_instance=self)
            active_accounts_authority.append([addaccount["name"], 1])
        for k in additional_posting_accounts:
            addaccount = Account(k, blockchain_instance=self)
            posting_accounts_authority.append([addaccount["name"], 1])

        props = self.get_chain_properties()
        try:
            hardfork_version = int(self.hardfork)
        except (ValueError, TypeError):
            hardfork_version = 0
        if hardfork_version >= 20:
            required_fee = Amount(props["account_creation_fee"], blockchain_instance=self)
        else:
            required_fee = Amount(props["account_creation_fee"], blockchain_instance=self) * 30
        op = {
            "fee": required_fee,
            "creator": creator["name"],
            "new_account_name": account_name,
            "owner": {
                "account_auths": owner_accounts_authority,
                "key_auths": owner_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "active": {
                "account_auths": active_accounts_authority,
                "key_auths": active_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "posting": {
                "account_auths": posting_accounts_authority,
                "key_auths": posting_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "memo_key": memo,
            "json_metadata": json_meta or {},
            "prefix": self.prefix,
            "json_str": True,
        }
        op = operations.Account_create(**op)
        return self.finalizeOp(op, creator, "active", **kwargs)

    def update_account(
        self,
        account: str | Account | None = None,
        owner_key=None,
        active_key=None,
        memo_key=None,
        posting_key=None,
        password=None,
        additional_owner_keys: list[str] | None = None,
        additional_active_keys: list[str] | None = None,
        additional_posting_keys: list[str] | None = None,
        additional_owner_accounts: list[str] | None = None,
        additional_active_accounts: list[str] | None = None,
        additional_posting_accounts: list[str] | None = None,
        storekeys: bool = True,
        store_owner_key: bool = False,
        json_meta=None,
        **kwargs,
    ):
        """Update account

        The brainkey/password can be used to recover all generated keys
        (see :class:`nectargraphenebase.account` for more details.

        The
        corresponding keys will automatically be installed in the
        wallet.

        .. warning:: Don't call this method unless you know what
                      you are doing! Be sure to understand what this
                      method does and where to find the private keys
                      for your account.

        .. note:: Please note that this imports private keys
                  (if password is present) into the wallet by
                  default when nobroadcast is set to False.
                  However, it **does not import the owner
                  key** for security reasons by default.
                  If you set store_owner_key to True, the
                  owner key is stored.
                  Do NOT expect to be able to recover it from
                  the wallet if you lose your password!

        :param str account_name: (**required**) account name
        :param str json_meta: Optional updated meta data for the account
        :param str owner_key: Main owner (public) key
        :param str active_key: Main active (public) key
        :param str posting_key: Main posting (public) key
        :param str memo_key: Main memo (public) key
        :param str password: Alternatively to providing keys, one
                             can provide a password from which the
                             keys will be derived
        :param array additional_owner_keys:  Additional owner public keys
        :param array additional_active_keys: Additional active public keys
        :param array additional_posting_keys: Additional posting public keys
        :param array additional_owner_accounts: Additional owner account
            names
        :param array additional_active_accounts: Additional active account
            names
        :param bool storekeys: Store new keys in the wallet (default:
            ``True``)
        :raises AccountExistsException: if the account already exists on
            the blockchain

        """
        if password and (owner_key or active_key or memo_key):
            raise ValueError("You cannot use 'password' AND provide keys!")

        account = Account(account, blockchain_instance=self)  # type: ignore[assignment]

        " Generate new keys from password"
        from nectargraphenebase.account import PasswordKey

        if password:
            active_key = PasswordKey(account["name"], password, role="active", prefix=self.prefix)
            owner_key = PasswordKey(account["name"], password, role="owner", prefix=self.prefix)
            posting_key = PasswordKey(account["name"], password, role="posting", prefix=self.prefix)
            memo_key = PasswordKey(account["name"], password, role="memo", prefix=self.prefix)
            active_pubkey = active_key.get_public_key()
            owner_pubkey = owner_key.get_public_key()
            posting_pubkey = posting_key.get_public_key()
            memo_pubkey = memo_key.get_public_key()
            active_privkey = active_key.get_private_key()
            posting_privkey = posting_key.get_private_key()
            owner_privkey = owner_key.get_private_key()
            memo_privkey = memo_key.get_private_key()
            # store private keys
            try:
                if storekeys and not self.nobroadcast:
                    if store_owner_key:
                        self.wallet.addPrivateKey(str(owner_privkey))
                    self.wallet.addPrivateKey(str(active_privkey))
                    self.wallet.addPrivateKey(str(memo_privkey))
                    self.wallet.addPrivateKey(str(posting_privkey))
            except ValueError as e:
                log.info(str(e))

        elif owner_key and active_key and memo_key and posting_key:
            active_pubkey = PublicKey(active_key, prefix=self.prefix)
            owner_pubkey = PublicKey(owner_key, prefix=self.prefix)
            posting_pubkey = PublicKey(posting_key, prefix=self.prefix)
            memo_pubkey = PublicKey(memo_key, prefix=self.prefix)
        else:
            raise ValueError("Call incomplete! Provide either a password or public keys!")
        owner = format(owner_pubkey, self.prefix)
        active = format(active_pubkey, self.prefix)
        posting = format(posting_pubkey, self.prefix)
        memo = format(memo_pubkey, self.prefix)

        owner_key_authority = [[owner, 1]]
        active_key_authority = [[active, 1]]
        posting_key_authority = [[posting, 1]]
        if additional_owner_accounts is None:
            owner_accounts_authority = account["owner"]["account_auths"]
        else:
            owner_accounts_authority = []
        if additional_active_accounts is None:
            active_accounts_authority = account["active"]["account_auths"]
        else:
            active_accounts_authority = []
        if additional_posting_accounts is None:
            posting_accounts_authority = account["posting"]["account_auths"]
        else:
            posting_accounts_authority = []

        # additional authorities
        if additional_owner_keys is not None:
            for k in additional_owner_keys:
                owner_key_authority.append([k, 1])
        if additional_active_keys is not None:
            for k in additional_active_keys:
                active_key_authority.append([k, 1])
        if additional_posting_keys is not None:
            for k in additional_posting_keys:
                posting_key_authority.append([k, 1])

        if additional_owner_accounts is not None:
            for k in additional_owner_accounts:
                addaccount = Account(k, blockchain_instance=self)
                owner_accounts_authority.append([addaccount["name"], 1])
        if additional_active_accounts is not None:
            for k in additional_active_accounts:
                addaccount = Account(k, blockchain_instance=self)
                active_accounts_authority.append([addaccount["name"], 1])
        if additional_posting_accounts is not None:
            for k in additional_posting_accounts:
                addaccount = Account(k, blockchain_instance=self)
                posting_accounts_authority.append([addaccount["name"], 1])
        op = {
            "account": account["name"],
            "owner": {
                "account_auths": owner_accounts_authority,
                "key_auths": owner_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "active": {
                "account_auths": active_accounts_authority,
                "key_auths": active_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "posting": {
                "account_auths": posting_accounts_authority,
                "key_auths": posting_key_authority,
                "address_auths": [],
                "weight_threshold": 1,
            },
            "memo_key": memo,
            "json_metadata": json_meta or account["json_metadata"],
            "prefix": self.prefix,
        }
        op = operations.Account_update(**op)
        return self.finalizeOp(op, account, "owner", **kwargs)

    def witness_set_properties(
        self, wif: str, owner: str | Account, props: dict[str, Any]
    ) -> dict[str, Any]:
        """Set witness properties

        :param str wif: Private signing key
        :param dict props: Properties
        :param str owner: witness account name

        Properties:::

            {
                "account_creation_fee": x,
                "account_subsidy_budget": x,
                "account_subsidy_decay": x,
                "maximum_block_size": x,
                "url": x,
                "sbd_exchange_rate": x,
                "sbd_interest_rate": x,
                "new_signing_key": x
            }

        """

        owner = Account(owner, blockchain_instance=self)

        try:
            PrivateKey(wif, prefix=self.prefix)
        except Exception as e:
            raise e
        props_list = [["key", repr(PrivateKey(wif, prefix=self.prefix).pubkey)]]
        for k in props:
            props_list.append([k, props[k]])
        op = operations.Witness_set_properties(
            {
                "owner": owner["name"],
                "props": props_list,
                "prefix": self.prefix,
                "json_str": True,
            }
        )
        tb = TransactionBuilder(blockchain_instance=self)
        tb.appendOps([op])
        tb.appendWif(wif)
        tb.sign()
        return tb.broadcast()

    def witness_update(
        self,
        signing_key: str,
        url: str,
        props: dict[str, Any],
        account: str | Account | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create or update a witness (register or modify a block producer).

        Creates a Witness_update operation for the given account with the provided signing key, node URL, and witness properties, then finalizes (signs/broadcasts or returns) the operation via the transaction pipeline.

        Parameters:
            signing_key (str): Witness block signing public key (must be valid for the chain prefix).
            url (str): URL for the witness (website or endpoint).
            props (dict): Witness properties, e.g.:
                {
                    "account_creation_fee": "3.000 HIVE",
                    "maximum_block_size": 65536,
                    "hbd_interest_rate": 0,
                }
                The "account_creation_fee" value will be converted to an Amount if present.
            account (str, optional): Witness account name. If omitted, the instance default_account config is used.

        Returns:
            The value returned by finalizeOp (typically a transaction/broadcast result or a transaction builder when unsigned/bundled).

        Raises:
            ValueError: If no account is provided or resolvable.
            Exception: If the signing_key is not a valid public key for the chain prefix (propagates the underlying PublicKey error).
        """
        if not account and self.config["default_account"]:
            account = self.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")

        account = Account(account, blockchain_instance=self)  # type: ignore[assignment]

        try:
            PublicKey(signing_key, prefix=self.prefix)
        except Exception as e:
            raise e
        if "account_creation_fee" in props:
            props["account_creation_fee"] = Amount(
                props["account_creation_fee"], blockchain_instance=self, json_str=True
            )
        op = operations.Witness_update(
            **{
                "owner": account["name"],
                "url": url,
                "block_signing_key": signing_key,
                "props": props,
                "fee": Amount(0, self.token_symbol, blockchain_instance=self, json_str=True),
                "prefix": self.prefix,
                "json_str": True,
            }
        )
        return self.finalizeOp(op, account, "active", **kwargs)

    def update_proposal_votes(
        self,
        proposal_ids: list[int],
        approve: bool,
        account: str | Account | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update proposal votes

        :param list proposal_ids: list of proposal ids
        :param bool approve: True/False
        :param str account: (optional) witness account name


        """
        if not account and self.config["default_account"]:
            account = self.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")

        account = Account(account, blockchain_instance=self)  # type: ignore[assignment]
        if not isinstance(proposal_ids, list):
            proposal_ids = [proposal_ids]

        op = operations.Update_proposal_votes(
            **{
                "voter": account["name"],
                "proposal_ids": proposal_ids,
                "approve": approve,
                "prefix": self.prefix,
            }
        )
        return self.finalizeOp(op, account, "active", **kwargs)

    def _test_weights_treshold(self, authority: dict[str, Any]) -> bool:
        """This method raises an error if the threshold of an authority cannot
        be reached by the weights.

        :param dict authority: An authority of an account
        :raises ValueError: if the threshold is set too high
        """
        weights = 0
        for a in authority["account_auths"]:
            weights += int(a[1])
        for a in authority["key_auths"]:
            weights += int(a[1])
        if authority["weight_threshold"] > weights:
            raise ValueError("Threshold too restrictive!")
        if authority["weight_threshold"] == 0:
            raise ValueError("Cannot have threshold of 0")
        return True

    def custom_json(
        self,
        id: str,
        json_data: Any,
        required_auths: list[str] = [],
        required_posting_auths: list[str] = [],
        **kwargs,
    ) -> dict[str, Any]:
        """
        Create and submit a Custom_json operation.

        Parameters:
            id (str): Identifier for the custom JSON (max 32 bytes).
            json_data: JSON-serializable payload to include in the operation.
            required_auths (list): Accounts that must authorize with active permission. If non-empty, the operation will be finalized using active permission.
            required_posting_auths (list): Accounts that must authorize with posting permission. Used when `required_auths` is empty.

        Returns:
            The result returned by finalizeOp (signed and/or broadcast transaction), which may vary based on the instance configuration (e.g., unsigned, nobroadcast, bundle).

        Raises:
            Exception: If neither `required_auths` nor `required_posting_auths` contains an account.
        """
        account = None
        if len(required_auths):
            account = required_auths[0]
        elif len(required_posting_auths):
            account = required_posting_auths[0]
        else:
            raise Exception("At least one account needs to be specified")
        account = Account(account, full=False, blockchain_instance=self)
        op = operations.Custom_json(
            **{
                "json": json_data,
                "required_auths": required_auths,
                "required_posting_auths": required_posting_auths,
                "id": id,
                "prefix": self.prefix,
                "appbase": True,
            }
        )
        if len(required_auths) > 0:
            return self.finalizeOp(op, account, "active", **kwargs)
        else:
            return self.finalizeOp(op, account, "posting", **kwargs)

    def post(
        self,
        title: str,
        body: str,
        author: str | None = None,
        permlink: str | None = None,
        reply_identifier: str | None = None,
        json_metadata: dict[str, Any] | None = None,
        comment_options: dict[str, Any] | None = None,
        community: str | None = None,
        app: str | None = None,
        tags: list[str] | None = None,
        beneficiaries: list[dict[str, Any]] | None = None,
        self_vote: bool = False,
        parse_body: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Create a new post.
        If this post is intended as a reply/comment, `reply_identifier` needs
        to be set with the identifier of the parent post/comment (eg.
        `@author/permlink`).
        Optionally you can also set json_metadata, comment_options and upvote
        the newly created post as an author.
        Setting category, tags or community will override the values provided
        in json_metadata and/or comment_options where appropriate.

        :param str title: Title of the post
        :param str body: Body of the post/comment
        :param str author: Account are you posting from
        :param str permlink: Manually set the permlink (defaults to None).
            If left empty, it will be derived from title automatically.
        :param str reply_identifier: Identifier of the parent post/comment (only
            if this post is a reply/comment).
        :param json_metadata: JSON meta object that can be attached to
            the post.
        :type json_metadata: str, dict
        :param dict comment_options: JSON options object that can be
            attached to the post.

        Example::

            comment_options = {
                'max_accepted_payout': '1000000.000 HBD',
                'percent_hbd': 10000,
                'allow_votes': True,
                'allow_curation_rewards': True,
                'extensions': [[0, {
                    'beneficiaries': [
                        {'account': 'account1', 'weight': 5000},
                        {'account': 'account2', 'weight': 5000},
                    ]}
                ]]
            }

        :param str community: (Optional) Name of the community we are posting
            into. This will also override the community specified in
            `json_metadata` and the category
        :param str app: (Optional) Name of the app which are used for posting
            when not set, nectar/<version> is used
        :param tags: (Optional) A list of tags to go with the
            post. This will also override the tags specified in
            `json_metadata`. The first tag will be used as a 'category' when community is not specified. If
            provided as a string, it should be space separated.
        :type tags: str, list
        :param list beneficiaries: (Optional) A list of beneficiaries
            for posting reward distribution. This argument overrides
            beneficiaries as specified in `comment_options`.

        For example, if we would like to split rewards between account1 and
        account2::

            beneficiaries = [
                {'account': 'account1', 'weight': 5000},
                {'account': 'account2', 'weight': 5000}
            ]

        :param bool self_vote: (Optional) Upvote the post as author, right after
            posting.
        :param bool parse_body: (Optional) When set to True, all mentioned users,
            used links and images are put into users, links and images array inside
            json_metadata. This will override provided links, images and users inside
            json_metadata. Hashtags will added to tags until its length is below five entries.

        """

        # prepare json_metadata
        json_metadata = json_metadata or {}
        if isinstance(json_metadata, str):
            json_metadata = json.loads(json_metadata)

        # override the community
        if community:
            json_metadata.update({"community": community})
        if app:
            json_metadata.update({"app": app})
        elif "app" not in json_metadata:
            json_metadata.update({"app": "nectar/%s" % (nectar_version)})

        if not author and self.config["default_account"]:
            author = self.config["default_account"]
        if not author:
            raise ValueError("You need to provide an account")
        account = Account(author, blockchain_instance=self)
        # deal with the category and tags
        if isinstance(tags, str):
            tags = list({_f for _f in (re.split(r"[\W_]", tags)) if _f})

        tags = tags or json_metadata.get("tags", [])

        if parse_body:

            def get_urls(mdstring: str) -> list[str]:
                urls = re.findall(r'http[s]*://[^\s"><\)\(]+', mdstring)
                return list(dict.fromkeys(urls))

            def get_users(mdstring: str) -> list[str]:
                """
                Extract usernames mentioned in a Markdown string.

                Searches mdstring for @-mentions (ASCII @ or fullwidth ＠) and returns the usernames found in order of appearance.
                Usernames must start with a lowercase ASCII letter, may contain lowercase letters, digits, hyphens, dots (including fullwidth dot), and must end with a letter or digit.

                Parameters:
                    mdstring (str): Text to scan for @-mentions.

                Returns:
                    list[str]: List of matched username strings in the order they were found (may contain duplicates).
                """
                users = []
                for u in re.findall(
                    r"(^|[^a-zA-Z0-9_!#$%&*@＠／]|(^|[^a-zA-Z0-9_+~.-／#]))[@＠]([a-z][-．a-z\d]+[a-z\d])",
                    mdstring,
                ):
                    users.append(list(u)[-1])
                return users

            def get_hashtags(mdstring: str) -> list[str]:
                hashtags = []
                for t in re.findall(r"(^|\s)(#[-a-z\d]+)", mdstring):
                    hashtags.append(list(t)[-1])
                return hashtags

            users = []
            image = []
            links = []
            for url in get_urls(body):
                img_exts = [".jpg", ".png", ".gif", ".svg", ".jpeg"]
                if os.path.splitext(url)[1].lower() in img_exts:
                    image.append(url)
                elif url[:25] == "https://images.hive.blog/":
                    image.append(url)
                else:
                    links.append(url)
            users = get_users(body)
            hashtags = get_hashtags(body)
            users = list(set(users).difference({author}))
            if len(users) > 0:
                json_metadata.update({"users": users})
            if len(image) > 0:
                json_metadata.update({"image": image})
            if len(links) > 0:
                json_metadata.update({"links": links})
            if len(tags) < 5:
                for i in range(5 - len(tags)):
                    if len(hashtags) > i:
                        tags.append(hashtags[i])

        if tags:
            # first tag should be a category
            if community is None:
                category = tags[0]
            else:
                category = community
            json_metadata.update({"tags": tags})
        elif community:
            category = community
        else:
            category = None

        # can't provide a category while replying to a post
        if reply_identifier and category:
            category = None

        # deal with replies/categories
        if reply_identifier:
            parent_author, parent_permlink = resolve_authorperm(reply_identifier)
            if not permlink:
                permlink = derive_permlink(title, parent_permlink)
        elif category:
            parent_permlink = sanitize_permlink(category)
            parent_author = ""
            if not permlink:
                permlink = derive_permlink(title)
        else:
            parent_author = ""
            parent_permlink = ""
            if not permlink:
                permlink = derive_permlink(title)

        post_op = operations.Comment(
            **{
                "parent_author": parent_author.strip(),
                "parent_permlink": parent_permlink.strip(),
                "author": account["name"] or "",
                "permlink": permlink.strip() if permlink else "",
                "title": title.strip() if title else "",
                "body": body,
                "json_metadata": json_metadata,
            }
        )
        ops = [post_op]

        # if comment_options are used, add a new op to the transaction
        if comment_options or beneficiaries:
            comment_op = self._build_comment_options_op(
                account["name"] or "",
                permlink or "",
                comment_options or {},
                beneficiaries or [],
            )
            ops.append(comment_op)

        if self_vote:
            vote_op = operations.Vote(
                **{
                    "voter": account["name"] or "",
                    "author": account["name"] or "",
                    "permlink": permlink or "",
                    "weight": HIVE_100_PERCENT,
                }
            )
            ops.append(vote_op)

        return self.finalizeOp(ops, account, "posting", **kwargs)

    def vote(
        self,
        weight: float,
        identifier: str,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Cast a vote on a post.

        Parameters:
            weight (float): Vote weight in percent, range -100.0 to 100.0. This is
                converted to the chain's internal weight units (multiplied by
                HIVE_1_PERCENT) and clamped to the allowed range.
            identifier (str): Post identifier in the form "@author/permlink".
            account (str, optional): Name of the account to use for voting. If not
                provided, the instance's `default_account` from config is used. A
                ValueError is raised if no account can be determined.

        Returns:
            The result from finalizeOp (operation signing/broadcast buffer or broadcast
            response) after creating a Vote operation using posting permission.
        """
        if not account:
            if "default_account" in self.config:
                account = self.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self)  # type: ignore[assignment]

        [post_author, post_permlink] = resolve_authorperm(identifier)

        vote_weight = int(float(weight) * HIVE_1_PERCENT)
        if vote_weight > HIVE_100_PERCENT:
            vote_weight = HIVE_100_PERCENT
        if vote_weight < -HIVE_100_PERCENT:
            vote_weight = -HIVE_100_PERCENT

        op = operations.Vote(
            **{
                "voter": account["name"] or "",
                "author": post_author,
                "permlink": post_permlink,
                "weight": vote_weight,
            }
        )

        return self.finalizeOp(op, account, "posting", **kwargs)

    def comment_options(
        self,
        options: dict[str, Any],
        identifier: str,
        beneficiaries: list[dict[str, Any]] = [],
        account: str | Account | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Set comment/post options for a post (Comment_options operation) and submit the operation.

        Parameters:
            options (dict): Comment options to set. Common keys include:
                - max_accepted_payout (str): e.g. "1000000.000 HBD"
                - percent_hbd (int): e.g. 10000 for 100%
                - allow_votes (bool)
                - allow_curation_rewards (bool)
                Other valid keys accepted by the chain's Comment_options operation are supported.
            identifier (str): Post identifier in the form "author/permlink" or a permlink for the default author.
            beneficiaries (list): Optional list of beneficiaries (each entry typically a dict with `account` and `weight`).
            account (str): Account that authorizes this operation; defaults to the instance's `default_account` if not provided.
            **kwargs: Additional keyword arguments forwarded to finalizeOp (e.g., broadcast/signing options).

        Returns:
            The result of finalizeOp for the created Comment_options operation (signed/broadcasted transaction or unsigned buffer), depending on instance configuration.

        Raises:
            ValueError: If no account is provided and no default account is configured.
        """
        if not account and self.config["default_account"]:
            account = self.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self)  # type: ignore[assignment]
        author, permlink = resolve_authorperm(identifier)
        op = self._build_comment_options_op(author, permlink, options, beneficiaries)
        return self.finalizeOp(op, account, "posting", **kwargs)

    def _build_comment_options_op(
        self,
        author: str,
        permlink: str,
        options: dict[str, Any],
        beneficiaries: list[dict[str, Any]],
    ) -> Any:
        """
        Build and return a Comment_options operation for a post, validating and normalizing provided options and beneficiaries.

        Parameters:
            author (str): The post author's account name.
            permlink (str): The permlink of the post to set options for.
            options (dict): Optional comment options; supported keys include
                "max_accepted_payout", "percent_hbd", "allow_votes",
                "allow_curation_rewards", and "extensions". Keys not listed are removed.
            beneficiaries (list): Optional list of beneficiary dicts, each with
                "account" (str) and optional "weight" (int, 1..HIVE_100_PERCENT). If provided,
                beneficiaries override any beneficiaries in `options`.

        Returns:
            operations.Comment_options: A Comment_options operation ready to be appended to a transaction.

        Raises:
            ValueError: If a beneficiary is missing the "account" field, has an account name
                longer than 16 characters, has an invalid weight (not in 1..HIVE_100_PERCENT),
                or if the sum of beneficiary weights exceeds HIVE_100_PERCENT.
        """
        options = remove_from_dict(
            options or {},
            [
                "max_accepted_payout",
                "percent_hbd",
                "allow_votes",
                "allow_curation_rewards",
                "extensions",
            ],
            keep_keys=True,
        )
        # override beneficiaries extension
        if beneficiaries:
            # validate schema
            # or just simply vo.Schema([{'account': str, 'weight': int}])

            weight_sum = 0
            for b in beneficiaries:
                if "account" not in b:
                    raise ValueError("beneficiaries need an account field!")
                if "weight" not in b:
                    b["weight"] = HIVE_100_PERCENT
                if len(b["account"]) > 16:
                    raise ValueError("beneficiaries error, account name length >16!")
                if b["weight"] < 1 or b["weight"] > HIVE_100_PERCENT:
                    raise ValueError("beneficiaries error, 1<=weight<=%s!" % (HIVE_100_PERCENT))
                weight_sum += b["weight"]

            if weight_sum > HIVE_100_PERCENT:
                raise ValueError("beneficiaries exceed total weight limit %s" % HIVE_100_PERCENT)

            options["beneficiaries"] = beneficiaries

        default_max_payout = Amount(
            "1000000.000 %s" % (self.backed_token_symbol), blockchain_instance=self
        )
        comment_op = operations.Comment_options(
            **{
                "author": author,
                "permlink": permlink,
                "max_accepted_payout": options.get("max_accepted_payout", default_max_payout),
                "percent_hbd": int(options.get("percent_hbd", HIVE_100_PERCENT)),
                "allow_votes": options.get("allow_votes", True),
                "allow_curation_rewards": options.get("allow_curation_rewards", True),
                "extensions": options.get("extensions", []),
                "beneficiaries": options.get("beneficiaries", []),
                "prefix": self.prefix,
            }
        )
        return comment_op

    def get_api_methods(self) -> list[str]:
        """
        Return the list of all JSON-RPC API methods supported by the connected node.

        Returns:
            list: Method names (strings) provided by the node's JSON-RPC API.
        """
        if self.rpc is None:
            raise RuntimeError("RPC connection not established")
        return self.rpc.get_methods()

    def get_apis(self) -> list[str]:
        """Returns all enabled apis"""
        api_methods = self.get_api_methods()
        api_list = []
        for a in api_methods:
            api = a.split(".")[0]
            if api not in api_list:
                api_list.append(api)
        return api_list

    def _get_asset_symbol(self, asset_id: int) -> str:
        """
        Return the asset symbol for a given asset id.

        Asset ids are looked up in self.chain_params["chain_assets"]. Common mappings include
        0 -> HBD, 1 -> HIVE, 2 -> VESTS.

        Parameters:
            asset_id (int): Numeric asset id as used in chain_params.

        Returns:
            str: The asset symbol for the provided id.

        Raises:
            KeyError: If the asset id is not present in self.chain_params["chain_assets"].
        """
        for asset in self.chain_params["chain_assets"]:
            if asset["id"] == asset_id:
                return asset["symbol"]

        raise KeyError("asset ID not found in chain assets")

    @property
    def backed_token_symbol(self) -> str:
        """
        Return the symbol for the chain's backed asset (HBD-like).

        Attempts to read the asset symbol at asset id 0 (typical HBD). If that key is missing, falls back to asset id 1 (main token) and returns that symbol. Returns a string (e.g., "HBD", "TBD", or the chain's main token symbol). May propagate KeyError if neither asset id is available.
        """
        # some networks (e.g. whaleshares) do not have HBD
        try:
            symbol = self._get_asset_symbol(0)
        except KeyError:
            symbol = self._get_asset_symbol(1)
        return symbol

    @property
    def token_symbol(self) -> str:
        """get the current chains symbol for HIVE (e.g. "TESTS" on testnet)"""
        return self._get_asset_symbol(1)

    @property
    def vest_token_symbol(self) -> str:
        """get the current chains symbol for VESTS"""
        return self._get_asset_symbol(2)
