from __future__ import annotations

import json
import warnings
from datetime import date, datetime, timezone
from typing import Any

from prettytable import PrettyTable

from nectar.account import Account
from nectar.amount import Amount
from nectar.blockchainobject import BlockchainObject
from nectar.exceptions import WitnessDoesNotExistsException
from nectar.instance import shared_blockchain_instance
from nectar.utils import formatTimeString, parse_time
from nectarapi.exceptions import NoMethodWithName, RPCError
from nectarbase import operations


class Witness(BlockchainObject):
    """Read data about a witness in the chain

    :param str owner: Name of the witness
    :param bool lazy: Use lazy loading
    :param bool full: Get full data about witness
    :param nectar.nectar.nectar blockchain_instance: nectar
        instance to use when accessing the RPC
    """

    type_id = 3

    def __init__(
        self,
        owner: str | dict[str, Any],
        full: bool = False,
        lazy: bool = False,
        blockchain_instance: Any | None = None,
        **kwargs: Any,
    ) -> None:
        # Warn about any unused kwargs to maintain backward compatibility
        """
        Initialize a Witness object representing a blockchain witness.

        Parameters:
            owner (str | dict): Witness owner account name or a dictionary of witness fields. If a dict is provided, it will be parsed into the internal witness representation.
            full (bool): If True, load full witness data when available; otherwise keep a lighter representation.
            lazy (bool): If True, defer network loading until data is accessed.

        Notes:
            - `blockchain_instance` defaults to the shared blockchain instance when not provided.
            - Any unexpected keyword arguments are accepted for backward compatibility but will trigger a DeprecationWarning and be ignored.
        """
        if kwargs:
            if blockchain_instance is None and kwargs.get("hive_instance"):
                blockchain_instance = kwargs["hive_instance"]
                warnings.warn(
                    "hive_instance is deprecated, use blockchain_instance instead",
                    DeprecationWarning,
                    stacklevel=2,
                )

            for key in kwargs:
                if key == "hive_instance":
                    continue
                warnings.warn(
                    f"Unexpected keyword argument '{key}' passed to Witness.__init__. "
                    "This may be a deprecated parameter and will be ignored.",
                    DeprecationWarning,
                    stacklevel=2,
                )
        self.full = full
        self.lazy = lazy
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if isinstance(owner, dict):
            owner = self._parse_json_data(owner)
        super().__init__(
            owner, lazy=lazy, full=full, id_item="owner", blockchain_instance=self.blockchain
        )

    def refresh(self) -> None:
        """
        Refresh the witness data from the blockchain and reinitialize this object.

        If the witness identifier is empty or the blockchain is not connected, the method returns early.
        Fetches witness data via the configured RPC, parses
        timestamps and numeric fields via _parse_json_data, and reinitializes the Witness instance with the
        retrieved data (respecting this object's lazy/full flags and blockchain instance).

        Raises:
            WitnessDoesNotExistsException: If no witness information is found for the current identifier.
        """
        if not self.identifier:
            return
        if not self.blockchain.is_connected():
            return
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        witness = self.blockchain.rpc.find_witnesses({"owners": [self.identifier]})["witnesses"]
        if len(witness) > 0:
            witness = witness[0]
        if not witness:
            raise WitnessDoesNotExistsException(self.identifier)
        witness = self._parse_json_data(witness)
        super().__init__(
            witness,
            id_item="owner",
            lazy=self.lazy,
            full=self.full,
            blockchain_instance=self.blockchain,
        )

    def _parse_json_data(self, witness: dict) -> dict:
        parse_times = [
            "created",
            "last_sbd_exchange_update",
            "hardfork_time_vote",
            "last_hbd_exchange_update",
        ]
        for p in parse_times:
            if p in witness and isinstance(witness.get(p), str):
                witness[p] = parse_time(witness.get(p, "1970-01-01T00:00:00"))
        parse_int = [
            "votes",
            "virtual_last_update",
            "virtual_position",
            "virtual_scheduled_time",
        ]
        for p in parse_int:
            if p in witness and isinstance(witness.get(p), str):
                witness[p] = int(witness.get(p, "0"))
        return witness

    def json(self) -> dict[str, Any]:
        output = self.copy()
        parse_times = [
            "created",
            "last_sbd_exchange_update",
            "hardfork_time_vote",
            "last_hbd_exchange_update",
        ]
        for p in parse_times:
            if p in output:
                p_date = output.get(p, datetime(1970, 1, 1, 0, 0))
                if isinstance(p_date, (datetime, date)):
                    output[p] = formatTimeString(p_date)
                else:
                    output[p] = p_date
        parse_int = [
            "votes",
            "virtual_last_update",
            "virtual_position",
            "virtual_scheduled_time",
        ]
        for p in parse_int:
            if p in output and isinstance(output[p], int):
                output[p] = str(output[p])
        return json.loads(str(json.dumps(output)))

    @property
    def account(self) -> Account:
        return Account(self["owner"], blockchain_instance=self.blockchain)

    @property
    def is_active(self) -> bool:
        return (
            len(self["signing_key"]) > 3
            and self["signing_key"][3:] != "1111111111111111111111111111111114T1Anm"
        )

    def feed_publish(self, base, quote=None, account=None):
        """
        Publish a witness feed price (exchange rate) to the blockchain.

        Accepts the base and quote as Amount objects, strings, or numeric values and submits a Feed_publish operation using the provided account (defaults to the witness owner).

        Parameters:
            base: Amount | str | number
                The base side of the exchange_rate (must use the blockchain's backed token symbol).
            quote: Amount | str | number, optional
                The quote side of the exchange_rate. Defaults to "1.000 <TOKEN>" where <TOKEN> is the blockchain token_symbol.
            account: str | Account, optional
                Account name or Account object used to sign and publish the feed. If omitted, the witness owner is used.

        Returns:
            The result returned by blockchain.finalizeOp (typically the broadcast/transaction result).

        Raises:
            ValueError: If no account is provided and the witness has no owner.
            AssertionError: If the resolved base or quote symbols do not match the blockchain's expected backed_token_symbol and token_symbol, respectively.
        """
        quote = quote if quote is not None else "1.000 %s" % (self.blockchain.token_symbol)
        if not account:
            account = self["owner"]
        if not account:
            raise ValueError("You need to provide an account")

        account = Account(account, blockchain_instance=self.blockchain)
        if isinstance(base, Amount):
            base = Amount(base, blockchain_instance=self.blockchain)
        elif isinstance(base, str):
            base = Amount(base, blockchain_instance=self.blockchain)
        else:
            base = Amount(
                base, self.blockchain.backed_token_symbol, blockchain_instance=self.blockchain
            )

        if isinstance(quote, Amount):
            quote = Amount(quote, blockchain_instance=self.blockchain)
        elif isinstance(quote, str):
            quote = Amount(quote, blockchain_instance=self.blockchain)
        else:
            quote = Amount(quote, self.blockchain.token_symbol, blockchain_instance=self.blockchain)

        if not base.symbol == self.blockchain.backed_token_symbol:
            raise AssertionError()
        if not quote.symbol == self.blockchain.token_symbol:
            raise AssertionError()
        op = operations.Feed_publish(
            **{
                "publisher": account["name"],
                "exchange_rate": {
                    "base": base,
                    "quote": quote,
                },
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active")

    def update_witness(self, signing_key, url, props, account=None):
        """Update witness

        :param str signing_key: Signing key
        :param str url: URL
        :param dict props: Properties
        :param str account: (optional) witness account name

        Properties:::

            {
                "account_creation_fee": x,
                "maximum_block_size": x,
                "sbd_interest_rate": x,
            }

        """
        if not account:
            account = self["owner"]
        return self.blockchain.witness_update(signing_key, url, props, account=account)

    def update(self, *args: Any, **kwargs: Any) -> Any:
        """Compatibility shim to avoid clashing with MutableMapping.update"""
        return self.update_witness(*args, **kwargs)

    @staticmethod
    def get_witness_by_account(
        account_name: str, blockchain_instance: Any | None = None
    ) -> dict[str, Any] | None:
        """
        Fetch witness information by account name using the `get_witness_by_account` RPC call.

        :param str account_name: Name of the witness account
        :param blockchain_instance: Nectar instance (optional)
        :return: Witness data dictionary or None if not found/error
        """
        blockchain = blockchain_instance or shared_blockchain_instance()
        try:
            return blockchain.rpc.get_witness_by_account(account_name)
        except (RPCError, NoMethodWithName):
            return None


class WitnessesObject(list):
    def printAsTable(self, sort_key="votes", reverse=True, return_str=False, **kwargs):
        no_feed = False
        if (
            len(self) > 0
            and "sbd_exchange_rate" not in self[0]
            and "hbd_exchange_rate" not in self[0]
        ):
            table_header = ["Name", "Votes [PV]", "Disabled", "Missed", "Fee", "Size", "Version"]
            no_feed = True
        else:
            table_header = [
                "Name",
                "Votes [PV]",
                "Disabled",
                "Missed",
                "Feed base",
                "Feed quote",
                "Feed update",
                "Fee",
                "Size",
                "Interest",
                "Version",
            ]
        if "sbd_exchange_rate" in self[0]:
            bd_exchange_rate = "sbd_exchange_rate"
            bd_interest_rate = "sbd_interest_rate"
            last_bd_exchange_update = "last_sbd_exchange_update"
        else:
            bd_exchange_rate = "hbd_exchange_rate"
            bd_interest_rate = "hbd_interest_rate"
            last_bd_exchange_update = "last_hbd_exchange_update"
        t = PrettyTable(table_header)
        t.align = "l"
        if sort_key == "base":
            sortedList = sorted(
                self, key=lambda self: self[bd_exchange_rate]["base"], reverse=reverse
            )
        elif sort_key == "quote":
            sortedList = sorted(
                self, key=lambda self: self[bd_exchange_rate]["quote"], reverse=reverse
            )
        elif sort_key == "last_sbd_exchange_update" or sort_key == "last_hbd_exchange_update":
            sortedList = sorted(
                self,
                key=lambda self: (
                    datetime.now(timezone.utc) - self[last_bd_exchange_update]
                ).total_seconds(),
                reverse=reverse,
            )
        elif sort_key == "account_creation_fee":
            sortedList = sorted(
                self, key=lambda self: self["props"]["account_creation_fee"], reverse=reverse
            )
        elif sort_key == "sbd_interest_rate" or sort_key == "hbd_interest_rate":
            sortedList = sorted(
                self, key=lambda self: self["props"][bd_interest_rate], reverse=reverse
            )
        elif sort_key == "maximum_block_size":
            sortedList = sorted(
                self, key=lambda self: self["props"]["maximum_block_size"], reverse=reverse
            )
        elif sort_key == "votes":
            sortedList = sorted(self, key=lambda self: int(self[sort_key]), reverse=reverse)
        else:
            sortedList = sorted(self, key=lambda self: self[sort_key], reverse=reverse)
        for witness in sortedList:
            disabled = ""
            if not witness.is_active:
                disabled = "yes"

            if no_feed:
                t.add_row(
                    [
                        witness["owner"],
                        str(round(int(witness["votes"]) / 1e15, 2)),
                        disabled,
                        str(witness["total_missed"]),
                        str(witness["props"]["account_creation_fee"]),
                        str(witness["props"]["maximum_block_size"]),
                        witness["running_version"],
                    ]
                )
            else:
                # Handle both string and datetime formats for exchange update timestamps
                exchange_update = witness[last_bd_exchange_update]
                if isinstance(exchange_update, str):
                    exchange_update_dt = datetime.strptime(
                        exchange_update, "%Y-%m-%dT%H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                else:
                    exchange_update_dt = exchange_update
                td = datetime.now(timezone.utc) - exchange_update_dt
                t.add_row(
                    [
                        witness["owner"],
                        str(round(int(witness["votes"]) / 1e15, 2)),
                        disabled,
                        str(witness["total_missed"]),
                        str(
                            Amount(
                                witness[bd_exchange_rate]["base"],
                                blockchain_instance=witness.blockchain,
                            )
                        ),
                        str(
                            Amount(
                                witness[bd_exchange_rate]["quote"],
                                blockchain_instance=witness.blockchain,
                            )
                        ),
                        str(td.days)
                        + " days "
                        + str(td.seconds // 3600)
                        + ":"
                        + str((td.seconds // 60) % 60),
                        str(
                            Amount(
                                witness["props"]["account_creation_fee"],
                                blockchain_instance=witness.blockchain,
                            )
                        ),
                        str(witness["props"]["maximum_block_size"]),
                        str(witness["props"][bd_interest_rate] / 100) + " %",
                        witness["running_version"],
                    ]
                )
        if return_str:
            return t.get_string(**kwargs)
        else:
            print(t.get_string(**kwargs))

    def get_votes_sum(self):
        vote_sum = 0
        for witness in self:
            vote_sum += int(witness["votes"])
        return vote_sum

    def __contains__(self, item: object, /) -> bool:  # type: ignore[override]
        from nectar.account import Account

        if isinstance(item, Account):
            name = item["name"]
        elif isinstance(item, str):
            name = item
        elif len(self) > 0 and hasattr(self[0], "blockchain") and isinstance(item, dict):
            account = Account(item, blockchain_instance=self[0].blockchain)
            name = account["name"]
        else:
            # Fallback to string comparison
            name = str(item)

        return any([name == x["owner"] for x in self])

    def __str__(self):
        return self.printAsTable(return_str=True)

    def __repr__(self):
        return "<{} {}>".format(
            self.__class__.__name__,
            str(getattr(self, "identifier", f"list_{len(self)}")),
        )


class GetWitnesses(WitnessesObject):
    """Obtain a list of witnesses

    :param list name_list: list of witneses to fetch
    :param int batch_limit: (optional) maximum number of witnesses
        to fetch per call, defaults to 100
    :param nectar.nectar.nectar blockchain_instance: nectar instance to use when
        accessing the RPC

    .. code-block:: python

        from nectar.witness import GetWitnesses
        w = GetWitnesses(["gtg", "jesta"])
        print(w[0].json())
        print(w[1].json())

    """

    def __init__(
        self,
        name_list,
        batch_limit=100,
        lazy=False,
        full=True,
        blockchain_instance=None,
    ):
        """
        Initialize the GetWitnesses collection by fetching witness objects for the given list of account names.

        Names are fetched in batches (size controlled by `batch_limit`). If no blockchain connection is available the initializer returns early and the collection remains empty.

        Parameters:
            name_list (Iterable[str]): Account names of witnesses to retrieve.
            batch_limit (int): Maximum number of names to request per batch.
            lazy (bool): If True, create Witness objects in lazy-loading mode.
            full (bool): If True, create Witness objects with full data loaded.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if not self.blockchain.is_connected():
            return
        witnesses = []
        name_cnt = 0
        while name_cnt < len(name_list):
            self.blockchain.rpc.set_next_node_on_empty_reply(False)
            witnesses += self.blockchain.rpc.find_witnesses(
                {"owners": name_list[name_cnt : batch_limit + name_cnt]}
            )["witnesses"]
            name_cnt += batch_limit
        self.identifier = ""
        super().__init__(
            [
                Witness(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                for x in witnesses
            ]
        )


class Witnesses(WitnessesObject):
    """Obtain a list of **active** witnesses and the current schedule

    :param nectar.nectar.nectar blockchain_instance: nectar instance to use when
        accessing the RPC

    .. code-block:: python

       >>> from nectar.witness import Witnesses
       >>> Witnesses()
       <Witnesses >

    """

    def __init__(self, lazy=False, full=True, blockchain_instance=None, **kwargs):
        """
        Initialize a Witnesses collection and load active witnesses from the configured blockchain.

        Parameters:
            lazy (bool): If True, create Witness objects without fetching full data (deferred loading).
            full (bool): If True, eager-load full witness data when constructing each Witness.

        Notes:
            Resolves the blockchain instance from `blockchain_instance` or the shared default and immediately calls `refresh()` to populate the list of active witnesses.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.lazy = lazy
        self.full = full
        self.refresh()

    def refresh(self):
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        self.active_witnessess = self.blockchain.rpc.get_active_witnesses()["witnesses"]
        self.schedule = self.blockchain.rpc.get_witness_schedule()
        try:
            self.witness_count = self.blockchain.rpc.get_witness_count()
        except (RPCError, NoMethodWithName):
            try:
                # Some nodes expose the method only on condenser_api; fall back to that.
                self.witness_count = self.blockchain.rpc.get_witness_count(api="condenser_api")
            except Exception:
                # As a last resort, derive the count from the active witness set.
                self.witness_count = len(self.active_witnessess)
        self.current_witness = self.blockchain.get_dynamic_global_properties(use_stored_data=False)[
            "current_witness"
        ]
        self.identifier = ""
        super().__init__(
            [
                Witness(x, lazy=self.lazy, full=self.full, blockchain_instance=self.blockchain)
                for x in self.active_witnessess
            ]
        )


class WitnessesVotedByAccount(WitnessesObject):
    """Obtain a list of witnesses which have been voted by an account

    :param str account: Account name
    :param nectar.nectar.nectar blockchain_instance: nectar instance to use when
        accessing the RPC

    .. code-block:: python

       >>> from nectar.witness import WitnessesVotedByAccount
       >>> WitnessesVotedByAccount("gtg")
       <WitnessesVotedByAccount gtg>

    """

    def __init__(self, account, lazy=False, full=True, blockchain_instance=None, **kwargs):
        """
        Initialize a WitnessesVotedByAccount collection for the given account.

        Resolves the provided account to a full Account object, reads the list of witnesses that the account voted for, and populates the list with Witness objects created with the specified loading flags. If the account has no witness votes recorded the constructor returns early and the collection remains empty. The instance identifier is set to the account name.

        Parameters:
            account (str|Account): Account name or Account-like object to inspect for witness votes.
            lazy (bool): If True, create Witness objects in lazy-loading mode. Defaults to False.
            full (bool): If True, request full witness data when constructing Witness objects. Defaults to True.

        Note:
            The blockchain instance is taken from the optional `blockchain_instance` argument or the shared default; it is not documented here as a parameter.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.account = Account(account, full=True, blockchain_instance=self.blockchain)
        account_name = self.account["name"]
        self.identifier = account_name
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if "witnesses_voted_for" not in self.account:
            return
        limit = self.account["witnesses_voted_for"]
        witnessess_dict = self.blockchain.rpc.list_witness_votes(
            {"start": [account_name], "limit": limit, "order": "by_account_witness"}
        )["votes"]
        witnessess = []
        for w in witnessess_dict:
            witnessess.append(w["witness"])

        super().__init__(
            [
                Witness(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                for x in witnessess
            ]
        )


class WitnessesRankedByVote(WitnessesObject):
    """Obtain a list of witnesses ranked by Vote

    :param str from_account: Witness name from which the lists starts (default = "")
    :param int limit: Limits the number of shown witnesses (default = 100)
    :param nectar.nectar.nectar blockchain_instance: nectar instance to use when
        accessing the RPC

    .. code-block:: python

       >>> from nectar.witness import WitnessesRankedByVote
       >>> WitnessesRankedByVote(limit=100)
       <WitnessesRankedByVote >

    """

    def __init__(
        self,
        from_account="",
        limit=100,
        lazy=False,
        full=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a list of witnesses ranked by vote, with optional pagination.

        Builds a WitnessesRankedByVote list starting at `from_account` and returning up to `limit`
        entries. The constructor transparently pages RPC calls when the requested `limit`
        exceeds the per-call query limit, handles RPC calls and wraps returned witness entries as Witness objects.

        Parameters:
            from_account (str): Account name to start ranking from (inclusive). When empty, ranking starts from the top.
            limit (int): Maximum number of witnesses to return.
            lazy (bool): If True, create Witness objects in lazy-loading mode.
            full (bool): If True, fully load each Witness on creation.

        Notes:
            - `blockchain_instance` is taken from the shared instance when not provided.
            - The method uses different RPC endpoints depending on the node configuration
              (appbase vs non-appbase, and condenser mode) and automatically pages results
              to satisfy `limit`.
            - Returns early (no list created) if no witnesses are found.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        witnessList = []
        last_limit = limit
        self.identifier = ""
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        query_limit = 1000

        if from_account == "":
            last_account = None
        else:
            last_account = Witness(from_account, blockchain_instance=self.blockchain)["votes"]
        if limit > query_limit:
            while last_limit > query_limit:
                tmpList = WitnessesRankedByVote(last_account, query_limit)
                if last_limit < limit:
                    witnessList.extend(tmpList[1:])
                    last_limit -= query_limit - 1
                else:
                    witnessList.extend(tmpList)
                    last_limit -= query_limit

                last_account = witnessList[-1]["votes"]
        if last_limit < limit:
            last_limit += 1
        witnessess = self.blockchain.rpc.list_witnesses(
            {"start": [0, last_account], "limit": last_limit, "order": "by_vote_name"}
        )["witnesses"]

        # self.witness_count = len(self.voted_witnessess)
        if last_limit < limit:
            witnessess = witnessess[1:]
        if len(witnessess) > 0:
            for x in witnessess:
                witnessList.append(
                    Witness(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                )
        if len(witnessList) == 0:
            return
        super().__init__(witnessList)


class ListWitnesses(WitnessesObject):
    """List witnesses ranked by name

    :param str from_account: Witness name from which the list starts (default = "")
    :param int limit: Limits the number of shown witnesses (default = 100)
    :param nectar.nectar.nectar blockchain_instance: nectar instance to use when
        accessing the RPC

    .. code-block:: python

       >>> from nectar.witness import ListWitnesses
       >>> ListWitnesses(from_account="gtg", limit=100)
       <ListWitnesses gtg>

    """

    def __init__(
        self,
        from_account="",
        limit=100,
        lazy=False,
        full=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a ListWitnesses collection starting from a given account name.

        Creates a list of Witness objects beginning at `from_account` (lexicographic start)
        up to `limit` entries. If no witnesses are found the constructor returns early
        leaving the instance empty. The object uses the provided blockchain instance
        (or the shared default) to query the node and sets `identifier` to `from_account`.

        Parameters:
            from_account (str): Account name to start listing witnesses from (inclusive).
            limit (int): Maximum number of witness entries to retrieve.
            lazy (bool): If True, construct Witness objects in lazy mode (defer full data load).
            full (bool): If True, request full witness data when constructing Witness objects.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.identifier = from_account
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        witnessess = self.blockchain.rpc.list_witnesses(
            {"start": from_account, "limit": limit, "order": "by_name"}
        )["witnesses"]
        if len(witnessess) == 0:
            return
        super().__init__(
            [
                Witness(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                for x in witnessess
            ]
        )
