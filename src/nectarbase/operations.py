import json
import re
from binascii import hexlify
from collections import OrderedDict
from typing import Any

from nectargraphenebase.account import PublicKey
from nectargraphenebase.types import (
    Array,
    Bool,
    HexString,
    Int16,
    Map,
    PointInTime,
    String,
    Uint16,
    Uint32,
    Uint64,
)
from nectargraphenebase.types import (
    Optional as GrapheneOptional,
)

from .objects import (
    Amount,
    CommentOptionExtensions,
    ExchangeRate,
    GrapheneObject,
    Memo,
    Operation,
    Permission,
    UpdateProposalExtensions,
    WitnessProps,
    isArgsThisClass,
)

default_prefix = "STM"


def check_for_class(self: Any, args: tuple[Any, ...]) -> bool:
    if isArgsThisClass(self, args):
        self.data = args[0].data
        return True
    else:
        return False


class Transfer(GrapheneObject):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Allow for overwrite of prefix
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "memo" not in kwargs:
            kwargs["memo"] = ""
        if isinstance(kwargs["memo"], dict):
            kwargs["memo"]["prefix"] = prefix
            memo = GrapheneOptional(Memo(**kwargs["memo"]))
        elif isinstance(kwargs["memo"], str):
            memo = String(kwargs["memo"])
        else:
            memo = GrapheneOptional(Memo(kwargs["memo"]))

        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                    ("memo", memo),
                ]
            )
        )


# Added recurring transfer support for HF25
class Recurring_transfer(GrapheneObject):
    def __init__(self, *args, **kwargs):
        # Allow for overwrite of prefix
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "memo" not in kwargs:
            kwargs["memo"] = ""
        if isinstance(kwargs["memo"], dict):
            kwargs["memo"]["prefix"] = prefix
            memo = GrapheneOptional(Memo(**kwargs["memo"]))
        elif isinstance(kwargs["memo"], str):
            memo = String(kwargs["memo"])
        else:
            memo = GrapheneOptional(Memo(kwargs["memo"]))

        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                    ("memo", memo),
                    ("recurrence", Int16(kwargs["recurrence"])),
                    ("executions", Int16(kwargs["executions"])),
                ]
            )
        )


class Vote(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("voter", String(kwargs["voter"])),
                    ("author", String(kwargs["author"])),
                    ("permlink", String(kwargs["permlink"])),
                    ("weight", Int16(kwargs["weight"])),
                ]
            )
        )


class Transfer_to_vesting(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                ]
            )
        )


class Withdraw_vesting(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("vesting_shares", Amount(kwargs["vesting_shares"], prefix=prefix)),
                ]
            )
        )


class Account_witness_vote(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("witness", String(kwargs["witness"])),
                    ("approve", Bool(bool(kwargs["approve"]))),
                ]
            )
        )


class Account_witness_proxy(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("proxy", String(kwargs["proxy"])),
                ]
            )
        )


class Custom(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("required_auths", Array([String(o) for o in kwargs["required_auths"]])),
                    ("id", Uint16(int(kwargs["id"]))),
                    ("data", String(kwargs["data"])),
                ]
            )
        )


class Custom_binary(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("id", Uint16(int(kwargs["id"]))),
                    ("data", String(kwargs["data"])),
                ]
            )
        )


class Op_wrapper(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        super().__init__(
            OrderedDict(
                [
                    ("op", Operation(kwargs["op"], prefix=prefix)),
                ]
            )
        )


class Account_create(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if not len(kwargs["new_account_name"]) <= 16:
            raise AssertionError("Account name must be at most 16 chars long")

        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("fee", Amount(kwargs["fee"], prefix=prefix, json_str=json_str)),
                    ("creator", String(kwargs["creator"])),
                    ("new_account_name", String(kwargs["new_account_name"])),
                    ("owner", Permission(kwargs["owner"], prefix=prefix)),
                    ("active", Permission(kwargs["active"], prefix=prefix)),
                    ("posting", Permission(kwargs["posting"], prefix=prefix)),
                    ("memo_key", PublicKey(kwargs["memo_key"], prefix=prefix)),
                    ("json_metadata", String(meta)),
                ]
            )
        )


class Account_create_with_delegation(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if not len(kwargs["new_account_name"]) <= 16:
            raise AssertionError("Account name must be at most 16 chars long")

        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("fee", Amount(kwargs["fee"], prefix=prefix, json_str=json_str)),
                    ("delegation", Amount(kwargs["delegation"], prefix=prefix, json_str=json_str)),
                    ("creator", String(kwargs["creator"])),
                    ("new_account_name", String(kwargs["new_account_name"])),
                    ("owner", Permission(kwargs["owner"], prefix=prefix)),
                    ("active", Permission(kwargs["active"], prefix=prefix)),
                    ("posting", Permission(kwargs["posting"], prefix=prefix)),
                    ("memo_key", PublicKey(kwargs["memo_key"], prefix=prefix)),
                    ("json_metadata", String(meta)),
                    ("extensions", Array([])),
                ]
            )
        )


class Account_update(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)

        if "owner" in kwargs:
            owner = GrapheneOptional(Permission(kwargs["owner"], prefix=prefix))
        else:
            owner = GrapheneOptional(None)

        if "active" in kwargs:
            active = GrapheneOptional(Permission(kwargs["active"], prefix=prefix))
        else:
            active = GrapheneOptional(None)

        if "posting" in kwargs:
            posting = GrapheneOptional(Permission(kwargs["posting"], prefix=prefix))
        else:
            posting = GrapheneOptional(None)

        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("owner", owner),
                    ("active", active),
                    ("posting", posting),
                    ("memo_key", PublicKey(kwargs["memo_key"], prefix=prefix)),
                    ("json_metadata", String(meta)),
                ]
            )
        )


class Account_update2(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        extensions = Array([])

        if "owner" in kwargs:
            owner = GrapheneOptional(Permission(kwargs["owner"], prefix=prefix))
        else:
            owner = GrapheneOptional(None)

        if "active" in kwargs:
            active = GrapheneOptional(Permission(kwargs["active"], prefix=prefix))
        else:
            active = GrapheneOptional(None)

        if "posting" in kwargs:
            posting = GrapheneOptional(Permission(kwargs["posting"], prefix=prefix))
        else:
            posting = GrapheneOptional(None)

        if "memo_key" in kwargs:
            memo_key = GrapheneOptional(PublicKey(kwargs["memo_key"], prefix=prefix))
        else:
            memo_key = GrapheneOptional(None)

        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]
        posting_meta = ""
        if "posting_json_metadata" in kwargs and kwargs["posting_json_metadata"]:
            if isinstance(kwargs["posting_json_metadata"], dict):
                posting_meta = json.dumps(kwargs["posting_json_metadata"])
            else:
                posting_meta = kwargs["posting_json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("owner", owner),
                    ("active", active),
                    ("posting", posting),
                    ("memo_key", memo_key),
                    ("json_metadata", String(meta)),
                    ("posting_json_metadata", String(posting_meta)),
                    ("extensions", extensions),
                ]
            )
        )


class Create_proposal(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        extensions = Array([])

        super().__init__(
            OrderedDict(
                [
                    ("creator", String(kwargs["creator"])),
                    ("receiver", String(kwargs["receiver"])),
                    ("start_date", PointInTime(kwargs["start_date"])),
                    ("end_date", PointInTime(kwargs["end_date"])),
                    ("daily_pay", Amount(kwargs["daily_pay"], prefix=prefix, json_str=json_str)),
                    ("subject", String(kwargs["subject"])),
                    ("permlink", String(kwargs["permlink"])),
                    ("extensions", extensions),
                ]
            )
        )


class Update_proposal_votes(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        extensions = Array([])
        proposal_ids = []
        for e in kwargs["proposal_ids"]:
            proposal_ids.append(Uint64(e))

        super().__init__(
            OrderedDict(
                [
                    ("voter", String(kwargs["voter"])),
                    ("proposal_ids", Array(proposal_ids)),
                    ("approve", Bool(kwargs["approve"])),
                    ("extensions", extensions),
                ]
            )
        )


class Remove_proposal(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize a Remove_proposal operation.

        Creates the internal OrderedDict for a remove_proposal operation with:
        - proposal_owner: account name (String)
        - proposal_ids: list of Uint64-wrapped proposal IDs
        - extensions: empty Array

        If initialized with a single existing GrapheneObject instance, initialization returns early after copying that instance's data (handled by check_for_class).

        Required kwargs:
        - proposal_owner: str
        - proposal_ids: iterable of integers (each converted to Uint64)
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        extensions = Array([])
        proposal_ids = []
        for e in kwargs["proposal_ids"]:
            proposal_ids.append(Uint64(e))

        super().__init__(
            OrderedDict(
                [
                    ("proposal_owner", String(kwargs["proposal_owner"])),
                    ("proposal_ids", Array(proposal_ids)),
                    ("extensions", extensions),
                ]
            )
        )


class Update_proposal(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize an Update_proposal operation.

        Accepts either an existing Update_proposal instance (handled by check_for_class), a single positional dict, or keyword arguments. Required fields: `proposal_id`, `creator`, `daily_pay`, `subject`, and `permlink`. Optional `end_date` will be converted into an `update_proposal_end_date` extension. The `daily_pay` Amount uses the provided `prefix` kwarg if present, otherwise `default_prefix` is used.

        Accepted kwargs:
        - proposal_id: numeric id of the proposal (converted to Uint64)
        - creator: account name string (converted to String)
        - daily_pay: amount specifier (converted to Amount; honors `prefix`)
        - subject: short subject string (converted to String)
        - permlink: permlink string (converted to String)
        - end_date: optional datetime/string; if provided, added as an extension
        - prefix: optional asset/account prefix for Amount conversion (defaults to module `default_prefix`)

        No return value; constructs the internal OrderedDict representing the operation.
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        extensions = Array([])
        if "end_date" in kwargs and kwargs["end_date"]:
            extension = {
                "type": "update_proposal_end_date",
                "value": {"end_date": kwargs["end_date"]},
            }
            extensions = Array([UpdateProposalExtensions(extension)])

        super().__init__(
            OrderedDict(
                [
                    ("proposal_id", Uint64(kwargs["proposal_id"])),
                    ("creator", String(kwargs["creator"])),
                    (
                        "daily_pay",
                        Amount(kwargs["daily_pay"], prefix=kwargs.get("prefix", default_prefix)),
                    ),
                    ("subject", String(kwargs["subject"])),
                    ("permlink", String(kwargs["permlink"])),
                    ("extensions", extensions),
                ]
            )
        )


class Witness_set_properties(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.pop("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        extensions = Array([])
        props = {}
        for k in kwargs["props"]:
            if "key" == k[0]:
                block_signing_key = PublicKey(k[1], prefix=prefix)
                props["key"] = repr(block_signing_key)
            elif "new_signing_key" == k[0]:
                new_signing_key = PublicKey(k[1], prefix=prefix)
                props["new_signing_key"] = repr(new_signing_key)
        for k in kwargs["props"]:
            if k[0] in ["key", "new_signing_key"]:
                continue
            if isinstance(k[1], str):
                is_hex = re.fullmatch(r"[0-9a-fA-F]+", k[1] or "") is not None
            else:
                is_hex = False
            if isinstance(k[1], int) and k[0] in [
                "account_subsidy_budget",
                "account_subsidy_decay",
                "maximum_block_size",
            ]:
                props[k[0]] = (hexlify(Uint32(k[1]).__bytes__())).decode()
            elif isinstance(k[1], int) and k[0] in ["sbd_interest_rate", "hbd_interest_rate"]:
                props[k[0]] = (hexlify(Uint16(k[1]).__bytes__())).decode()
            elif not isinstance(k[1], str) and k[0] in ["account_creation_fee"]:
                props[k[0]] = (
                    hexlify(Amount(k[1], prefix=prefix, json_str=json_str).__bytes__())
                ).decode()
            elif not is_hex and isinstance(k[1], str) and k[0] in ["account_creation_fee"]:
                props[k[0]] = (
                    hexlify(Amount(k[1], prefix=prefix, json_str=json_str).__bytes__())
                ).decode()
            elif not isinstance(k[1], str) and k[0] in ["sbd_exchange_rate", "hbd_exchange_rate"]:
                if "prefix" not in k[1]:
                    k[1]["prefix"] = prefix
                props[k[0]] = (hexlify(ExchangeRate(k[1]).__bytes__())).decode()
            elif not is_hex and k[0] in ["url"]:
                props[k[0]] = (hexlify(String(k[1]).__bytes__())).decode()
            else:
                props[k[0]] = k[1]
        props_list = []
        for k in props:
            props_list.append([String(k), HexString(props[k])])
        props_list = sorted(
            props_list,
            key=lambda x: str(x[0]),
            reverse=False,
        )
        map_props = Map(props_list)

        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("props", map_props),
                    ("extensions", extensions),
                ]
            )
        )


class Witness_update(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.pop("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "block_signing_key" in kwargs and kwargs["block_signing_key"]:
            block_signing_key = PublicKey(kwargs["block_signing_key"], prefix=prefix)
        else:
            block_signing_key = PublicKey(
                prefix + "1111111111111111111111111111111114T1Anm", prefix=prefix
            )
        if "prefix" not in kwargs["props"]:
            kwargs["props"]["prefix"] = prefix
        if "json_str" not in kwargs["props"]:
            kwargs["props"]["json_str"] = json_str

        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("url", String(kwargs["url"])),
                    ("block_signing_key", block_signing_key),
                    ("props", WitnessProps(kwargs["props"])),
                    ("fee", Amount(kwargs["fee"], prefix=prefix, json_str=json_str)),
                ]
            )
        )


class Comment(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict) or isinstance(
                kwargs["json_metadata"], list
            ):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("parent_author", String(kwargs["parent_author"])),
                    ("parent_permlink", String(kwargs["parent_permlink"])),
                    ("author", String(kwargs["author"])),
                    ("permlink", String(kwargs["permlink"])),
                    ("title", String(kwargs["title"])),
                    ("body", String(kwargs["body"])),
                    ("json_metadata", String(meta)),
                ]
            )
        )


class Custom_json(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        if "json" in kwargs and kwargs["json"]:
            if isinstance(kwargs["json"], dict) or isinstance(kwargs["json"], list):
                js = json.dumps(kwargs["json"], separators=(",", ":"))
            else:
                js = kwargs["json"]

        if len(kwargs["id"]) > 32:
            raise Exception("'id' too long")

        super().__init__(
            OrderedDict(
                [
                    ("required_auths", Array([String(o) for o in kwargs["required_auths"]])),
                    (
                        "required_posting_auths",
                        Array([String(o) for o in kwargs["required_posting_auths"]]),
                    ),
                    ("id", String(kwargs["id"])),
                    ("json", String(js)),
                ]
            )
        )


class Comment_options(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize a Comment_options operation.

        This constructor builds the serialized fields for a comment options operation from provided keyword arguments or a single dict positional argument. It converts and validates inputs into the expected Graphene types and handles extensions.

        Expected kwargs:
        - author (str): post author.
        - permlink (str): post permlink.
        - max_accepted_payout (str|Amount): payout limit; converted to Amount using optional `prefix` and `json_str`.
        - percent_hbd (int|str): required percent value (primary source) stored as Uint16.
        - allow_votes (bool): whether voting is allowed.
        - allow_curation_rewards (bool): whether curation rewards are allowed.
        - beneficiaries (list, optional): if provided, placed into extensions as a beneficiaries extension.
        - extensions (iterable, optional): explicit extensions; each entry is wrapped with CommentOptionExtensions.
        - prefix (str, optional): asset/account prefix used when constructing Amount (defaults to module default_prefix).
        - json_str (bool, optional): if true, construct Amount with json string mode.

        Behavior and side effects:
        - If initialized from an existing GrapheneObject (via check_for_class), initialization returns early after copying.
        - If `beneficiaries` is present and non-empty, it is converted into an extensions entry.
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", True)
        # handle beneficiaries
        if "beneficiaries" in kwargs and kwargs["beneficiaries"]:
            kwargs["extensions"] = [[0, {"beneficiaries": kwargs["beneficiaries"]}]]
        extensions = Array([])
        if "extensions" in kwargs and kwargs["extensions"]:
            extensions = Array([CommentOptionExtensions(o) for o in kwargs["extensions"]])
        percent_value = kwargs.get("percent_hbd")
        if percent_value is None:
            raise ValueError("Comment_options requires 'percent_hbd'")
        super().__init__(
            OrderedDict(
                [
                    ("author", String(kwargs["author"])),
                    ("permlink", String(kwargs["permlink"])),
                    (
                        "max_accepted_payout",
                        Amount(kwargs["max_accepted_payout"], prefix=prefix, json_str=json_str),
                    ),
                    ("percent_hbd", Uint16(int(percent_value))),
                    ("allow_votes", Bool(bool(kwargs["allow_votes"]))),
                    ("allow_curation_rewards", Bool(bool(kwargs["allow_curation_rewards"]))),
                    ("extensions", extensions),
                ]
            )
        )


class Delete_comment(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("author", String(kwargs["author"])),
                    ("permlink", String(kwargs["permlink"])),
                ]
            )
        )


class Feed_publish(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "prefix" not in kwargs["exchange_rate"]:
            kwargs["exchange_rate"]["prefix"] = prefix
        if "json_str" not in kwargs["exchange_rate"]:
            kwargs["exchange_rate"]["json_str"] = json_str
        super().__init__(
            OrderedDict(
                [
                    ("publisher", String(kwargs["publisher"])),
                    ("exchange_rate", ExchangeRate(kwargs["exchange_rate"])),
                ]
            )
        )


class Convert(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("requestid", Uint32(kwargs["requestid"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                ]
            )
        )


# Operation added for HF25 for the new HBD/Hive conversion operation
class Collateralized_convert(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("requestid", Uint32(kwargs["requestid"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                ]
            )
        )


class Set_withdraw_vesting_route(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("from_account", String(kwargs["from_account"])),
                    ("to_account", String(kwargs["to_account"])),
                    ("percent", Uint16(kwargs["percent"])),
                    ("auto_vest", Bool(kwargs["auto_vest"])),
                ]
            )
        )


class Limit_order_cancel(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("orderid", Uint32(kwargs["orderid"])),
                ]
            )
        )


class Claim_account(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        super().__init__(
            OrderedDict(
                [
                    ("creator", String(kwargs["creator"])),
                    ("fee", Amount(kwargs["fee"], prefix=prefix, json_str=json_str)),
                    ("extensions", Array([])),
                ]
            )
        )


class Create_claimed_account(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)

        if not len(kwargs["new_account_name"]) <= 16:
            raise AssertionError("Account name must be at most 16 chars long")

        meta = ""
        if "json_metadata" in kwargs and kwargs["json_metadata"]:
            if isinstance(kwargs["json_metadata"], dict):
                meta = json.dumps(kwargs["json_metadata"])
            else:
                meta = kwargs["json_metadata"]

        super().__init__(
            OrderedDict(
                [
                    ("creator", String(kwargs["creator"])),
                    ("new_account_name", String(kwargs["new_account_name"])),
                    ("owner", Permission(kwargs["owner"], prefix=prefix)),
                    ("active", Permission(kwargs["active"], prefix=prefix)),
                    ("posting", Permission(kwargs["posting"], prefix=prefix)),
                    ("memo_key", PublicKey(kwargs["memo_key"], prefix=prefix)),
                    ("json_metadata", String(meta)),
                    ("extensions", Array([])),
                ]
            )
        )


class Delegate_vesting_shares(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        super().__init__(
            OrderedDict(
                [
                    ("delegator", String(kwargs["delegator"])),
                    ("delegatee", String(kwargs["delegatee"])),
                    ("vesting_shares", Amount(kwargs["vesting_shares"], prefix=prefix)),
                ]
            )
        )


class Limit_order_create(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("orderid", Uint32(kwargs["orderid"])),
                    (
                        "amount_to_sell",
                        Amount(kwargs["amount_to_sell"], prefix=prefix, json_str=json_str),
                    ),
                    (
                        "min_to_receive",
                        Amount(kwargs["min_to_receive"], prefix=prefix, json_str=json_str),
                    ),
                    ("fill_or_kill", Bool(kwargs["fill_or_kill"])),
                    ("expiration", PointInTime(kwargs["expiration"])),
                ]
            )
        )


class Limit_order_create2(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "prefix" not in kwargs["exchange_rate"]:
            kwargs["exchange_rate"]["prefix"] = prefix
        super().__init__(
            OrderedDict(
                [
                    ("owner", String(kwargs["owner"])),
                    ("orderid", Uint32(kwargs["orderid"])),
                    (
                        "amount_to_sell",
                        Amount(kwargs["amount_to_sell"], prefix=prefix, json_str=json_str),
                    ),
                    ("fill_or_kill", Bool(kwargs["fill_or_kill"])),
                    ("exchange_rate", ExchangeRate(kwargs["exchange_rate"])),
                    ("expiration", PointInTime(kwargs["expiration"])),
                ]
            )
        )


class Change_recovery_account(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("account_to_recover", String(kwargs["account_to_recover"])),
                    ("new_recovery_account", String(kwargs["new_recovery_account"])),
                    ("extensions", Array([])),
                ]
            )
        )


class Transfer_from_savings(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "memo" not in kwargs:
            kwargs["memo"] = ""
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("request_id", Uint32(kwargs["request_id"])),
                    ("to", String(kwargs["to"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                    ("memo", String(kwargs["memo"])),
                ]
            )
        )


class Cancel_transfer_from_savings(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("request_id", Uint32(kwargs["request_id"])),
                ]
            )
        )


class Claim_reward_balance(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize a Claim_reward_balance operation.

        Constructs the serialized fields for claiming reward balances. Requires
        account, reward_hive, reward_hbd, and reward_vests in the canonical order.
        All reward fields are required asset strings - use "0.000 HIVE" or "0.000 HBD"
        when nothing to claim for that asset.

        Behavior:
        - Always serializes ("account", "reward_hive", "reward_hbd", "reward_vests")
        - Converts provided values to Amount objects, respecting prefix/json_str behavior
        - Uses zero-asset strings ("0.000 HIVE"/"0.000 HBD") for any missing reward fields

        Recognized kwargs:
        - account (str): account name claiming rewards.
        - reward_hive (str|Amount): HIVE amount to claim (required, use "0.000 HIVE" if none).
        - reward_hbd (str|Amount): HBD amount to claim (required, use "0.000 HBD" if none).
        - reward_vests (str|Amount): VESTS amount to claim.
        - prefix (str): asset prefix to use (defaults to module default_prefix).
        - json_str (bool): if True, pass amounts as JSON-string form to Amount.

        Also supports initialization from an existing instance via the module's check_for_class helper.
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)

        # Ensure all required fields are present, using zero amounts for missing rewards
        account = kwargs["account"]
        reward_hive = kwargs.get("reward_hive", "0.000 HIVE")
        reward_hbd = kwargs.get("reward_hbd", "0.000 HBD")
        reward_vests = kwargs["reward_vests"]

        super().__init__(
            OrderedDict(
                [
                    ("account", String(account)),
                    ("reward_hive", Amount(reward_hive, prefix=prefix, json_str=json_str)),
                    ("reward_hbd", Amount(reward_hbd, prefix=prefix, json_str=json_str)),
                    ("reward_vests", Amount(reward_vests, prefix=prefix, json_str=json_str)),
                ]
            )
        )


class Transfer_to_savings(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "memo" not in kwargs:
            kwargs["memo"] = ""
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("amount", Amount(kwargs["amount"], prefix=prefix, json_str=json_str)),
                    ("memo", String(kwargs["memo"])),
                ]
            )
        )


class Request_account_recovery(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        new_owner = Permission(kwargs["new_owner_authority"], prefix=prefix)
        super().__init__(
            OrderedDict(
                [
                    ("recovery_account", String(kwargs["recovery_account"])),
                    ("account_to_recover", String(kwargs["account_to_recover"])),
                    ("new_owner_authority", new_owner),
                    ("extensions", Array([])),
                ]
            )
        )


class Recover_account(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        new_owner = Permission(kwargs["new_owner_authority"], prefix=prefix)
        recent_owner = Permission(kwargs["recent_owner_authority"], prefix=prefix)
        super().__init__(
            OrderedDict(
                [
                    ("account_to_recover", String(kwargs["account_to_recover"])),
                    ("new_owner_authority", new_owner),
                    ("recent_owner_authority", recent_owner),
                    ("extensions", Array([])),
                ]
            )
        )


class Escrow_transfer(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize an Escrow_transfer operation object.

        If constructed from an existing GrapheneObject instance (detected via check_for_class), the initializer returns early after copying data.

        Accepts either a single dict positional argument or keyword arguments. Expected fields:
        - from, to, agent (str): account names involved.
        - escrow_id (int): escrow identifier.
        - hbd_amount, hive_amount, fee: amounts; when both `hbd_amount` and `hive_amount` are provided, amounts are wrapped with the `json_str` option; otherwise amounts are wrapped without `json_str`.
        - ratification_deadline, escrow_expiration: datetime-like values for deadlines.
        - json_meta: optional metadata — if a dict or list it will be JSON-serialized; otherwise used as-is.
        Optional kwargs:
        - prefix (str): asset prefix (default "STM").
        - json_str (bool): whether to force JSON string representation for Amount fields when the branch requires it.

        No return value; constructs and initializes the underlying ordered field mapping for the operation.
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        meta = ""
        if "json_meta" in kwargs and kwargs["json_meta"]:
            if isinstance(kwargs["json_meta"], dict) or isinstance(kwargs["json_meta"], list):
                meta = json.dumps(kwargs["json_meta"])
            else:
                meta = kwargs["json_meta"]
        if "hbd_amount" in kwargs and "hive_amount" in kwargs:
            super().__init__(
                OrderedDict(
                    [
                        ("from", String(kwargs["from"])),
                        ("to", String(kwargs["to"])),
                        ("agent", String(kwargs["agent"])),
                        ("escrow_id", Uint32(kwargs["escrow_id"])),
                        (
                            "hbd_amount",
                            Amount(kwargs["hbd_amount"], prefix=prefix, json_str=json_str),
                        ),
                        (
                            "hive_amount",
                            Amount(kwargs["hive_amount"], prefix=prefix, json_str=json_str),
                        ),
                        ("fee", Amount(kwargs["fee"], prefix=prefix, json_str=json_str)),
                        ("ratification_deadline", PointInTime(kwargs["ratification_deadline"])),
                        ("escrow_expiration", PointInTime(kwargs["escrow_expiration"])),
                        ("json_meta", String(meta)),
                    ]
                )
            )
        else:
            super().__init__(
                OrderedDict(
                    [
                        ("from", String(kwargs["from"])),
                        ("to", String(kwargs["to"])),
                        ("agent", String(kwargs["agent"])),
                        ("escrow_id", Uint32(kwargs["escrow_id"])),
                        ("hbd_amount", Amount(kwargs["hbd_amount"], prefix=prefix)),
                        ("hive_amount", Amount(kwargs["hive_amount"], prefix=prefix)),
                        ("fee", Amount(kwargs["fee"], prefix=prefix)),
                        ("ratification_deadline", PointInTime(kwargs["ratification_deadline"])),
                        ("escrow_expiration", PointInTime(kwargs["escrow_expiration"])),
                        ("json_meta", String(meta)),
                    ]
                )
            )


class Escrow_dispute(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("who", String(kwargs["who"])),
                    ("escrow_id", Uint32(kwargs["escrow_id"])),
                ]
            )
        )


class Escrow_release(GrapheneObject):
    def __init__(self, *args, **kwargs):
        """
        Initialize an Escrow_release operation.

        Constructs the operation fields required to release escrowed funds: from, to, who, escrow_id, hbd_amount, and hive_amount. Accepts either a single dict positional argument or keyword arguments. If initialized from an existing GrapheneObject instance (detected by check_for_class), initialization returns early after cloning.

        Key kwargs:
        - from, to, who (str): account names involved in the escrow release.
        - escrow_id (int): escrow identifier.
        - hbd_amount, hive_amount (str|Amount): amounts to release; wrapped as Amount objects using the provided prefix.
        - prefix (str, optional): asset/account prefix passed to Amount (defaults to default_prefix).
        - json_str (bool, optional): when True and both amount keys are present, amounts are wrapped with json_str enabled.

        Raises:
        - KeyError if any required field is missing.
        """
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        prefix = kwargs.get("prefix", default_prefix)
        json_str = kwargs.get("json_str", False)
        if "hive_amount" in kwargs and "hbd_amount" in kwargs:
            super().__init__(
                OrderedDict(
                    [
                        ("from", String(kwargs["from"])),
                        ("to", String(kwargs["to"])),
                        ("who", String(kwargs["who"])),
                        ("escrow_id", Uint32(kwargs["escrow_id"])),
                        (
                            "hbd_amount",
                            Amount(kwargs["hbd_amount"], prefix=prefix, json_str=json_str),
                        ),
                        (
                            "hive_amount",
                            Amount(kwargs["hive_amount"], prefix=prefix, json_str=json_str),
                        ),
                    ]
                )
            )
        else:
            super().__init__(
                OrderedDict(
                    [
                        ("from", String(kwargs["from"])),
                        ("to", String(kwargs["to"])),
                        ("who", String(kwargs["who"])),
                        ("escrow_id", Uint32(kwargs["escrow_id"])),
                        ("hbd_amount", Amount(kwargs["hbd_amount"], prefix=prefix)),
                        ("hive_amount", Amount(kwargs["hive_amount"], prefix=prefix)),
                    ]
                )
            )


class Escrow_approve(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("from", String(kwargs["from"])),
                    ("to", String(kwargs["to"])),
                    ("agent", String(kwargs["agent"])),
                    ("who", String(kwargs["who"])),
                    ("escrow_id", Uint32(kwargs["escrow_id"])),
                    ("approve", Bool(kwargs["approve"])),
                ]
            )
        )


class Decline_voting_rights(GrapheneObject):
    def __init__(self, *args, **kwargs):
        if check_for_class(self, args):
            return
        if len(args) == 1 and len(kwargs) == 0:
            kwargs = args[0]
        super().__init__(
            OrderedDict(
                [
                    ("account", String(kwargs["account"])),
                    ("decline", Bool(kwargs["decline"])),
                ]
            )
        )
