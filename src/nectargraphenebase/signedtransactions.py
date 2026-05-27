import hashlib
import logging
from binascii import hexlify, unhexlify
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .account import PublicKey
from .chains import known_chains
from .ecdsasig import sign_message, verify_message
from .objects import GrapheneObject, Operation, isArgsThisClass
from .types import (
    Array,
    PointInTime,
    Set,
    Signature,
    Uint16,
    Uint32,
)

log = logging.getLogger(__name__)


class Signed_Transaction(GrapheneObject):
    """Create a signed transaction and offer method to create the
    signature

    :param num ref_block_num: reference block number
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
            # Remove prefix from kwargs if present (not used in this context)
            kwargs.pop("prefix", None)
            if "extensions" not in kwargs:
                kwargs["extensions"] = Set([])
            elif not kwargs.get("extensions"):
                kwargs["extensions"] = Set([])
            if "signatures" not in kwargs:
                kwargs["signatures"] = Array([])
            else:
                # Defensive: if a string, wrap in a list and log warning
                sigs = kwargs["signatures"]
                if isinstance(sigs, str):
                    raise TypeError(
                        "signatures parameter must be a list of signature strings, not a string. "
                        f"Did you mean to pass [{sigs!r}]?"
                    )
                kwargs["signatures"] = Array([Signature(unhexlify(a)) for a in sigs])

            if "operations" in kwargs:
                opklass = self.getOperationKlass()
                if all([not isinstance(a, opklass) for a in kwargs["operations"]]):
                    kwargs["operations"] = Array([opklass(a) for a in kwargs["operations"]])
                else:
                    kwargs["operations"] = Array(kwargs["operations"])

            super().__init__(
                OrderedDict(
                    [
                        ("ref_block_num", Uint16(kwargs["ref_block_num"])),
                        ("ref_block_prefix", Uint32(kwargs["ref_block_prefix"])),
                        ("expiration", PointInTime(kwargs["expiration"])),
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
        if isinstance(s, bytes):
            der_bytes = s
        else:
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
        self.message = unhexlify(self.chainid) + bytes(self)
        self.digest = hashlib.sha256(self.message).digest()

        # restore signatures
        self.data["signatures"] = sigs

    def verify(
        self,
        pubkeys: Optional[List[Any]] = None,
        chain: Optional[Union[str, Dict[str, Any]]] = None,
        recover_parameter: bool = False,
    ) -> List[Any]:
        """Returned pubkeys have to be checked if they are existing"""
        if not chain:
            raise ValueError("chain parameter is required")
        chain_params = self.getChainParams(chain)
        self.deriveDigest(chain)
        signatures = self.data["signatures"].data
        pubKeysFound = []

        for signature in signatures:
            p = None
            if recover_parameter:
                try:
                    p = verify_message(self.message, bytes(signature))
                except (ValueError, AssertionError, InvalidSignature):
                    p = None

            if p is None:
                for i in range(4):
                    try:
                        p = verify_message(self.message, bytes(signature), recover_parameter=i)
                        if p is not None:
                            phex = hexlify(p).decode("ascii")
                            pubKeysFound.append(phex)
                    except (
                        ValueError,
                        AssertionError,
                        InvalidSignature,
                    ) as e:
                        log.debug("Signature recovery failed for parameter %d: %s", i, e)
                        p = None
            else:
                phex = hexlify(p).decode("ascii")
                pubKeysFound.append(phex)

        for pubkey in pubkeys or []:
            if not isinstance(pubkey, PublicKey):
                raise Exception("Pubkeys must be array of 'PublicKey'")

            k = pubkey.unCompressed()[2:]
            if k not in pubKeysFound and repr(pubkey) not in pubKeysFound:
                k = PublicKey(PublicKey(k).compressed())
                f = format(k, chain_params["prefix"])
                raise Exception("Signature for %s missing!" % f)
        return pubKeysFound

    def sign(
        self, wifkeys: Union[str, List[str]], chain: Optional[Union[str, Dict[str, Any]]] = None
    ) -> "Signed_Transaction":
        """Sign the transaction with the provided private keys.

        :param array wifkeys: Array of wif keys
        :param str chain: identifier for the chain

        """
        if not chain:
            raise Exception("Chain needs to be provided!")
        self.deriveDigest(chain)

        # Get Unique private keys
        # Preserve order while removing duplicates (Python 3.7+ dicts maintain insertion order)
        self.privkeys = list(dict.fromkeys(wifkeys if isinstance(wifkeys, list) else [wifkeys]))

        # Sign the message with every private key given!
        sigs = []
        for wif in self.privkeys:
            signature = sign_message(self.message, wif)
            sigs.append(Signature(signature))

        self.data["signatures"] = Array(sigs)
        return self
