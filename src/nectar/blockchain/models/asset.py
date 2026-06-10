from typing import Any, cast

from nectar.blockchainobject import BlockchainObject
from nectar.exceptions import AssetDoesNotExistsException


class Asset(BlockchainObject):
    """Deals with Assets of the network.

    :param str Asset: Symbol name or object id of an asset
    :param bool lazy: Lazy loading
    :param bool full: Also obtain bitasset-data and dynamic asset dat
    :param Blockchain blockchain_instance: Blockchain instance
    :returns: All data of an asset

    .. note:: This class comes with its own caching function to reduce the
              load on the API server. Instances of this class can be
              refreshed with ``Asset.refresh()``.
    """

    type_id = 3

    def __init__(
        self,
        asset: str | int,
        lazy: bool = False,
        full: bool = False,
        blockchain_instance: Any = None,
        **kwargs,
    ) -> None:
        self.full = full
        super().__init__(
            asset, lazy=lazy, full=full, blockchain_instance=blockchain_instance, **kwargs
        )
        # self.refresh()

    def refresh(self) -> None:
        """Refresh the data from the API server"""
        self.chain_params = self.blockchain.get_network()
        if self.chain_params is None:
            from nectargraphenebase.chains import known_chains

            self.chain_params = known_chains["HIVE"]
        cast(dict[str, Any], self)["asset"] = ""
        found_asset = False

        # Store original identifier before it gets overwritten
        original_identifier = self.identifier
        if hasattr(original_identifier, "symbol"):
            # If identifier is an Asset object, get its symbol
            original_identifier = original_identifier.symbol
        elif hasattr(original_identifier, "identifier"):
            # If identifier has an identifier attribute, get its string representation
            original_identifier = str(original_identifier)
        elif not isinstance(original_identifier, (str, int)):
            # Convert to string if it's not already a string or int
            original_identifier = str(original_identifier)

        for asset in self.chain_params["chain_assets"]:
            if original_identifier in [asset["symbol"], str(asset["asset"]), str(asset["id"])]:
                cast(dict[str, Any], self)["asset"] = asset["asset"]
                cast(dict[str, Any], self)["precision"] = asset["precision"]
                cast(dict[str, Any], self)["id"] = asset["id"]
                cast(dict[str, Any], self)["symbol"] = asset["symbol"]
                found_asset = True
                break
        if not found_asset:
            raise AssetDoesNotExistsException(
                f"{original_identifier} chain_assets:{self.chain_params['chain_assets']}"
            )

    @property
    def symbol(self) -> str:
        return cast(dict[str, Any], self)["symbol"]

    @property
    def asset(self) -> str:
        return cast(dict[str, Any], self)["asset"]

    @property
    def precision(self) -> int:
        return cast(dict[str, Any], self)["precision"]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Asset):
            return (
                cast(dict[str, Any], self)["symbol"] == other["symbol"]
                and cast(dict[str, Any], self)["asset"] == other["asset"]
                and cast(dict[str, Any], self)["precision"] == other["precision"]
            )
        if isinstance(other, dict):
            symbol = other["symbol"] if "symbol" in other else None
            asset = other["asset"] if "asset" in other else None
            precision = other["precision"] if "precision" in other else None
            return (
                cast(dict[str, Any], self)["symbol"] == symbol
                and cast(dict[str, Any], self)["asset"] == asset
                and cast(dict[str, Any], self)["precision"] == precision
            )
        if isinstance(other, (str, int)):
            return cast(dict[str, Any], self)["symbol"] == other
        return False

    def __ne__(self, other: object) -> bool:
        if isinstance(other, Asset):
            return (
                cast(dict[str, Any], self)["symbol"] != other["symbol"]
                or cast(dict[str, Any], self)["asset"] != other["asset"]
                or cast(dict[str, Any], self)["precision"] != other["precision"]
            )
        if isinstance(other, dict):
            symbol = other["symbol"] if "symbol" in other else None
            asset = other["asset"] if "asset" in other else None
            precision = other["precision"] if "precision" in other else None
            return (
                cast(dict[str, Any], self)["symbol"] != symbol
                or cast(dict[str, Any], self)["asset"] != asset
                or cast(dict[str, Any], self)["precision"] != precision
            )
        if isinstance(other, (str, int)):
            return cast(dict[str, Any], self)["symbol"] != other
        return True
