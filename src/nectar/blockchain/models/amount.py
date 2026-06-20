from collections.abc import Iterator, MutableMapping
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Any, Union

from nectar.blockchain.models.asset import Asset
from nectar.instance import shared_blockchain_instance

if TYPE_CHECKING:
    from .price import Price


def check_asset(other: Any, self: Any, hv: Any) -> None:
    """
    Assert that two asset representations refer to the same asset.

    If both `other` and `self` are dicts containing an "asset" key, each asset id is wrapped in an Asset using the provided blockchain instance and compared for equality. Otherwise the two values are compared directly. Raises AssertionError if the values do not match.
    """
    if (
        isinstance(other, (dict, MutableMapping))
        and "asset" in other
        and isinstance(self, (dict, MutableMapping))
        and "asset" in self
    ):
        if not Asset(other["asset"], blockchain_instance=hv) == Asset(
            self["asset"], blockchain_instance=hv
        ):
            raise AssertionError()
    else:
        if not other == self:
            raise AssertionError()


def quantize(amount: str | int | float | Decimal, precision: int) -> Decimal:
    # make sure amount is decimal and has the asset precision
    amount = Decimal(amount)
    places = Decimal(10) ** (-precision)
    return amount.quantize(places, rounding=ROUND_DOWN)


class Amount(MutableMapping):
    """This class deals with Amounts of any asset to simplify dealing with the tuple::

        (amount, asset)

    :param list args: Allows to deal with different representations of an amount
    :param float amount: Let's create an instance with a specific amount
    :param str asset: Let's you create an instance with a specific asset (symbol)
    :param boolean fixed_point_arithmetic: when set to True, all operations are fixed
        point operations and the amount is always be rounded down to the precision
    :param Blockchain blockchain_instance: Blockchain instance
    :returns: All data required to represent an Amount/Asset
    :rtype: dict
    :raises ValueError: if the data provided is not recognized

    Way to obtain a proper instance:

        * ``args`` can be a string, e.g.:  "1 HBD"
        * ``args`` can be a dictionary containing ``amount`` and ``asset_id``
        * ``args`` can be a dictionary containing ``amount`` and ``asset``
        * ``args`` can be a list of a ``float`` and ``str`` (symbol)
        * ``args`` can be a list of a ``float`` and a :class:`nectar.asset.Asset`
        * ``amount`` and ``asset`` are defined manually

    An instance is a dictionary and comes with the following keys:

        * ``amount`` (float)
        * ``symbol`` (str)
        * ``asset`` (instance of :class:`nectar.asset.Asset`)

    Instances of this class can be used in regular mathematical expressions
    (``+-*/%``) such as:

    .. testcode::

        from nectar.amount import Amount
        from nectar.asset import Asset
        a = Amount("1 HIVE")
        b = Amount(1, "HIVE")
        c = Amount("20", Asset("HIVE"))
        a + b
        a * 2
        a += b
        a /= 2.0

    .. testoutput::

        2.000 HIVE
        2.000 HIVE

    """

    def __init__(
        self,
        amount: Union[str, int, float, Decimal, list, dict, "Amount"],
        asset: str | Asset | None = None,
        fixed_point_arithmetic: bool = False,
        new_appbase_format: bool = True,
        blockchain_instance: Any = None,
        json_str: bool = False,
        **kwargs,
    ) -> None:
        """Initialize an Amount object representing a quantity of a specific blockchain asset."""
        self._data = {}
        self["asset"] = {}
        self.new_appbase_format = new_appbase_format
        self.fixed_point_arithmetic = fixed_point_arithmetic

        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if amount and asset is None and isinstance(amount, Amount):
            # Copy Asset object
            self["amount"] = amount["amount"]
            self["symbol"] = amount["symbol"]
            self["asset"] = amount["asset"]

        elif amount and asset is None and isinstance(amount, list) and len(amount) == 3:
            # Copy Asset object
            self["amount"] = Decimal(amount[0]) / Decimal(10 ** amount[1])
            self["asset"] = Asset(amount[2], blockchain_instance=self.blockchain)
            self["symbol"] = self["asset"]["symbol"]

        elif (
            amount
            and asset is None
            and isinstance(amount, dict)
            and "amount" in amount
            and "nai" in amount
            and "precision" in amount
        ):
            # Copy Asset object
            self.new_appbase_format = True
            self["amount"] = Decimal(amount["amount"]) / Decimal(10 ** amount["precision"])
            self["asset"] = Asset(amount["nai"], blockchain_instance=self.blockchain)
            self["symbol"] = self["asset"]["symbol"]

        elif amount is not None and asset is None and isinstance(amount, str):
            self["amount"], self["symbol"] = amount.split(" ")
            self["asset"] = Asset(self["symbol"], blockchain_instance=self.blockchain)

        elif (
            amount
            and asset is None
            and isinstance(amount, dict)
            and "amount" in amount
            and "asset_id" in amount
        ):
            self["asset"] = Asset(amount["asset_id"], blockchain_instance=self.blockchain)
            self["symbol"] = self["asset"]["symbol"]
            self["amount"] = Decimal(amount["amount"]) / Decimal(10 ** self["asset"]["precision"])

        elif (
            amount
            and asset is None
            and isinstance(amount, dict)
            and "amount" in amount
            and "asset" in amount
        ):
            self["asset"] = Asset(amount["asset"], blockchain_instance=self.blockchain)
            self["symbol"] = self["asset"]["symbol"]
            self["amount"] = Decimal(amount["amount"]) / Decimal(10 ** self["asset"]["precision"])

        elif isinstance(amount, (float)) and asset and isinstance(asset, Asset):
            self["amount"] = str(amount)
            self["asset"] = asset
            self["symbol"] = self["asset"]["symbol"]

        elif isinstance(amount, (int, Decimal)) and asset and isinstance(asset, Asset):
            self["amount"] = amount
            self["asset"] = asset
            self["symbol"] = self["asset"]["symbol"]

        elif isinstance(amount, (float)) and asset and isinstance(asset, dict):
            self["amount"] = str(amount)
            self["asset"] = asset
            self["symbol"] = self["asset"]["symbol"]

        elif isinstance(amount, (int, Decimal)) and asset and isinstance(asset, dict):
            self["amount"] = amount
            self["asset"] = asset
            self["symbol"] = self["asset"]["symbol"]

        elif isinstance(amount, (float)) and asset and isinstance(asset, str):
            self["amount"] = str(amount)
            self["asset"] = Asset(asset, blockchain_instance=self.blockchain)
            self["symbol"] = asset

        elif isinstance(amount, (int, Decimal)) and asset and isinstance(asset, str):
            self["amount"] = amount
            self["asset"] = Asset(asset, blockchain_instance=self.blockchain)
            self["symbol"] = asset
        elif amount and asset and isinstance(asset, Asset):
            self["amount"] = amount
            self["symbol"] = asset["symbol"]
            self["asset"] = asset
        elif amount and asset and isinstance(asset, str):
            self["amount"] = amount
            self["asset"] = Asset(asset, blockchain_instance=self.blockchain)
            self["symbol"] = self["asset"]["symbol"]
        else:
            raise ValueError
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        else:
            self["amount"] = Decimal(self["amount"])

    def copy(self) -> "Amount":
        """Copy the instance and make sure not to use a reference"""
        return Amount(
            amount=self["amount"],
            asset=self["asset"].copy(),
            new_appbase_format=self.new_appbase_format,
            fixed_point_arithmetic=self.fixed_point_arithmetic,
            blockchain_instance=self.blockchain,
        )

    @property
    def amount(self) -> float:
        """Returns the amount as float"""
        return float(self["amount"])

    @property
    def amount_decimal(self) -> Decimal:
        """Returns the amount as decimal"""
        return self["amount"]

    @property
    def symbol(self) -> str:
        """Returns the symbol of the asset"""
        return self["symbol"]

    def as_tuple(self) -> tuple[float, str]:
        return float(self), self.symbol

    @property
    def asset(self) -> Asset:
        """
        Return the Asset object for this Amount, constructing it lazily if missing.

        If the internal 'asset' entry is falsy, this creates a nectar.asset.Asset using the stored symbol
        and this Amount's blockchain instance, stores it in 'asset', and returns it. Always returns an
        Asset instance.
        """
        if not isinstance(self["asset"], Asset):
            self["asset"] = Asset(self["symbol"], blockchain_instance=self.blockchain)
        return self["asset"]

    def json(self) -> str | dict | list:
        asset_obj = self["asset"]
        if isinstance(asset_obj, Asset):
            asset_precision = asset_obj["precision"]
            asset_identifier = asset_obj["asset"]
        elif isinstance(asset_obj, dict):
            asset_precision = asset_obj.get("precision")
            asset_identifier = asset_obj.get("asset")
        else:
            resolved_asset = Asset(self["symbol"], blockchain_instance=self.blockchain)
            self["asset"] = resolved_asset
            asset_precision = resolved_asset["precision"]
            asset_identifier = resolved_asset["asset"]

        if asset_precision is None or asset_identifier is None:
            return str(self)

        amount_value = str(int(self))

        if self.new_appbase_format:
            payload = {
                "amount": amount_value,
                "nai": asset_identifier,
                "precision": asset_precision,
            }
        else:
            payload = [amount_value, asset_precision, asset_identifier]
        return payload

    def __str__(self) -> str:
        amount = quantize(self["amount"], self["asset"]["precision"])
        symbol = self["symbol"]
        return "{:.{prec}f} {}".format(amount, symbol, prec=self["asset"]["precision"])

    def __float__(self) -> float:
        if self.fixed_point_arithmetic:
            return float(quantize(self["amount"], self["asset"]["precision"]))
        else:
            return float(self["amount"])

    def __int__(self) -> int:
        amount = quantize(self["amount"], self["asset"]["precision"])
        return int(amount * 10 ** self["asset"]["precision"])

    def __add__(self, other: Union["Amount", int, float, str]) -> "Amount":
        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            a["amount"] += other["amount"]
        else:
            a["amount"] += Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __sub__(self, other: Union["Amount", int, float, str]) -> "Amount":
        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            a["amount"] -= other["amount"]
        else:
            a["amount"] -= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __mul__(self, other: Union[int, float, Decimal, "Amount", "Price"]) -> "Amount":
        from .price import Price

        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            a["amount"] *= other["amount"]
        elif isinstance(other, Price):
            if not self["asset"] == other["quote"]["asset"]:
                raise AssertionError()
            a = self.copy() * other["price"]
            a["asset"] = other["base"]["asset"].copy()
            a["symbol"] = other["base"]["asset"]["symbol"]
        else:
            a["amount"] *= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __floordiv__(self, other: Union[int, float, Decimal, "Amount"]) -> Union["Amount", "Price"]:
        a = self.copy()
        if isinstance(other, Amount):
            from .price import Price

            check_asset(other["asset"], self["asset"], self.blockchain)
            return Price(self, other, blockchain_instance=self.blockchain)
        else:
            a["amount"] //= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __div__(
        self, other: Union[int, float, Decimal, "Amount", "Price"]
    ) -> Union["Amount", "Price"]:
        from .price import Price

        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return Price(self, other, blockchain_instance=self.blockchain)
        elif isinstance(other, Price):
            if not self["asset"] == other["base"]["asset"]:
                raise AssertionError()
            a = self.copy()
            a["amount"] = a["amount"] / other["price"]
            a["asset"] = other["quote"]["asset"].copy()
            a["symbol"] = other["quote"]["asset"]["symbol"]
        else:
            a["amount"] /= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __mod__(self, other: Union[int, float, Decimal, "Amount"]) -> "Amount":
        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            a["amount"] %= other["amount"]
        else:
            a["amount"] %= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __pow__(self, other: Union[int, float, Decimal, "Amount"]) -> "Amount":
        a = self.copy()
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            a["amount"] **= other["amount"]
        else:
            a["amount"] **= Decimal(other)
        if self.fixed_point_arithmetic:
            a["amount"] = quantize(a["amount"], self["asset"]["precision"])
        return a

    def __iadd__(self, other: Union["Amount", int, float, str]) -> "Amount":
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            self["amount"] += other["amount"]
        else:
            self["amount"] += Decimal(other)
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __isub__(self, other: Union["Amount", int, float, str]) -> "Amount":
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            self["amount"] -= other["amount"]
        else:
            self["amount"] -= Decimal(other)
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __imul__(self, other: Union[int, float, Decimal, "Amount"]) -> "Amount":
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            self["amount"] *= other["amount"]
        else:
            self["amount"] *= Decimal(other)

        self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __idiv__(self, other: int | float | Decimal) -> "Amount":
        """
        In-place division: divide this Amount by another Amount or numeric value and return self.

        If `other` is an Amount, asserts asset compatibility and divides this object's internal amount by the other's amount. If `other` is numeric, divides by Decimal(other). When `fixed_point_arithmetic` is enabled, the result is quantized to this asset's precision.

        Returns:
            self (Amount): The mutated Amount instance.

        Raises:
            AssertionError: If `other` is an Amount with a different asset (via check_asset).
        """
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            self["amount"] = self["amount"] / other["amount"]
        else:
            self["amount"] /= Decimal(other)
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __ifloordiv__(self, other: Union[int, float, Decimal, "Amount"]) -> "Amount":
        if isinstance(other, Amount):
            self["amount"] //= other["amount"]
        else:
            self["amount"] //= Decimal(other)
        self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __imod__(self, other: int | float | Decimal) -> "Amount":
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            self["amount"] %= other["amount"]
        else:
            self["amount"] %= Decimal(other)
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __ipow__(self, other: Union[int, float, Decimal, "Amount"]) -> "Amount":
        if isinstance(other, Amount):
            self["amount"] **= other["amount"]
        else:
            self["amount"] **= Decimal(other)
        if self.fixed_point_arithmetic:
            self["amount"] = quantize(self["amount"], self["asset"]["precision"])
        return self

    def __lt__(self, other: Union["Amount", int, float, str]) -> bool:
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount < quantize(other["amount"], self["asset"]["precision"])
        else:
            return quant_amount < quantize((other or 0), self["asset"]["precision"])

    def __le__(self, other: Union["Amount", int, float, str]) -> bool:
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount <= quantize(other["amount"], self["asset"]["precision"])
        else:
            return quant_amount <= quantize((other or 0), self["asset"]["precision"])

    def __eq__(self, other: object) -> bool:
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount == quantize(other["amount"], self["asset"]["precision"])
        if isinstance(other, (int, float, str, Decimal)):
            return quant_amount == quantize((other or 0), self["asset"]["precision"])
        return False

    def __ne__(self, other: object) -> bool:
        """
        Return True if this Amount is not equal to `other`.

        Compares values after quantizing both sides to this amount's asset precision. If `other` is an Amount, its asset must match this Amount's asset (an assertion is raised on mismatch) and the comparison uses both amounts quantized to the shared precision. If `other` is numeric or None, it is treated as a numeric value (None → 0) and compared after quantization.

        Returns:
                bool: True when the quantized values differ, False otherwise.
        """
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount != quantize(other["amount"], self["asset"]["precision"])
        if isinstance(other, (int, float, str, Decimal)):
            return quant_amount != quantize((other or 0), self["asset"]["precision"])
        return True

    def __ge__(self, other: Union["Amount", int, float, str]) -> bool:
        """
        Return True if this Amount is greater than or equal to `other`.

        Performs comparison after quantizing both values to this Amount's asset precision. If `other` is an Amount, its asset must match this Amount's asset (an AssertionError is raised on mismatch). If `other` is None, it is treated as zero. Returns a boolean.
        """
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount >= quantize(other["amount"], self["asset"]["precision"])
        else:
            return quant_amount >= quantize((other or 0), self["asset"]["precision"])

    def __gt__(self, other: Union["Amount", int, float, str]) -> bool:
        quant_amount = quantize(self["amount"], self["asset"]["precision"])
        if isinstance(other, Amount):
            check_asset(other["asset"], self["asset"], self.blockchain)
            return quant_amount > quantize(other["amount"], self["asset"]["precision"])
        else:
            return quant_amount > quantize((other or 0), self["asset"]["precision"])

    __repr__ = __str__
    __truediv__ = __div__
    __itruediv__ = __idiv__
    __truemul__ = __mul__

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)
