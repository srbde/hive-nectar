import logging
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import httpx2

from nectar.account import Account
from nectar.amount import Amount
from nectar.asset import Asset
from nectar.instance import shared_blockchain_instance
from nectar.price import FilledOrder, Order, Price
from nectar.utils import addTzInfo, assets_from_string, formatTimeFromNow, formatTimeString
from nectarbase import operations

log = logging.getLogger(__name__)


class Market(dict):
    """This class allows access to the internal market for trading, etc. (Hive-only).

    :param Hive blockchain_instance: Hive instance
    :param Asset base: Base asset
    :param Asset quote: Quote asset
    :returns: Blockchain Market
    :rtype: dictionary with overloaded methods

    Instances of this class are dictionaries that come with additional
    methods (see below) that allow dealing with a market and its
    corresponding functions.

    This class tries to identify **two** assets as provided in the
    parameters in one of the following forms:

    * ``base`` and ``quote`` are valid assets (according to :class:`nectar.asset.Asset`)
    * ``base:quote`` separated with ``:``
    * ``base/quote`` separated with ``/``
    * ``base-quote`` separated with ``-``

    .. note:: Throughout this library, the ``quote`` symbol will be
              presented first (e.g. ``HIVE:HBD`` with ``HIVE`` being the
              quote), while the ``base`` only refers to a secondary asset
              for a trade. This means, if you call
              :func:`nectar.market.Market.sell` or
              :func:`nectar.market.Market.buy`, you will sell/buy **only
              quote** and obtain/pay **only base**.

    """

    def __init__(
        self,
        base: Optional[Union[str, Asset]] = None,
        quote: Optional[Union[str, Asset]] = None,
        blockchain_instance: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """
        Create a Market mapping with "base" and "quote" Asset objects.

        Supports three initialization modes:
        - Single-string market identifier (e.g., "HBD:HIVE" or "HIVE:HBD"): parsed into quote and base symbols and converted to Asset objects.
        - Explicit base and quote (either Asset instances or values accepted by Asset): each converted to an Asset.
        - No arguments: uses the blockchain instance's default token symbols (token_symbol as base, backed_token_symbol as quote).

        The resolved Asset objects are recorded in the instance as entries "base" and "quote". The blockchain instance used is the provided one or the shared global instance.

        Raises:
            ValueError: if the combination of arguments does not match any supported initialization mode.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if quote is None and isinstance(base, str):
            quote_symbol, base_symbol = assets_from_string(base)
            quote = Asset(quote_symbol, blockchain_instance=self.blockchain)
            base = Asset(base_symbol, blockchain_instance=self.blockchain)
            super().__init__({"base": base, "quote": quote}, blockchain_instance=self.blockchain)
        elif base and quote:
            # Handle Asset objects properly without converting to string
            if isinstance(quote, Asset):
                quote_asset = quote
            else:
                quote_asset = Asset(str(quote), blockchain_instance=self.blockchain)

            if isinstance(base, Asset):
                base_asset = base
            else:
                base_asset = Asset(str(base), blockchain_instance=self.blockchain)

            super().__init__(
                {"base": base_asset, "quote": quote_asset}, blockchain_instance=self.blockchain
            )
        elif base is None and quote is None:
            quote = Asset(self.blockchain.backed_token_symbol, blockchain_instance=self.blockchain)
            base = Asset(self.blockchain.token_symbol, blockchain_instance=self.blockchain)
            super().__init__({"base": base, "quote": quote}, blockchain_instance=self.blockchain)
        else:
            raise ValueError("Unknown Market config")

    def get_string(self, separator: str = ":") -> str:
        """
        Return the market identifier as "QUOTE{separator}BASE" (e.g. "HIVE:HBD").

        Parameters:
            separator (str): Token placed between quote and base symbols. Defaults to ":".

        Returns:
            str: Formatted market string in the form "<quote><separator><base>".
        """
        return "{}{}{}".format(self["quote"]["symbol"], separator, self["base"]["symbol"])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            quote_symbol, base_symbol = assets_from_string(other)
            return (
                self["quote"]["symbol"] == quote_symbol and self["base"]["symbol"] == base_symbol
            ) or (self["quote"]["symbol"] == base_symbol and self["base"]["symbol"] == quote_symbol)
        if isinstance(other, Market):
            return (
                self["quote"]["symbol"] == other["quote"]["symbol"]
                and self["base"]["symbol"] == other["base"]["symbol"]
            )
        return False

    def ticker(self, raw_data: bool = False) -> Union[Dict[str, Any], Any]:
        """
        Return the market ticker for this Market (HIVE:HBD).

        By default returns a dict with Price objects for 'highest_bid', 'latest', and 'lowest_ask',
        a float 'percent_change' (24h), and Amount objects for 'hbd_volume' and 'hive_volume' when present.
        If raw_data is True, returns the unprocessed RPC result.

        Parameters:
            raw_data (bool): If True, return the raw market_history RPC response instead of mapped objects.

        Returns:
            dict or Any: Mapped ticker dictionary (prices as Price, volumes as Amount) or raw RPC data.

        Notes:
            Prices are expressed as HBD per HIVE.
        """
        data = {}
        # Core Exchange rate
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        ticker = self.blockchain.rpc.get_ticker()

        if raw_data:
            return ticker

        data["highest_bid"] = Price(
            ticker["highest_bid"],
            base=self["base"],
            quote=self["quote"],
            blockchain_instance=self.blockchain,
        )
        data["latest"] = Price(
            ticker["latest"],
            quote=self["quote"],
            base=self["base"],
            blockchain_instance=self.blockchain,
        )
        data["lowest_ask"] = Price(
            ticker["lowest_ask"],
            base=self["base"],
            quote=self["quote"],
            blockchain_instance=self.blockchain,
        )
        data["percent_change"] = float(ticker["percent_change"])
        if "hbd_volume" in ticker:
            data["hbd_volume"] = Amount(ticker["hbd_volume"], blockchain_instance=self.blockchain)
        if "hive_volume" in ticker:
            data["hive_volume"] = Amount(ticker["hive_volume"], blockchain_instance=self.blockchain)

        return data

    def volume24h(self, raw_data: bool = False) -> Optional[Union[Dict[str, Amount], Any]]:
        """
        Return 24-hour trading volume for this market.

        If raw_data is True, returns the raw result from the blockchain `market_history` RPC.
        Otherwise, if the RPC result contains 'hbd_volume' and 'hive_volume', returns a dict mapping
        asset symbols to Amount objects, e.g. { "HBD": Amount(...), "HIVE": Amount(...) }.
        If the expected volume keys are not present, returns None.

        Parameters:
            raw_data (bool): If True, return the unprocessed RPC response.
        """
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        volume = self.blockchain.rpc.get_volume()
        if raw_data:
            return volume
        if "hbd_volume" in volume and "hive_volume" in volume:
            return {
                self.blockchain.backed_token_symbol: Amount(
                    volume["hbd_volume"], blockchain_instance=self.blockchain
                ),
                self.blockchain.token_symbol: Amount(
                    volume["hive_volume"], blockchain_instance=self.blockchain
                ),
            }

    def orderbook(self, limit: int = 25, raw_data: bool = False) -> Union[Dict[str, Any], Any]:
        """Returns the order book for the HBD/HIVE market.

        :param int limit: Limit the amount of orders (default: 25)

        Sample output (raw_data=False):

            .. code-block:: none

                {
                    'asks': [
                        380.510 HIVE 460.291 HBD @ 1.209669 HBD/HIVE,
                        53.785 HIVE 65.063 HBD @ 1.209687 HBD/HIVE
                    ],
                    'bids': [
                        0.292 HIVE 0.353 HBD @ 1.208904 HBD/HIVE,
                        8.498 HIVE 10.262 HBD @ 1.207578 HBD/HIVE
                    ],
                    'asks_date': [
                        datetime.datetime(2018, 4, 30, 21, 7, 24, tzinfo=<UTC>),
                        datetime.datetime(2018, 4, 30, 18, 12, 18, tzinfo=<UTC>)
                    ],
                    'bids_date': [
                        datetime.datetime(2018, 4, 30, 21, 1, 21, tzinfo=<UTC>),
                        datetime.datetime(2018, 4, 30, 20, 38, 21, tzinfo=<UTC>)
                    ]
                }

        Sample output (raw_data=True):

            .. code-block:: js

                {
                    'asks': [
                        {
                            'order_price': {'base': '8.000 HIVE', 'quote': '9.618 HBD'},
                            'real_price': '1.20225000000000004',
                            'hive': 4565,
                            'hbd': 5488,
                            'created': '2018-04-30T21:12:45'
                        }
                    ],
                    'bids': [
                        {
                            'order_price': {'base': '10.000 HBD', 'quote': '8.333 HIVE'},
                            'real_price': '1.20004800192007677',
                            'hive': 8333,
                            'hbd': 10000,
                            'created': '2018-04-30T20:29:33'
                        }
                    ]
                }

        .. note:: Each bid is an instance of
            class:`nectar.price.Order` and thus carries the keys
            ``base``, ``quote`` and ``price``. From those you can
            obtain the actual amounts for sale

        """
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        orders = self.blockchain.rpc.get_order_book({"limit": limit})
        if raw_data:
            return orders
        asks = list(
            [
                Order(
                    Amount(x["order_price"]["quote"], blockchain_instance=self.blockchain),
                    Amount(x["order_price"]["base"], blockchain_instance=self.blockchain),
                    blockchain_instance=self.blockchain,
                )
                for x in orders["asks"]
            ]
        )
        bids = list(
            [
                Order(
                    Amount(x["order_price"]["quote"], blockchain_instance=self.blockchain),
                    Amount(x["order_price"]["base"], blockchain_instance=self.blockchain),
                    blockchain_instance=self.blockchain,
                ).invert()
                for x in orders["bids"]
            ]
        )
        asks_date = list([formatTimeString(x["created"]) for x in orders["asks"]])
        bids_date = list([formatTimeString(x["created"]) for x in orders["bids"]])
        data = {"asks": asks, "bids": bids, "asks_date": asks_date, "bids_date": bids_date}
        return data

    def recent_trades(
        self, limit: int = 25, raw_data: bool = False
    ) -> Union[List[FilledOrder], List[Dict[str, Any]]]:
        """
        Return recent trades for this market.

        By default returns up to `limit` most recent trades wrapped as FilledOrder objects; if `raw_data` is True the raw trade dictionaries from the market_history API are returned instead.

        Parameters:
            limit (int): Maximum number of trades to retrieve (default: 25).
            raw_data (bool): If True, return raw API trade entries; if False, return a list of FilledOrder instances constructed with this market's blockchain instance.

        Returns:
            list: A list of FilledOrder objects when `raw_data` is False, or a list of raw trade dicts as returned by the market_history API when `raw_data` is True.
        """
        self.blockchain.rpc.set_next_node_on_empty_reply(limit > 0)
        orders = self.blockchain.rpc.get_recent_trades({"limit": limit})["trades"]
        if raw_data:
            return orders
        filled_order = list([FilledOrder(x, blockchain_instance=self.blockchain) for x in orders])
        return filled_order

    def trade_history(
        self,
        start: Optional[Union[datetime, date, time]] = None,
        stop: Optional[Union[datetime, date, time]] = None,
        limit: int = 25,
        raw_data: bool = False,
    ) -> Union[List[FilledOrder], List[Dict[str, Any]]]:
        """Returns the trade history for the internal market

        :param datetime start: Start date
        :param datetime stop: Stop date
        :param int limit: Defines how many trades are fetched at each interval point
        :param bool raw_data: when True, the raw data are returned
        """
        if not stop:
            stop = datetime.now(timezone.utc)
        if not start:
            # Ensure stop is a datetime for arithmetic operations
            if isinstance(stop, datetime):
                start = stop - timedelta(hours=1)
            else:
                # Convert date/time to datetime for arithmetic
                if isinstance(stop, date):
                    start = datetime.combine(stop, time.min, timezone.utc) - timedelta(hours=1)
                else:  # time object
                    start = datetime.combine(date.today(), stop, timezone.utc) - timedelta(hours=1)
        # Fetch a single page of trades; callers can page manually if needed.
        return self.trades(start=start, stop=stop, limit=limit, raw_data=raw_data)

    def trades(
        self,
        limit: int = 100,
        start: Optional[Union[datetime, date, time]] = None,
        stop: Optional[Union[datetime, date, time]] = None,
        raw_data: bool = False,
    ) -> Union[List[FilledOrder], List[Dict[str, Any]]]:
        """Returns your trade history for a given market.

        :param int limit: Limit the amount of orders (default: 100)
        :param datetime start: start time
        :param datetime stop: stop time

        """
        # FIXME, this call should also return whether it was a buy or
        # sell
        if not stop:
            stop = datetime.now(timezone.utc)
        if not start:
            # Ensure stop is a datetime for arithmetic operations
            if isinstance(stop, datetime):
                start = stop - timedelta(hours=24)
            else:
                # Convert date/time to datetime for arithmetic
                if isinstance(stop, date):
                    start = datetime.combine(stop, time.min, timezone.utc) - timedelta(hours=24)
                else:  # time object
                    start = datetime.combine(date.today(), stop, timezone.utc) - timedelta(hours=24)
        start = addTzInfo(start)
        stop = addTzInfo(stop)
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        orders = self.blockchain.rpc.get_trade_history(
            {
                "start": formatTimeString(start) if start else None,
                "end": formatTimeString(stop) if stop else None,
                "limit": limit,
            },
        )["trades"]
        if raw_data:
            return orders
        filled_order = list([FilledOrder(x, blockchain_instance=self.blockchain) for x in orders])
        return filled_order

    def market_history_buckets(self) -> List[int]:
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        ret = self.blockchain.rpc.get_market_history_buckets()
        return ret["bucket_sizes"]

    def market_history(
        self,
        bucket_seconds: Union[int, float] = 300,
        start_age: int = 3600,
        end_age: int = 0,
        raw_data: bool = False,
    ) -> Union[List[Dict[str, Any]], Any]:
        """
        Return market history buckets for a time window.

        This fetches aggregated market history buckets (filled orders) for the market over a window defined by start_age and end_age and grouped by bucket_seconds. bucket_seconds may be provided either as a numeric bucket size (seconds) or as an index into available buckets returned by market_history_buckets(). When raw_data is False any bucket "open" timestamp strings are normalized to a consistent formatted datetime string.

        Parameters:
            bucket_seconds (int): Bucket size in seconds or an index into market_history_buckets().
            start_age (int): Age in seconds from now to the start of the window (default 3600 seconds).
            end_age (int): Age in seconds from now to the end of the window (default 0 = now).
            raw_data (bool): If True, return the raw RPC response without normalizing timestamps.

        Returns:
            list: A list of bucket dicts (or the raw RPC list when raw_data is True). Each bucket contains fields such as 'open', 'seconds', 'open_hbd', 'close_hbd', 'high_hbd', 'low_hbd', 'hbd_volume', 'open_hive', 'close_hive', 'high_hive', 'low_hive', 'hive_volume', and 'id' when available.

        Raises:
            ValueError: If bucket_seconds is not a valid bucket size or valid index into available buckets.
        """
        buckets = self.market_history_buckets()
        if (
            isinstance(bucket_seconds, int)
            and bucket_seconds < len(buckets)
            and bucket_seconds >= 0
        ):
            bucket_seconds = buckets[bucket_seconds]
        else:
            if bucket_seconds not in buckets:
                raise ValueError("You need select the bucket_seconds from " + str(buckets))
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        history = self.blockchain.rpc.get_market_history(
            {
                "bucket_seconds": bucket_seconds,
                "start": formatTimeFromNow(-start_age - end_age),
                "end": formatTimeFromNow(-end_age),
            },
        )["buckets"]
        if raw_data:
            return history
        new_history = []
        for h in history:
            if "open" in h and isinstance(h.get("open"), str):
                h["open"] = formatTimeString(h.get("open", "1970-01-01T00:00:00"))
                new_history.append(h)
        return new_history

    def accountopenorders(
        self, account: Optional[Union[str, Account]] = None, raw_data: bool = False
    ) -> Union[List[Order], List[Dict[str, Any]], None]:
        """Returns open Orders

        :param Account account: Account name or instance of Account to show orders for in this market
        :param bool raw_data: (optional) returns raw data if set True,
            or a list of Order() instances if False (defaults to False)
        """
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, full=True, blockchain_instance=self.blockchain)

        r = []
        # orders = account["limit_orders"]
        if not self.blockchain.is_connected():
            return None
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        orders = self.blockchain.rpc.find_limit_orders({"account": account["name"]})["orders"]
        if raw_data:
            return orders
        for o in orders:
            order = {}
            order["order"] = Order(
                Amount(o["sell_price"]["base"], blockchain_instance=self.blockchain),
                Amount(o["sell_price"]["quote"], blockchain_instance=self.blockchain),
                blockchain_instance=self.blockchain,
            )
            order["orderid"] = o["orderid"]
            order["created"] = formatTimeString(o["created"])
            r.append(order)
        return r

    def buy(
        self,
        price: Union[str, Price, float],
        amount: Union[str, Amount],
        expiration: Optional[int] = None,
        killfill: bool = False,
        account: Optional[Union[str, Account]] = None,
        orderid: Optional[int] = None,
        returnOrderId: bool = False,
    ) -> Union[Dict[str, Any], str]:
        """
        Place a buy order (limit order) on this market.

        Prices are expressed in the market's base/quote orientation (HIVE per HBD in HBD_HIVE). This method submits a limit-order-create operation that effectively places a sell order of the base asset to acquire the requested amount of the quote asset.

        Parameters:
            price (float or Price): Price expressed in base per quote (e.g., HIVE per HBD).
            amount (number or str or Amount): Amount of the quote asset to buy.
            expiration (int, optional): Order lifetime in seconds (default: configured order-expiration, typically 7 days).
            killfill (bool, optional): If True, set fill_or_kill on the order (defaults to False).
            account (str, optional): Account name that will own and broadcast the order. If omitted, default_account from config is used; a ValueError is raised if none is available.
            orderid (int, optional): Explicit client-side order id. If omitted one is randomly generated.
            returnOrderId (bool or str, optional): If truthy (or set to "head"/"irreversible"), the call will wait for the transaction and attach the assigned order id to the returned transaction under the "orderid" key.

        Returns:
            dict: The finalized broadcast transaction object returned by the blockchain client. If returnOrderId was used, the dict includes an "orderid" field.

        Raises:
            ValueError: If no account can be resolved.
            AssertionError: If an Amount is provided whose asset symbol does not match the market quote.

        Notes:
            - Because buy orders are implemented as limit-sell orders of the base asset, the trade can result in receiving more of the quote asset than requested if matching orders exist at better prices.
        """
        if not expiration:
            expiration = self.blockchain.config["order-expiration"]
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self.blockchain)

        if isinstance(price, Price):
            price = price.as_base(self["base"]["symbol"])

        if isinstance(amount, Amount):
            amount = Amount(amount, blockchain_instance=self.blockchain)
            if not amount["asset"]["symbol"] == self["quote"]["symbol"]:
                raise AssertionError(
                    "Price: {} does not match amount: {}".format(str(price), str(amount))
                )
        elif isinstance(amount, str):
            amount = Amount(amount, blockchain_instance=self.blockchain)
        else:
            amount = Amount(amount, self["quote"]["symbol"], blockchain_instance=self.blockchain)
        order = operations.Limit_order_create(
            **{
                "owner": account["name"],
                "orderid": orderid or random.getrandbits(32),
                "amount_to_sell": Amount(
                    float(amount) * float(price),
                    self["base"]["symbol"],
                    blockchain_instance=self.blockchain,
                    json_str=True,
                ),
                "min_to_receive": Amount(
                    float(amount),
                    self["quote"]["symbol"],
                    blockchain_instance=self.blockchain,
                    json_str=True,
                ),
                "expiration": formatTimeFromNow(expiration),
                "fill_or_kill": killfill,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )

        if returnOrderId:
            # Make blocking broadcasts
            prevblocking = self.blockchain.blocking
            self.blockchain.blocking = returnOrderId

        tx = self.blockchain.finalizeOp(order, account["name"], "active")

        if returnOrderId:
            tx["orderid"] = tx["operation_results"][0][1]
            self.blockchain.blocking = prevblocking

        return tx

    def sell(
        self,
        price: Union[str, Price, float],
        amount: Union[str, Amount],
        expiration: Optional[int] = None,
        killfill: bool = False,
        account: Optional[Union[str, Account]] = None,
        orderid: Optional[int] = None,
        returnOrderId: bool = False,
    ) -> Union[Dict[str, Any], str]:
        """
        Place a limit sell order on this market, selling the market's quote asset for its base asset.

        This creates a Limit_order_create operation where `amount_to_sell` is the provided `amount` in the market's quote asset and `min_to_receive` is `amount * price` in the market's base asset.

        Parameters:
            price (float or Price): Price expressed as base per quote (e.g., in HBD_HIVE market, a price of 3 means 1 HBD = 3 HIVE).
            amount (number or str or Amount): Quantity of the quote asset to sell; may be an Amount instance, a string (e.g., "10.000 HBD"), or a numeric value.
            expiration (int, optional): Order lifetime in seconds; defaults to the node/configured order-expiration (typically 7 days).
            killfill (bool, optional): If True, treat the order as fill-or-kill (cancel if not fully filled). Defaults to False.
            account (str, optional): Account name placing the order. If omitted, the configured default_account is used. Raises ValueError if no account is available.
            orderid (int, optional): Client-provided order identifier; a random 32-bit id is used if not supplied.
            returnOrderId (bool or str, optional): If truthy (or set to "head"/"irreversible"), the call will wait according to the blocking mode and the returned transaction will include an "orderid" field.

        Returns:
            dict: The finalized transaction object returned by the blockchain finalizeOp call. If `returnOrderId` is used, the dict will include an "orderid" key.

        Raises:
            ValueError: If no account is provided or available from configuration.
            AssertionError: If an Amount is provided whose asset symbol does not match the market's quote asset.
        """
        if not expiration:
            expiration = self.blockchain.config["order-expiration"]
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self.blockchain)
        if isinstance(price, Price):
            price = price.as_base(self["base"]["symbol"])

        if isinstance(amount, Amount):
            amount = Amount(amount, blockchain_instance=self.blockchain)
            if not amount["asset"]["symbol"] == self["quote"]["symbol"]:
                raise AssertionError(
                    "Price: {} does not match amount: {}".format(str(price), str(amount))
                )
        elif isinstance(amount, str):
            amount = Amount(amount, blockchain_instance=self.blockchain)
        else:
            amount = Amount(amount, self["quote"]["symbol"], blockchain_instance=self.blockchain)
        order = operations.Limit_order_create(
            **{
                "owner": account["name"],
                "orderid": orderid or random.getrandbits(32),
                "amount_to_sell": Amount(
                    float(amount),
                    self["quote"]["symbol"],
                    blockchain_instance=self.blockchain,
                    json_str=True,
                ),
                "min_to_receive": Amount(
                    float(amount) * float(price),
                    self["base"]["symbol"],
                    blockchain_instance=self.blockchain,
                    json_str=True,
                ),
                "expiration": formatTimeFromNow(expiration),
                "fill_or_kill": killfill,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        if returnOrderId:
            # Make blocking broadcasts
            prevblocking = self.blockchain.blocking
            self.blockchain.blocking = returnOrderId

        tx = self.blockchain.finalizeOp(order, account["name"], "active")

        if returnOrderId:
            tx["orderid"] = tx["operation_results"][0][1]
            self.blockchain.blocking = prevblocking

        return tx

    def cancel(
        self,
        orderNumbers: Union[int, List[int], Set[int], Tuple[int, ...]],
        account: Optional[Union[str, Account]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Cancels an order you have placed in a given market. Requires
        only the "orderNumbers".

        :param orderNumbers: A single order number or a list of order numbers
        :type orderNumbers: int, list
        """
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, full=False, blockchain_instance=self.blockchain)

        if not isinstance(orderNumbers, (list, set, tuple)):
            orderNumbers = {orderNumbers}

        op = []
        for order in orderNumbers:
            op.append(
                operations.Limit_order_cancel(
                    **{"owner": account["name"], "orderid": order, "prefix": self.blockchain.prefix}
                )
            )
        return self.blockchain.finalizeOp(op, account["name"], "active", **kwargs)

    @staticmethod
    def _weighted_average(
        values: List[Union[int, float]], weights: List[Union[int, float]]
    ) -> float:
        """Calculates a weighted average"""
        if not (len(values) == len(weights) and len(weights) > 0):
            raise AssertionError("Length of both array must be the same and greater than zero!")
        return sum(x * y for x, y in zip(values, weights)) / sum(weights)

    @staticmethod
    def btc_usd_ticker(verbose: bool = False) -> float:
        """
        Return the market-weighted BTC/USD price aggregated from multiple external sources.

        Queries a set of public endpoints (currently CoinGecko; legacy support for Bitfinex, GDAX, Kraken, OKCoin, Bitstamp is present)
        and computes a volume-weighted average price (VWAP) across successful responses.

        Parameters:
            verbose (bool): If True, prints the raw price/volume map collected from each source.

        Returns:
            float: The VWAP of BTC in USD computed from available sources.

        Raises:
            RuntimeError: If no valid price data could be obtained from any source after several attempts.
        """
        prices = {}
        responses = []
        urls = [
            # "https://api.bitfinex.com/v1/pubticker/BTCUSD",
            # "https://api.gdax.com/products/BTC-USD/ticker",
            # "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
            # "https://www.okcoin.com/api/v1/ticker.do?symbol=btc_usd",
            # "https://www.bitstamp.net/api/v2/ticker/btcusd/",
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_vol=true",
        ]
        cnt = 0
        while len(prices) == 0 and cnt < 5:
            cnt += 1
            try:
                responses = list(httpx2.get(u, timeout=30) for u in urls)
            except Exception as e:
                log.debug(str(e))

            for r in [
                x
                for x in responses
                if hasattr(x, "status_code") and x.status_code == 200 and x.json()
            ]:
                try:
                    if "bitfinex" in str(r.url):
                        data = r.json()
                        prices["bitfinex"] = {
                            "price": float(data["last_price"]),
                            "volume": float(data["volume"]),
                        }
                    elif "gdax" in str(r.url):
                        data = r.json()
                        prices["gdax"] = {
                            "price": float(data["price"]),
                            "volume": float(data["volume"]),
                        }
                    elif "kraken" in str(r.url):
                        data = r.json()["result"]["XXBTZUSD"]["p"]
                        prices["kraken"] = {"price": float(data[0]), "volume": float(data[1])}
                    elif "okcoin" in str(r.url):
                        data = r.json()["ticker"]
                        prices["okcoin"] = {
                            "price": float(data["last"]),
                            "volume": float(data["vol"]),
                        }
                    elif "bitstamp" in str(r.url):
                        data = r.json()
                        prices["bitstamp"] = {
                            "price": float(data["last"]),
                            "volume": float(data["volume"]),
                        }
                    elif "coingecko" in str(r.url):
                        data = r.json()["bitcoin"]
                        if "usd_24h_vol" in data:
                            volume = float(data["usd_24h_vol"])
                        else:
                            volume = 1
                        prices["coingecko"] = {"price": float(data["usd"]), "volume": volume}
                except KeyError as e:
                    log.info(str(e))

        if verbose:
            print(prices)

        if len(prices) == 0:
            raise RuntimeError("Obtaining BTC/USD prices has failed from all sources.")

        # vwap
        return Market._weighted_average(
            [x["price"] for x in prices.values()], [x["volume"] for x in prices.values()]
        )

    @staticmethod
    def hive_btc_ticker() -> float:
        """
        Return the HIVE/BTC price as a volume-weighted average from multiple public exchanges.

        Queries several public APIs (CoinGecko and others) to collect recent HIVE/BTC prices and 24h volumes, then computes a volume-weighted average price (VWAP). The function retries up to 5 times if no valid responses are obtained.

        Returns:
            float: VWAP price expressed in BTC per 1 HIVE.

        Raises:
            RuntimeError: If no valid price data could be obtained from any source.
        """
        prices = {}
        responses = []
        urls = [
            # "https://bittrex.com/api/v1.1/public/getmarketsummary?market=BTC-HIVE",
            # "https://api.binance.com/api/v1/ticker/24hr",
            # "https://api.probit.com/api/exchange/v1/ticker?market_ids=HIVE-USDT",
            "https://api.coingecko.com/api/v3/simple/price?ids=hive&vs_currencies=btc&include_24hr_vol=true",
        ]
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36",
        }
        cnt = 0
        while len(prices) == 0 and cnt < 5:
            cnt += 1
            try:
                responses = list(httpx2.get(u, headers=headers, timeout=30) for u in urls)
            except Exception as e:
                log.debug(str(e))

            for r in [
                x
                for x in responses
                if hasattr(x, "status_code") and x.status_code == 200 and x.json()
            ]:
                try:
                    if "poloniex" in str(r.url):
                        data = r.json()["BTC_HIVE"]
                        prices["poloniex"] = {
                            "price": float(data["last"]),
                            "volume": float(data["baseVolume"]),
                        }
                    elif "bittrex" in str(r.url):
                        data = r.json()["result"][0]
                        price = (data["Bid"] + data["Ask"]) / 2
                        prices["bittrex"] = {"price": price, "volume": data["BaseVolume"]}
                    elif "binance" in str(r.url):
                        data = [x for x in r.json() if x["symbol"] == "HIVEBTC"][0]
                        prices["binance"] = {
                            "price": float(data["lastPrice"]),
                            "volume": float(data["quoteVolume"]),
                        }
                    elif "huobi" in str(r.url):
                        data = r.json()["data"][-1]
                        prices["huobi"] = {
                            "price": float(data["close"]),
                            "volume": float(data["vol"]),
                        }
                    elif "upbit" in str(r.url):
                        data = r.json()[-1]
                        prices["upbit"] = {
                            "price": float(data["tradePrice"]),
                            "volume": float(data["tradeVolume"]),
                        }
                    elif "probit" in str(r.url):
                        data = r.json()["data"]
                        prices["probit"] = {
                            "price": float(data["last"]),
                            "volume": float(data["base_volume"]),
                        }
                    elif "coingecko" in str(r.url):
                        data = r.json()["hive"]
                        if "btc_24h_vol" in data:
                            volume = float(data["btc_24h_vol"])
                        else:
                            volume = 1
                        prices["coingecko"] = {"price": float(data["btc"]), "volume": volume}
                except KeyError as e:
                    log.info(str(e))

        if len(prices) == 0:
            raise RuntimeError("Obtaining HIVE/BTC prices has failed from all sources.")

        return Market._weighted_average(
            [x["price"] for x in prices.values()], [x["volume"] for x in prices.values()]
        )

    def hive_usd_implied(self) -> float:
        """Returns the current HIVE/USD market price"""
        return self.hive_btc_ticker() * self.btc_usd_ticker()
