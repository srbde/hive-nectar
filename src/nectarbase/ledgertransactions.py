import logging
from collections.abc import Mapping
from typing import Any

from nectargraphenebase.account import PublicKey
from nectargraphenebase.chains import known_chains
from nectargraphenebase.types import (
    Array,
    Signature,
)
from nectargraphenebase.unsignedtransactions import (
    Unsigned_Transaction as GrapheneUnsigned_Transaction,
)

from .operations import Operation

log = logging.getLogger(__name__)


class Ledger_Transaction(GrapheneUnsigned_Transaction):
    """Create an unsigned transaction and offer method to send it to a ledger device for signing

    :param num ref_block_num:
    :param num ref_block_prefix:
    :param str expiration: expiration date
    :param array operations:  array of operations
    :param dict custom_chains: custom chain which should be added to the known chains
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.known_chains = known_chains
        custom_chain = kwargs.get("custom_chains", {})
        if len(custom_chain) > 0:
            for c in custom_chain:
                if c not in self.known_chains:
                    self.known_chains[c] = custom_chain[c]
        super().__init__(*args, **kwargs)

    def add_custom_chains(self, custom_chain: Mapping[str, Any]) -> None:
        if len(custom_chain) > 0:
            for c in custom_chain:
                if c not in self.known_chains:
                    self.known_chains[c] = custom_chain[c]

    def getOperationKlass(self) -> type[Operation]:
        return Operation

    def getKnownChains(self) -> dict[str, Any]:
        """
        Return the mapping of known blockchain chains available to this transaction.

        Returns:
            dict: A mapping where keys are chain identifiers (e.g., "HIVE", "STEEM" or custom names)
            and values are the chain metadata/configuration that was registered with this transaction.
        """
        return self.known_chains

    def sign(self, path: str = "48'/13'/0'/0'/0'", chain: str = "HIVE") -> "Ledger_Transaction":
        """
        Sign the transaction using a Ledger device and attach the resulting signature to this transaction.

        Builds APDUs for the given BIP32 path and blockchain chain identifier, sends them to a connected Ledger dongle, collects the final signature returned by the device, and stores it as the transaction's "signatures" entry.

        Parameters:
            path (str): BIP32 derivation path to use on the Ledger (default "48'/13'/0'/0'/0'").
            chain (str): Chain identifier used when building APDUs (e.g., "HIVE" or "STEEM").

        Returns:
            Ledger_Transaction: self with `self.data["signatures"]` set to an Array containing the Ledger-produced Signature.

        Notes:
            - This method opens a connection to the Ledger device and closes it before returning.
            - Any exceptions raised by the Ledger communication layer are not handled here and will propagate to the caller.
        """
        from ledgerblue.comm import getDongle  # type: ignore[import-not-found]

        dongle = getDongle(True)
        try:
            apdu_list = self.build_apdu(path, chain)
            for apdu in apdu_list:
                result = dongle.exchange(bytes(apdu))
            sigs = []
            signature = result
            sigs.append(Signature(signature))
            self.data["signatures"] = Array(sigs)
            return self
        finally:
            dongle.close()

    def get_pubkey(
        self,
        path: str = "48'/13'/0'/0'/0'",
        request_screen_approval: bool = False,
        prefix: str = "STM",
    ) -> PublicKey:
        from ledgerblue.comm import getDongle  # type: ignore[import-not-found]

        dongle = getDongle(True)
        try:
            apdu = self.build_apdu_pubkey(path, request_screen_approval)
            result = dongle.exchange(bytes(apdu))
            offset = 1 + result[0]
            address = result[offset + 1 : offset + 1 + result[offset]]
            # public_key = result[1: 1 + result[0]]
            return PublicKey(address.decode(), prefix=prefix)
        finally:
            dongle.close()
