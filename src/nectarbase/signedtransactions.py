import logging
from collections.abc import Mapping
from typing import Any

from nectargraphenebase.chains import known_chains
from nectargraphenebase.signedtransactions import Signed_Transaction as GrapheneSigned_Transaction

from .operations import Operation

log = logging.getLogger(__name__)


class Signed_Transaction(GrapheneSigned_Transaction):
    """Create a signed transaction and offer method to create the
    signature

    :param num refNum: parameter ref_block_num (see :func:`nectarbase.transactions.getBlockParams`)
    :param num refPrefix: parameter ref_block_prefix (see :func:`nectarbase.transactions.getBlockParams`)
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
        """
        Add entries from custom_chain into this transaction's known chains without overwriting existing entries.

        Accepts a mapping of chain identifiers to chain configuration values and merges any keys not already present into self.known_chains. Existing known chains are left unchanged.
        Parameters:
            custom_chain (Mapping): Mapping of chain name -> chain data (e.g., RPC URL or chain parameters); keys present in self.known_chains are not replaced.
        """
        if len(custom_chain) > 0:
            for c in custom_chain:
                if c not in self.known_chains:
                    self.known_chains[c] = custom_chain[c]

    def sign(
        self, wifkeys: str | list[str], chain: str | dict[str, Any] | None = None
    ) -> GrapheneSigned_Transaction:
        """
        Sign the transaction using one or more WIF-format private keys.

        wifkeys: Single WIF string or iterable of WIF private key strings used to produce signatures.
        chain: Chain identifier to use for signing (defaults to "HIVE").

        Returns:
            The value returned by the superclass `sign` implementation.
        """
        return super().sign(wifkeys, chain)

    def verify(
        self,
        pubkeys: list[Any] | None = None,
        chain: str | dict[str, Any] | None = None,
        recover_parameter: bool = False,
    ) -> list[Any]:
        """
        Verify this transaction's signatures.

        Parameters:
            pubkeys (list[str] | None): Public keys to verify against. If None, an empty list is used (all signatures will be checked
                without restricting expected pubkeys).
            chain (str): Chain identifier to use for verification (defaults to "HIVE").
            recover_parameter (bool): If True, return signature recovery parameters alongside verification results.

        Returns:
            Any: The result returned by the superclass verify method (verification outcome as defined by the base implementation).
        """
        return super().verify(pubkeys, chain, recover_parameter)

    def getOperationKlass(self) -> type[Operation]:
        """
        Return the Operation class used to construct operations for this transaction.

        Returns:
            type: The Operation class used by this Signed_Transaction.
        """
        return Operation

    def getKnownChains(self) -> dict[str, Any]:
        return self.known_chains
