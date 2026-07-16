from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Union

from nectar.exceptions import InvalidAssetException
from nectar.instance import shared_blockchain_instance

from .amount import Amount, check_asset
from .asset import Asset

if TYPE_CHECKING:
    from nectar.market import Market
from nectar.utils import assets_from_string, formatTimeString


class Price(dict):
    """This class deals with all sorts of prices of any pair of assets to
    simplify dealing with the tuple::

        (quote, base)

    each being an instance of :class:`nectar.amount.Amount`. The
    amount themselves define the price.

    .. note::

        The price (floating) is derived as ``base/quote``

    :param list args: Allows to deal with different representations of a price
    :param Asset base: Base asset
    :param Asset quote: Quote asset
    :param Hive blockchain_instance: Hive instance
    :returns: All data required to represent a price
    :rtype: dictionary

    Way to obtain a proper instance:

        * ``args`` is a str with a price and two assets
        * ``args`` can be a floating number and ``base`` and ``quote`` being instances of :class:`nectar.asset.Asset`
        * ``args`` can be a floating number and ``base`` and ``quote`` being instances of ``str``
        * ``args`` can be dict with keys ``price``, ``base``, and ``quote`` (*graphene balances*)
        * ``args`` can be dict with keys ``base`` and ``quote``
        * ``args`` can be dict with key ``receives`` (filled orders)
        * ``args`` being a list of ``[quote, base]`` both being instances of :class:`nectar.amount.Amount`
        * ``args`` being a list of ``[quote, base]`` both being instances of ``str`` (``amount symbol``)
        * ``base`` and ``quote`` being instances of :class:`nectar.asset.Amount`

    This allows instantiations like:

    * ``Price("0.315 HBD/HIVE")``
    * ``Price(0.315, base="HBD", quote="HIVE")``
    * ``Price(0.315, base=Asset("HBD"), quote=Asset("HIVE"))``
    * ``Price({"base": {"amount": 1, "asset_id": "HBD"}, "quote": {"amount": 10, "asset_id": "HBD"}})``
    * ``Price(quote="10 HIVE", base="1 HBD")``
    * ``Price("10 HIVE", "1 HBD")``
    * ``Price(Amount("10 HIVE"), Amount("1 HBD"))``
    * ``Price(1.0, "HBD/HIVE")``

    Instances of this class can be used in regular mathematical expressions
    (``+-*/%``) such as:

    .. code-block:: python

        >>> from nectar.price import Price
        >>> from nectar import Hive
        >>> hv = Hive("https://api.hive.blog")
        >>> Price("0.3314 HBD/HIVE", blockchain_instance=hv) * 2
        0.662804 HBD/HIVE
        >>> Price(0.3314, "HBD", "HIVE", blockchain_instance=hv)
        0.331402 HBD/HIVE

    """

    def __init__(
        self,
        price: Union[str, dict[str, Any], "Price"] | None = None,
        base: str | Amount | Asset | None = None,
        quote: str | Amount | Asset | None = None,
        base_asset: str | None = None,  # to identify sell/buy
        blockchain_instance: Any | None = None,
    ) -> None:
        """
        Initialize a Price object representing a ratio between a base and quote asset.

        This constructor accepts multiple input forms and normalizes them into internal
        "base" and "quote" Amount entries. Supported usages:
        - price: str like "X BASE/QUOTE" with no base/quote: parses symbols and creates
          Amounts from the fractional representation of X.
        - price: dict with "base" and "quote": loads Amounts directly (raises AssertionError
          if a top-level "price" key is present).
        - price: numeric (float/int/Decimal) with base and quote provided as Asset or
          symbol strings: converts the numeric value to a Fraction and builds Amounts.
        - price: str representing an Amount and base: when price is a string and base is
          a symbol string, price and base are used to build quote/base Amounts.
        - price and base as Amount instances: accepts Amount objects directly.
        - price is None with base and quote as symbol strings or Amounts: loads assets
          or Amounts respectively.

        Parameters (not exhaustive):
        - price: numeric, str, dict, or Amount — the price or a representation used to
          derive base/quote Amounts.
        - base: Asset, Amount, or str — identifies the base side (or a symbol string
          used to parse both symbols when combined with a numeric price).
        - quote: Asset, Amount, or str — identifies the quote side.
        - base_asset: optional; used only as an identifier flag for buy/sell contexts.
        - blockchain_instance: blockchain context used to construct Asset/Amount (omitted
          from param listing as a shared service).

        Raises:
        - AssertionError: if a dict `price` includes a top-level "price" key.
        - ValueError: if the combination of inputs cannot be parsed into base and quote.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if price == "":
            price = None
        if price is not None and isinstance(price, str) and not base and not quote:
            price, assets = price.split(" ")
            base_symbol, quote_symbol = assets_from_string(assets)
            base = Asset(base_symbol, blockchain_instance=self.blockchain)
            quote = Asset(quote_symbol, blockchain_instance=self.blockchain)
            frac = Fraction(float(price)).limit_denominator(10 ** base["precision"])
            self["quote"] = Amount(
                amount=frac.denominator, asset=quote, blockchain_instance=self.blockchain
            )
            self["base"] = Amount(
                amount=frac.numerator, asset=base, blockchain_instance=self.blockchain
            )

        elif price is not None and isinstance(price, dict) and "base" in price and "quote" in price:
            if "price" in price:
                raise AssertionError("You cannot provide a 'price' this way")
            # Regular 'price' objects according to hive-core
            # base_id = price["base"]["asset_id"]
            # if price["base"]["asset_id"] == base_id:
            self["base"] = Amount(price["base"], blockchain_instance=self.blockchain)
            self["quote"] = Amount(price["quote"], blockchain_instance=self.blockchain)
            # else:
            #    self["quote"] = Amount(price["base"], blockchain_instance=self.blockchain)
            #    self["base"] = Amount(price["quote"], blockchain_instance=self.blockchain)

        elif price is not None and isinstance(base, Asset) and isinstance(quote, Asset):
            if isinstance(price, Price):
                frac = Fraction(float(price["price"])).limit_denominator(10 ** base["precision"])
            elif isinstance(price, (int, float, str)):
                frac = Fraction(float(price)).limit_denominator(10 ** base["precision"])
            else:
                raise ValueError("Unsupported price type")
            self["quote"] = Amount(
                amount=frac.denominator, asset=quote, blockchain_instance=self.blockchain
            )
            self["base"] = Amount(
                amount=frac.numerator, asset=base, blockchain_instance=self.blockchain
            )

        elif price is not None and isinstance(base, str) and isinstance(quote, str):
            base = Asset(base, blockchain_instance=self.blockchain)
            quote = Asset(quote, blockchain_instance=self.blockchain)
            if isinstance(price, Price):
                frac = Fraction(float(price["price"])).limit_denominator(10 ** base["precision"])
            elif isinstance(price, (int, float, str)):
                frac = Fraction(float(price)).limit_denominator(10 ** base["precision"])
            else:
                raise ValueError("Unsupported price type")
            self["quote"] = Amount(
                amount=frac.denominator, asset=quote, blockchain_instance=self.blockchain
            )
            self["base"] = Amount(
                amount=frac.numerator, asset=base, blockchain_instance=self.blockchain
            )

        elif price is None and isinstance(base, str) and isinstance(quote, str):
            self["quote"] = Amount(quote, blockchain_instance=self.blockchain)
            self["base"] = Amount(base, blockchain_instance=self.blockchain)
        elif price is not None and isinstance(price, str) and isinstance(base, str):
            self["quote"] = Amount(price, blockchain_instance=self.blockchain)
            self["base"] = Amount(base, blockchain_instance=self.blockchain)
        # len(args) > 1

        elif isinstance(price, Amount) and isinstance(base, Amount):
            self["quote"], self["base"] = price, base

        # len(args) == 0
        elif price is None and isinstance(base, Amount) and isinstance(quote, Amount):
            self["quote"] = quote
            self["base"] = base

        elif (
            isinstance(price, float) or isinstance(price, int) or isinstance(price, Decimal)
        ) and isinstance(base, str):
            base_symbol, quote_symbol = assets_from_string(base)
            base = Asset(base_symbol, blockchain_instance=self.blockchain)
            quote = Asset(quote_symbol, blockchain_instance=self.blockchain)
            frac = Fraction(float(price)).limit_denominator(10 ** base["precision"])
            self["quote"] = Amount(
                amount=frac.denominator, asset=quote, blockchain_instance=self.blockchain
            )
            self["base"] = Amount(
                amount=frac.numerator, asset=base, blockchain_instance=self.blockchain
            )

        else:
            raise ValueError("Couldn't parse 'Price'.")

    def __setitem__(self, key: str, value: Any) -> None:
        dict.__setitem__(self, key, value)
        if (
            "quote" in self and "base" in self and self["base"] and self["quote"]
        ):  # don't derive price for deleted Orders
            dict.__setitem__(
                self, "price", self._safedivide(self["base"]["amount"], self["quote"]["amount"])
            )

    def copy(self) -> "Price":
        return Price(
            None,
            base=self["base"].copy(),
            quote=self["quote"].copy(),
            blockchain_instance=self.blockchain,
        )

    def _safedivide(
        self, a: int | float | Decimal, b: int | float | Decimal
    ) -> int | float | Decimal:
        if b != 0.0:
            return float(a) / float(b)
        else:
            return float("inf")

    def symbols(self) -> tuple[str, str]:
        return self["base"]["symbol"], self["quote"]["symbol"]

    def as_base(self, base: str | Asset) -> "Price":
        """
        Return a copy of this Price expressed with the given asset as the base.

        If `base` matches the current base symbol this returns a shallow copy.
        If `base` matches the current quote symbol this returns a copy with base and quote inverted.
        Raises InvalidAssetException if `base` is neither the base nor the quote of this price.

        Parameters:
            base (str): Asset symbol to use as the base (e.g., "HIVE" or "HBD").

        Returns:
            Price: A new Price instance whose base asset is `base`.
        """
        if base == self["base"]["symbol"]:
            return self.copy()
        elif base == self["quote"]["symbol"]:
            return self.copy().invert()
        else:
            raise InvalidAssetException

    def as_quote(self, quote: str | Asset) -> "Price":
        """
        Return a Price instance expressed with the given quote asset symbol.

        If `quote` matches the current quote symbol, returns a copy of this Price.
        If `quote` matches the current base symbol, returns a copied, inverted Price.
        A new object is always returned (the original is not modified).

        Parameters:
            quote (str): Asset symbol to use as the quote (e.g., "HBD" or "HIVE").

        Returns:
            Price: A Price object with `quote` as the quote asset.

        Raises:
            InvalidAssetException: If `quote` does not match either the current base or quote symbol.
        """
        if quote == self["quote"]["symbol"]:
            return self.copy()
        elif quote == self["base"]["symbol"]:
            return self.copy().invert()
        else:
            raise InvalidAssetException

    def invert(self) -> "Price":
        """
        Invert the price in place, swapping base and quote assets (e.g., HBD/HIVE -> HIVE/HBD).

        Returns:
            self: The same Price instance after inversion.

        Example:
            >>> from nectar.price import Price
            >>> from nectar import Hive
            >>> hv = Hive("https://api.hive.blog")
            >>> Price("0.3314 HBD/HIVE", blockchain_instance=hv).invert()
            3.017483 HIVE/HBD
        """
        tmp = self["quote"]
        self["quote"] = self["base"]
        self["base"] = tmp
        return self

    def json(self) -> dict[str, Any]:
        return {"base": self["base"].json(), "quote": self["quote"].json()}

    def __repr__(self) -> str:
        return "{price:.{precision}f} {base}/{quote}".format(
            price=self["price"],
            base=self["base"]["symbol"],
            quote=self["quote"]["symbol"],
            precision=(self["base"]["asset"]["precision"] + self["quote"]["asset"]["precision"]),
        )

    def __float__(self) -> float:
        return float(self["price"])

    def _check_other(self, other: "Price") -> None:
        if not other["base"]["symbol"] == self["base"]["symbol"]:
            raise AssertionError()
        if not other["quote"]["symbol"] == self["quote"]["symbol"]:
            raise AssertionError()

    def __mul__(self, other: Union["Price", Amount, float, int]) -> "Price":
        a = self.copy()
        if isinstance(other, Price):
            # Rotate/invert other
            if (
                self["quote"]["symbol"] not in other.symbols()
                and self["base"]["symbol"] not in other.symbols()
            ):
                raise InvalidAssetException

            # base/quote = a/b
            # a/b * b/c = a/c
            a = self.copy()
            if self["quote"]["symbol"] == other["base"]["symbol"]:
                a["base"] = Amount(
                    float(self["base"]) * float(other["base"]),
                    self["base"]["symbol"],
                    blockchain_instance=self.blockchain,
                )
                a["quote"] = Amount(
                    float(self["quote"]) * float(other["quote"]),
                    other["quote"]["symbol"],
                    blockchain_instance=self.blockchain,
                )
            # a/b * c/a =  c/b
            elif self["base"]["symbol"] == other["quote"]["symbol"]:
                a["base"] = Amount(
                    float(self["base"]) * float(other["base"]),
                    other["base"]["symbol"],
                    blockchain_instance=self.blockchain,
                )
                a["quote"] = Amount(
                    float(self["quote"]) * float(other["quote"]),
                    self["quote"]["symbol"],
                    blockchain_instance=self.blockchain,
                )
            else:
                raise ValueError("Wrong rotation of prices")
        elif isinstance(other, Amount):
            check_asset(other["asset"], self["quote"]["asset"], self.blockchain)
            a = other.copy() * self["price"]
            a["asset"] = self["base"]["asset"].copy()
            a["symbol"] = self["base"]["asset"]["symbol"]
        else:
            a["base"] *= other
        return a

    def __imul__(self, other: Union["Price", Amount, float, int]) -> "Price":
        if isinstance(other, Price):
            tmp = self * other
            self["base"] = tmp["base"]
            self["quote"] = tmp["quote"]
        else:
            self["base"] *= other
        return self

    def __div__(self, other: Union["Price", Amount, float, int]) -> Union["Price", float]:
        a = self.copy()
        if isinstance(other, Price):
            # Rotate/invert other
            if sorted(self.symbols()) == sorted(other.symbols()):
                return float(self.as_base(self["base"]["symbol"])) / float(
                    other.as_base(self["base"]["symbol"])
                )
            elif self["quote"]["symbol"] in other.symbols():
                other = other.as_base(self["quote"]["symbol"])
            elif self["base"]["symbol"] in other.symbols():
                other = other.as_base(self["base"]["symbol"])
            else:
                raise InvalidAssetException
            a["base"] = Amount(
                float(self["base"].amount / other["base"].amount),
                other["quote"]["symbol"],
                blockchain_instance=self.blockchain,
            )
            a["quote"] = Amount(
                float(self["quote"].amount / other["quote"].amount),
                self["quote"]["symbol"],
                blockchain_instance=self.blockchain,
            )
        elif isinstance(other, Amount):
            check_asset(other["asset"], self["quote"]["asset"], self.blockchain)
            a = other.copy() / self["price"]
            a["asset"] = self["base"]["asset"].copy()
            a["symbol"] = self["base"]["asset"]["symbol"]
        else:
            a["base"] /= other
        return a

    def __idiv__(self, other: Union["Price", Amount, float, int]) -> "Price":
        if isinstance(other, Price):
            tmp = self / other
            # tmp can be either Price or float, handle both cases
            if isinstance(tmp, (int, float)):
                # If division returned a float, we can't do in-place modification
                # Convert to Price by updating the base amount
                self["base"] = Amount(
                    float(tmp) * float(self["base"]),
                    self["base"]["symbol"],
                    blockchain_instance=self.blockchain,
                )
            else:
                # tmp is a Price, do normal in-place update
                self["base"] = tmp["base"]
                self["quote"] = tmp["quote"]
        else:
            self["base"] /= other
        return self

    def __floordiv__(self, other: Any) -> "Price":
        raise NotImplementedError("This is not possible as the price is a ratio")

    def __ifloordiv__(self, other: Any) -> "Price":
        raise NotImplementedError("This is not possible as the price is a ratio")

    def __lt__(self, other: Union["Price", Amount, float, int]) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] < other["price"]
        else:
            return self["price"] < float(other or 0)

    def __le__(self, other: Union["Price", Amount, float, int]) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] <= other["price"]
        else:
            return self["price"] <= float(other or 0)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] == other["price"]
        if isinstance(other, (float, int)):
            return self["price"] == float(other or 0)
        return False

    def __ne__(self, other: object) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] != other["price"]
        if isinstance(other, (float, int)):
            return self["price"] != float(other or 0)
        return True

    def __ge__(self, other: Union["Price", Amount, float, int]) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] >= other["price"]
        else:
            return self["price"] >= float(other or 0)

    def __gt__(self, other: Union["Price", Amount, float, int]) -> bool:
        if isinstance(other, Price):
            self._check_other(other)
            return self["price"] > other["price"]
        else:
            return self["price"] > float(other or 0)

    __truediv__ = __div__
    __truemul__ = __mul__
    __str__ = __repr__

    @property
    def market(self) -> "Market":
        """Open the corresponding market

        :returns: Instance of :class:`nectar.market.Market` for the
                  corresponding pair of assets.
        """
        from .market import Market

        return Market(
            base=self["base"]["asset"],
            quote=self["quote"]["asset"],
            blockchain_instance=self.blockchain,
        )


class Order(Price):
    """This class inherits :class:`nectar.price.Price` but has the ``base``
    and ``quote`` Amounts not only be used to represent the price (as a
    ratio of base and quote) but instead has those amounts represent the
    amounts of an actual order!

    :param Hive blockchain_instance: Hive instance

    .. note::

            If an order is marked as deleted, it will carry the
            'deleted' key which is set to ``True`` and all other
            data be ``None``.
    """

    def __init__(
        self,
        base: dict[str, Any] | Amount,
        quote: Amount | None = None,
        blockchain_instance: Any | None = None,
        **kwargs: Any,
    ) -> None:
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if isinstance(base, dict) and "sell_price" in base:
            super().__init__(base["sell_price"], blockchain_instance=self.blockchain)
            self["id"] = base.get("id")
        elif isinstance(base, dict) and "min_to_receive" in base and "amount_to_sell" in base:
            super().__init__(
                Amount(base["min_to_receive"], blockchain_instance=self.blockchain),
                Amount(base["amount_to_sell"], blockchain_instance=self.blockchain),
                blockchain_instance=self.blockchain,
            )
            self["id"] = base.get("id")
        elif isinstance(base, Amount) and isinstance(quote, Amount):
            super().__init__(None, base=base, quote=quote, blockchain_instance=self.blockchain)
        else:
            raise ValueError("Unknown format to load Order")

    def __repr__(self) -> str:
        if "deleted" in self and self["deleted"]:
            return "deleted order %s" % self["id"]
        else:
            t = ""
            if "time" in self and self["time"]:
                t += "(%s) " % self["time"]
            if "type" in self and self["type"]:
                t += "%s " % str(self["type"])
            if "quote" in self and self["quote"]:
                t += "%s " % str(self["quote"])
            if "base" in self and self["base"]:
                t += "%s " % str(self["base"])
            return t + "@ " + Price.__repr__(self)

    __str__ = __repr__


class FilledOrder(Price):
    """This class inherits :class:`nectar.price.Price` but has the ``base``
    and ``quote`` Amounts not only be used to represent the price (as a
    ratio of base and quote) but instead has those amounts represent the
    amounts of an actually filled order!

    :param Hive blockchain_instance: Hive instance

    .. note:: Instances of this class come with an additional ``date`` key
              that shows when the order has been filled!
    """

    def __init__(
        self, order: dict[str, Any], blockchain_instance: Any | None = None, **kwargs: Any
    ) -> None:
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if isinstance(order, dict) and "current_pays" in order and "open_pays" in order:
            # filled orders from account history
            if "op" in order:
                order = order["op"]

            super().__init__(
                Amount(order["open_pays"], blockchain_instance=self.blockchain),
                Amount(order["current_pays"], blockchain_instance=self.blockchain),
                blockchain_instance=self.blockchain,
            )
            if "date" in order:
                self["date"] = formatTimeString(order["date"])

        else:
            raise ValueError("Couldn't parse 'Price'.")

    def json(self) -> dict[str, Any]:
        return {
            "date": formatTimeString(self["date"]),
            "current_pays": self["base"].json(),
            "open_pays": self["quote"].json(),
        }

    def __repr__(self) -> str:
        t = ""
        if "date" in self and self["date"]:
            t += "(%s) " % self["date"]
        if "type" in self and self["type"]:
            t += "%s " % str(self["type"])
        if "quote" in self and self["quote"]:
            t += "%s " % str(self["quote"])
        if "base" in self and self["base"]:
            t += "%s " % str(self["base"])
        return t + "@ " + Price.__repr__(self)

    __str__ = __repr__
