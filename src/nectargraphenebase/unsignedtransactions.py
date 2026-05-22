import hashlib
import json
import logging
from binascii import hexlify, unhexlify
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union

from asn1crypto.core import OctetString
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .bip32 import parse_path
from .chains import known_chains
from .objects import Operation, isArgsThisClass
from .types import (
    Array,
    JsonObj,
    PointInTime,
    Set,
    Signature,
    String,
    Uint16,
    Uint32,
    Varint32,
)
from .types import (
    Optional as GrapheneOptional,
)

log = logging.getLogger(__name__)


class GrapheneObjectASN1:
    """Core abstraction class

    This class is used for any JSON reflected object in Graphene.

    * ``instance.__json__()``: encodes data into json format
    * ``bytes(instance)``: encodes data into wire format
    * ``str(instances)``: dumps json object as string

    """

    def __init__(self, data: Any = None) -> None:
        self.data = data

    def __bytes__(self) -> bytes:
        if self.data is None:
            return b""
        b = b""
        output = b""
        for name, value in list(self.data.items()):
            if name == "operations":
                for operation in value:
                    if isinstance(value, str):
                        b = bytes(operation, "utf-8")
                    else:
                        b = bytes(operation)
                    output += OctetString(b).dump()
            elif name != "signatures":
                if isinstance(value, str):
                    b = bytes(value, "utf-8")
                else:
                    b = bytes(value)
                output += OctetString(b).dump()
        return output

    def __json__(self) -> Dict[str, Any]:
        if self.data is None:
            return {}
        d = {}  # JSON output is *not* ordered
        for name, value in list(self.data.items()):
            if isinstance(value, GrapheneOptional) and value.isempty():
                continue

            if isinstance(value, String):
                d.update({name: str(value)})
            else:
                try:
                    d.update({name: JsonObj(value)})
                except Exception:
                    d.update({name: value.__str__()})
        return d

    def __str__(self) -> str:
        return json.dumps(self.__json__())

    def toJson(self) -> Dict[str, Any]:
        return self.__json__()

    def json(self) -> Dict[str, Any]:
        return self.__json__()


class Unsigned_Transaction(GrapheneObjectASN1):
    """Create an unsigned transaction with ASN1 encoder for using it with ledger

    :param num ref_block_num:
    :param num ref_block_prefix:
    :param str expiration: expiration date
    :param array operations:  array of operations
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if isArgsThisClass(self, args):
            self.data = args[0].data
        else:
            if len(args) == 1 and len(kwargs) == 0:
                kwargs = args[0]
            kwargs.pop("prefix", "STM")
            if "extensions" not in kwargs:
                kwargs["extensions"] = Set([])
            elif not kwargs.get("extensions"):
                kwargs["extensions"] = Set([])
            if "signatures" not in kwargs:
                kwargs["signatures"] = Array([])
            else:
                kwargs["signatures"] = Array(
                    [Signature(unhexlify(a)) for a in kwargs["signatures"]]
                )
            operations_count = 0
            if "operations" in kwargs:
                operations_count = len(kwargs["operations"])
                # opklass = self.getOperationKlass()
                # if all([not isinstance(a, opklass) for a in kwargs["operations"]]):
                #    kwargs['operations'] = Array([opklass(a, ) for a in kwargs["operations"]])
                # else:
                #    kwargs['operations'] = (kwargs["operations"])

            super().__init__(
                OrderedDict(
                    [
                        ("ref_block_num", Uint16(kwargs["ref_block_num"])),
                        ("ref_block_prefix", Uint32(kwargs["ref_block_prefix"])),
                        ("expiration", PointInTime(kwargs["expiration"])),
                        ("operations_count", Varint32(operations_count)),
                        ("operations", kwargs["operations"]),
                        ("extensions", kwargs["extensions"]),
                        ("signatures", kwargs["signatures"]),
                    ]
                )
            )

    @property
    def id(self) -> str:
        """The transaction id of this transaction"""
        # Store signatures temporarily since they are not part of
        # transaction id
        sigs = self.data["signatures"]
        self.data.pop("signatures", None)

        # Generage Hash of the seriliazed version
        h = hashlib.sha256(bytes(self)).digest()

        # recover signatures
        self.data["signatures"] = sigs

        # Return properly truncated tx hash
        return hexlify(h[:20]).decode("ascii")

    def getOperationKlass(self) -> type[Operation]:
        return Operation

    def derSigToHexSig(self, s: Union[str, bytes]) -> str:
        """Format DER to HEX signature"""
        der_bytes = unhexlify(s)
        r, s_val = decode_dss_signature(der_bytes)
        return "{:064x}{:064x}".format(r, s_val)

    def getKnownChains(self) -> Dict[str, Any]:
        return known_chains

    def getChainParams(self, chain: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        # Which network are we on:
        chains = self.getKnownChains()
        if isinstance(chain, str) and chain in chains:
            chain_params = chains[chain]
        elif isinstance(chain, dict):
            chain_params = chain
        else:
            raise Exception("sign() only takes a string or a dict as chain!")
        if "chain_id" not in chain_params:
            raise Exception("sign() needs a 'chain_id' in chain params!")
        return chain_params

    def deriveDigest(self, chain: Union[str, Dict[str, Any]]) -> None:
        chain_params = self.getChainParams(chain)
        # Chain ID
        self.chainid = chain_params["chain_id"]

        # Do not serialize signatures
        sigs = self.data["signatures"]
        self.data["signatures"] = []

        # Get message to sign
        #   bytes(self) will give the wire formated data according to
        #   GrapheneObject and the data given in __init__()
        self.message = OctetString(unhexlify(self.chainid)).dump()
        for name, value in list(self.data.items()):
            if name == "operations":
                for operation in value:
                    if isinstance(value, str):
                        b = bytes(operation, "utf-8")
                    else:
                        b = bytes(operation)
                    self.message += OctetString(b).dump()
            elif name != "signatures":
                if isinstance(value, str):
                    b = bytes(value, "utf-8")
                else:
                    b = bytes(value)
                self.message += OctetString(b).dump()

        self.digest = hashlib.sha256(self.message).digest()

        # restore signatures
        self.data["signatures"] = sigs

    def build_path(self, role: str, account_index: int, key_index: int) -> str:
        if role == "owner":
            return "48'/13'/0'/%d'/%d'" % (account_index, key_index)
        elif role == "active":
            return "48'/13'/1'/%d'/%d'" % (account_index, key_index)
        elif role == "posting":
            return "48'/13'/4'/%d'/%d'" % (account_index, key_index)
        elif role == "memo":
            return "48'/13'/3'/%d'/%d'" % (account_index, key_index)
        else:
            raise ValueError(f"Unknown role: {role}")

    def build_apdu(
        self, path: str = "48'/13'/0'/0'/0'", chain: Optional[Union[str, Dict[str, Any]]] = None
    ) -> List[bytes]:
        if chain is None:
            raise ValueError("chain parameter is required for build_apdu")
        self.deriveDigest(chain)
        parsed_path = parse_path(path, as_bytes=True)
        path_bytes = unhexlify(bytes(parsed_path))

        message = self.message
        path_size = int(len(path_bytes) / 4)
        message_size = len(message)

        offset = 0
        first = True
        result = []
        while offset < message_size:
            chunk = message[offset : offset + 255]
            total_size = len(chunk)
            if first:
                apdu = (
                    unhexlify("d4040000")
                    + bytes([total_size])
                    + bytes([path_size])
                    + path_bytes
                    + chunk
                )
                first = False
            else:
                total_size = len(chunk)
                apdu = unhexlify("d4048000") + bytes([total_size]) + chunk
            result.append(apdu)
            offset += len(chunk)
        return result

    def build_apdu_pubkey(
        self, path: str = "48'/13'/0'/0'/0'", request_screen_approval: bool = False
    ) -> bytes:
        parsed_path = parse_path(path, as_bytes=True)
        path_bytes = unhexlify(bytes(parsed_path))
        if not request_screen_approval:
            return (
                unhexlify("d4020001")
                + bytes([int(len(path_bytes)) + 1])
                + bytes([int(len(path_bytes) / 4)])
                + path_bytes
            )
        else:
            return (
                unhexlify("d4020101")
                + bytes([int(len(path_bytes)) + 1])
                + bytes([int(len(path_bytes) / 4)])
                + path_bytes
            )
