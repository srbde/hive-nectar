import decimal
import json
import struct
from collections import OrderedDict
from typing import Any

from nectargraphenebase.account import PublicKey
from nectargraphenebase.chains import known_chains
from nectargraphenebase.objects import GrapheneObject, isArgsThisClass
from nectargraphenebase.objects import Operation as GPHOperation
from nectargraphenebase.types import (
    Array,
    Bytes,
    Id,
    Int16,
    Map,
    PointInTime,
    Static_variant,
    String,
    Uint16,
    Uint32,
    Uint64,
)

from .operationids import operations

default_prefix = "STM"


def value_to_decimal(value: str | float | int, decimal_places: int) -> decimal.Decimal:
    decimal.getcontext().rounding = decimal.ROUND_DOWN  # define rounding method
    return decimal.Decimal(str(float(value))).quantize(decimal.Decimal(f"1e-{decimal_places}"))


class Amount:
    def __init__(
        self,
        d: str | Any,
        prefix: str = default_prefix,
        json_str: bool = False,
        **kwargs,
    ) -> None:
        self.json_str = json_str
        if isinstance(d, str):
            self.amount, self.symbol = d.strip().split(" ")
            self.precision = None
            for c in known_chains:
                if self.precision is not None:
                    continue
                if known_chains[c]["prefix"] != prefix:
                    continue
                for asset in known_chains[c]["chain_assets"]:
                    if self.precision is not None:
                        continue
                    if asset["symbol"] == self.symbol:
                        self.precision = asset["precision"]
                        self.asset = asset["asset"]
                    elif asset["asset"] == self.symbol:
                        self.precision = asset["precision"]
                        self.asset = asset["asset"]
            if self.precision is None:
                raise Exception("Asset unknown")
            self.amount = round(
                value_to_decimal(float(self.amount), self.precision) * 10**self.precision
            )
            # Workaround to allow transfers in HIVE

            self.str_repr = "{:.{}f} {}".format(
                (float(self.amount) / 10**self.precision), self.precision, self.symbol
            )
        elif isinstance(d, list):
            self.amount = d[0]
            self.asset = d[2]
            self.precision = d[1]
            self.symbol = None
            for c in known_chains:
                if known_chains[c]["prefix"] != prefix:
                    continue
                for asset in known_chains[c]["chain_assets"]:
                    if asset["asset"] == self.asset:
                        self.symbol = asset["symbol"]
            if self.symbol is None:
                raise ValueError("Unknown NAI, cannot resolve symbol")
            a = Array([String(d[0]), d[1], d[2]])
            self.str_repr = str(a.__str__())
        elif isinstance(d, dict) and "nai" in d:
            self.asset = d["nai"]
            self.symbol = None
            for c in known_chains:
                if known_chains[c]["prefix"] != prefix:
                    continue
                for asset in known_chains[c]["chain_assets"]:
                    if asset["asset"] == d["nai"]:
                        self.symbol = asset["symbol"]
            if self.symbol is None:
                raise ValueError("Unknown NAI, cannot resolve symbol")
            self.amount = d["amount"]
            self.precision = d["precision"]
            self.str_repr = json.dumps(d)
        elif isinstance(d, dict) and "amount" in d and "asset" in d:
            self.amount = d["amount"]
            asset_obj = d["asset"]
            self.precision = asset_obj["precision"]
            self.asset = asset_obj.get("asset", asset_obj.get("nai"))
            self.symbol = asset_obj.get("symbol")
            self.amount = round(value_to_decimal(self.amount, self.precision) * 10**self.precision)
            if hasattr(d, "json"):
                self.str_repr = json.dumps(d.json())
            else:
                # Fallback or manual construction if needed, but for now just str(d) or skip
                # If d is a dict with Decimal, we can't json dump it directly.
                # But we only expect nectar.amount.Amount here which has .json()
                self.str_repr = json.dumps(
                    d
                )  # This might still fail if not Amount object but just dict with Decimal

        else:
            self.amount = d.amount
            self.symbol = d.symbol
            self.asset = d.asset
            self.precision = d.precision
            self.amount = round(value_to_decimal(self.amount, self.precision) * 10**self.precision)
            self.str_repr = str(d)
            # self.str_repr = json.dumps((d.json()))
            # self.str_repr = '{:.{}f} {}'.format((float(self.amount) / 10 ** self.precision), self.precision, self.asset)

    def __bytes__(self) -> bytes:
        # padding
        # The nodes still serialize the legacy symbol name for HBD as 'SBD' and HIVE as 'STEEM' in wire format.
        # To match get_transaction_hex and avoid digest mismatches, map 'HBD' -> 'SBD' and 'HIVE' -> 'STEEM' on serialization.
        """
        Serialize the Amount into its wire-format byte representation.

        Returns:
            bytes: 8-byte little-endian signed integer amount, followed by a 1-byte precision,
                   followed by a 7-byte ASCII symbol padded with null bytes. On serialization,
                   the symbol is remapped for legacy wire-format compatibility: "HBD" -> "SBD"
                   and "HIVE" -> "STEEM".
        """
        _sym = self.symbol
        if _sym == "HBD":
            _sym = "SBD"
        elif _sym == "HIVE":
            _sym = "STEEM"
        symbol = str(_sym) + "\x00" * (7 - len(str(_sym)))
        return (
            struct.pack("<q", int(self.amount))
            + struct.pack("<b", self.precision)
            + bytes(symbol, "ascii")
        )

    def __str__(self) -> str:
        if self.json_str:
            return json.dumps(
                {
                    "amount": str(self.amount),
                    "precision": self.precision,
                    "nai": self.asset,
                }
            )
        return self.str_repr

    def toJson(self):
        try:
            return json.loads(str(self))
        except Exception:
            return str(self)


class Operation(GPHOperation):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.appbase = kwargs.pop("appbase", False)
        self.prefix = kwargs.pop("prefix", default_prefix)
        super().__init__(*args, **kwargs)

    def _getklass(self, name: str) -> type:
        from . import operations as nectar_ops

        class_ = getattr(nectar_ops, name)
        return class_

    def operations(self) -> dict[str, int]:
        return operations

    def getOperationNameForId(self, i: int) -> str:
        """Convert an operation id into the corresponding string"""
        for key in self.operations():
            if int(self.operations()[key]) == int(i):
                return key
        return "Unknown Operation ID %d" % i

    def json(self) -> dict[str, Any]:
        return json.loads(str(self))
        # return json.loads(str(json.dumps([self.name, self.op.toJson()])))

    def __bytes__(self) -> bytes:
        if self.opId is not None:
            return bytes(Id(self.opId)) + bytes(self.op)
        return bytes(self.op)

    def __str__(self) -> str:
        if self.appbase:
            op_data = self.op.toJson() if isinstance(self.op, GrapheneObject) else str(self.op)
            return json.dumps({"type": self.name.lower() + "_operation", "value": op_data})
        else:
            op_data = self.op.toJson() if isinstance(self.op, GrapheneObject) else str(self.op)
            return json.dumps([self.name.lower(), op_data])


class Memo(GrapheneObject):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            prefix = kwargs.pop("prefix", default_prefix)
            if "encrypted" not in kwargs or not kwargs["encrypted"]:
                super().__init__(None)
            else:
                if len(args) == 1 and len(kwargs) == 0:
                    kwargs = args[0]
                if "encrypted" in kwargs and kwargs["encrypted"]:
                    super().__init__(
                        OrderedDict(
                            [
                                ("from", PublicKey(kwargs["from"], prefix=prefix)),
                                ("to", PublicKey(kwargs["to"], prefix=prefix)),
                                ("nonce", Uint64(int(kwargs["nonce"]))),
                                ("check", Uint32(int(kwargs["check"]))),
                                ("encrypted", Bytes(kwargs["encrypted"])),
                            ]
                        )
                    )


class WitnessProps(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]
            prefix = kwargs.get("prefix", default_prefix)
            json_str = kwargs.get("json_str", False)
            if "sbd_interest_rate" in kwargs:
                super().__init__(
                    OrderedDict(
                        [
                            (
                                "account_creation_fee",
                                Amount(
                                    kwargs["account_creation_fee"],
                                    prefix=prefix,
                                    json_str=json_str,
                                ),
                            ),
                            (
                                "maximum_block_size",
                                Uint32(kwargs["maximum_block_size"]),
                            ),
                            ("sbd_interest_rate", Uint16(kwargs["sbd_interest_rate"])),
                        ]
                    )
                )
            elif "hbd_interest_rate" in kwargs:
                super().__init__(
                    OrderedDict(
                        [
                            (
                                "account_creation_fee",
                                Amount(
                                    kwargs["account_creation_fee"],
                                    prefix=prefix,
                                    json_str=json_str,
                                ),
                            ),
                            (
                                "maximum_block_size",
                                Uint32(kwargs["maximum_block_size"]),
                            ),
                            ("hbd_interest_rate", Uint16(kwargs["hbd_interest_rate"])),
                        ]
                    )
                )
            else:
                super().__init__(
                    OrderedDict(
                        [
                            (
                                "account_creation_fee",
                                Amount(
                                    kwargs["account_creation_fee"],
                                    prefix=prefix,
                                    json_str=json_str,
                                ),
                            ),
                            (
                                "maximum_block_size",
                                Uint32(kwargs["maximum_block_size"]),
                            ),
                        ]
                    )
                )


class Price(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]
            prefix = kwargs.get("prefix", default_prefix)
            super().__init__(
                OrderedDict(
                    [
                        ("base", Amount(kwargs["base"], prefix=prefix)),
                        ("quote", Amount(kwargs["quote"], prefix=prefix)),
                    ]
                )
            )


class Permission(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            prefix = kwargs.pop("prefix", default_prefix)

            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]

            # Sort keys (FIXME: ideally, the sorting is part of Public
            # Key and not located here)
            kwargs["key_auths"] = sorted(
                kwargs["key_auths"],
                key=lambda x: repr(PublicKey(x[0], prefix=prefix)),
                reverse=False,
            )
            kwargs["account_auths"] = sorted(
                kwargs["account_auths"],
                key=lambda x: x[0],
                reverse=False,
            )
            accountAuths = Map([(String(e[0]), Uint16(e[1])) for e in kwargs["account_auths"]])
            keyAuths = Map(
                [(PublicKey(e[0], prefix=prefix), Uint16(e[1])) for e in kwargs["key_auths"]]
            )
            super().__init__(
                OrderedDict(
                    [
                        ("weight_threshold", Uint32(int(kwargs["weight_threshold"]))),
                        ("account_auths", accountAuths),
                        ("key_auths", keyAuths),
                    ]
                )
            )


class Extension(Array):
    def __str__(self):
        """We overload the __str__ function because the json
        representation is different for extensions
        """
        return json.dumps(self.data if hasattr(self, "data") else [])


class ExchangeRate(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]

            prefix = kwargs.get("prefix", default_prefix)
            json_str = kwargs.get("json_str", False)
            super().__init__(
                OrderedDict(
                    [
                        (
                            "base",
                            Amount(kwargs["base"], prefix=prefix, json_str=json_str),
                        ),
                        (
                            "quote",
                            Amount(kwargs["quote"], prefix=prefix, json_str=json_str),
                        ),
                    ]
                )
            )


class Beneficiary(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("weight", Int16(kwargs["weight"])),
                ]
            )
        )


class Beneficiaries(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]

        super().__init__(
            OrderedDict(
                [
                    (
                        "beneficiaries",
                        Array([Beneficiary(o) for o in kwargs["beneficiaries"]]),
                    ),
                ]
            )
        )


class CommentOptionExtensions(Static_variant):
    """Serialize Comment Payout Beneficiaries.

    :param list beneficiaries: A static_variant containing beneficiaries.

    Example::

        [0,
            {'beneficiaries': [
                {'account': 'furion', 'weight': 10000}
            ]}
        ]

    """

    def __init__(self, o):
        if isinstance(o, dict) and "type" in o and "value" in o:
            if o["type"] == "comment_payout_beneficiaries":
                type_id = 0
            else:
                type_id = ~0
            data = o["value"]
        else:
            type_id, data = o
        if type_id == 0:
            data = Beneficiaries(data)
        else:
            raise Exception("Unknown CommentOptionExtension")
        super().__init__(data, type_id)

    def __str__(self):
        if self.type_id == 0:
            return json.dumps({"type": "comment_payout_beneficiaries", "value": self.data.json()})
        return super().__str__()


class UpdateProposalEndDate(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]

            super().__init__(
                OrderedDict(
                    [
                        ("end_date", PointInTime(kwargs["end_date"])),
                    ]
                )
            )


class UpdateProposalExtensions(Static_variant):
    """Serialize Update proposal extensions.

    :param end_date: A static_variant containing the new end_date.

    Example::

        {
            'type': '1',
            'value':
                  {
                    'end_date': '2021-04-05T13:39:48'
                  }
        }

    """

    def __init__(self, o):
        if isinstance(o, dict) and "type" in o and "value" in o:
            if o["type"] == "update_proposal_end_date":
                type_id = 1
            else:
                type_id = ~0
            data = o["value"]
        else:
            type_id, data = o

        if type_id == 1:
            data = UpdateProposalEndDate(data)
        else:
            raise Exception("Unknown UpdateProposalExtension")
        super().__init__(data, type_id, False)

    def __str__(self):
        if self.type_id == 1:
            return json.dumps({"type": "update_proposal_end_date", "value": self.data.json()})
        return super().__str__()
