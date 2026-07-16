import logging
import math
from datetime import date, datetime, timezone
from typing import Any

from nectar.blockchaininstance import BlockChainInstance
from nectar.constants import HIVE_100_PERCENT
from nectar.price import Price
from nectargraphenebase.chains import known_chains

from .amount import Amount
from .utils import formatToTimeStamp

log = logging.getLogger(__name__)


class Hive(BlockChainInstance):
    """Connect to the Hive network.

    :param str node: Node to connect to *(optional)*
    :param str rpcuser: RPC user *(optional)*
    :param str rpcpassword: RPC password *(optional)*
    :param bool nobroadcast: Do **not** broadcast a transaction!
        *(optional)*
    :param bool unsigned: Do **not** sign a transaction! *(optional)*
    :param bool debug: Enable Debugging *(optional)*
    :param keys: Predefine the wif keys to shortcut the
        wallet database *(optional)*
    :type keys: array, dict, string
    :param wif: Predefine the wif keys to shortcut the
            wallet database *(optional)*
    :type wif: array, dict, string
    :param bool offline: Boolean to prevent connecting to network (defaults
        to ``False``) *(optional)*
    :param int expiration: Delay in seconds until transactions are supposed
        to expire *(optional)* (default is 300)
    :param str blocking: Wait for broadcasted transactions to be included
        in a block and return full transaction (can be "head" or
        "irreversible")
    :param bool bundle: Do not broadcast transactions right away, but allow
        to bundle operations. It is not possible to send out more than one
        vote operation and more than one comment operation in a single broadcast *(optional)*
    :param dict custom_chains: custom chain which should be added to the known chains

    Three wallet operation modes are possible:

    * **Wallet Database**: Here, the nectarlibs load the keys from the
      locally stored wallet SQLite database (see ``storage.py``).
      To use this mode, simply call ``Hive()`` without the
      ``keys`` parameter
    * **Providing Keys**: Here, you can provide the keys for
      your accounts manually. All you need to do is add the wif
      keys for the accounts you want to use as a simple array
      using the ``keys`` parameter to ``Hive()``.
    * **Force keys**: This more is for advanced users and
      requires that you know what you are doing. Here, the
      ``keys`` parameter is a dictionary that overwrite the
      ``active``, ``owner``, ``posting`` or ``memo`` keys for
      any account. This mode is only used for *foreign*
      signatures!

    If no node is provided, it will connect to default nodes from
    nectar.NodeList. Default settings can be changed with:

    .. code-block:: python

        hive = Hive(<host>)

    where ``<host>`` starts with ``https://``, ``ws://`` or ``wss://``.

    The purpose of this class it to simplify interaction with
    Hive.

    The idea is to have a class that allows to do this:

    .. code-block:: python

        >>> from nectar import Hive
        >>> hive = Hive()
        >>> print(hive.get_blockchain_version())  # doctest: +SKIP

    This class also deals with edits, votes and reading content.

    Example for adding a custom chain:

    .. code-block:: python

        from nectar import Hive
        hv = Hive(node=["https://mytstnet.com"], custom_chains={"MYTESTNET":
            {'chain_assets': [{'asset': 'HBD', 'id': 0, 'precision': 3, 'symbol': 'HBD'},
                              {'asset': 'HIVE', 'id': 1, 'precision': 3, 'symbol': 'HIVE'},
                              {'asset': 'VESTS', 'id': 2, 'precision': 6, 'symbol': 'VESTS'}],
             'chain_id': '79276aea5d4877d9a25892eaa01b0adf019d3e5cb12a97478df3298ccdd01674',
             'min_version': '0.0.0',
             'prefix': 'MTN'}
            }
        )

    """

    def get_network(
        self, use_stored_data: bool = True, config: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Identify the network

        :param bool use_stored_data: if True, stored data will be returned. If stored data are
                                     empty or old, refresh_data() is used.

        :returns: Network parameters
        :rtype: dictionary
        """
        if use_stored_data:
            self.refresh_data("config")
            return self.data["network"]

        if self.rpc is None:
            return known_chains["HIVE"]
        try:
            return self.rpc.get_network(props=config)
        except Exception:
            return known_chains["HIVE"]

    def rshares_to_token_backed_dollar(
        self,
        rshares: int | float,
        not_broadcasted_vote: bool = False,
        use_stored_data: bool = True,
    ) -> float:
        return self.rshares_to_hbd(
            rshares, not_broadcasted_vote=not_broadcasted_vote, use_stored_data=use_stored_data
        )

    def rshares_to_hbd(
        self,
        rshares: int | float,
        not_broadcasted_vote: bool = False,
        use_stored_data: bool = True,
    ) -> float:
        """Calculates the current HBD value of a vote"""
        payout = float(rshares) * self.get_hbd_per_rshares(
            use_stored_data=use_stored_data,
            not_broadcasted_vote_rshares=rshares if not_broadcasted_vote else 0,
        )
        return payout

    def get_hbd_per_rshares(
        self, not_broadcasted_vote_rshares: int | float = 0, use_stored_data: bool = True
    ) -> float:
        """Returns the current rshares to HBD ratio"""
        reward_fund = self.get_reward_funds(use_stored_data=use_stored_data)
        if not reward_fund or not isinstance(reward_fund, dict):
            return 0
        reward_balance = float(Amount(reward_fund["reward_balance"], blockchain_instance=self))
        recent_claims = float(reward_fund["recent_claims"]) + not_broadcasted_vote_rshares
        if recent_claims == 0:
            return 0
        fund_per_share = reward_balance / (recent_claims)
        median_price = self.get_median_price(use_stored_data=use_stored_data)
        # Check if median_price is a valid Price object (not None or raw dict)
        from nectar.price import Price

        if median_price is None or (
            isinstance(median_price, dict) and not isinstance(median_price, Price)
        ):
            return 0
        HBD_price = float(median_price * Amount(1, self.hive_symbol, blockchain_instance=self))
        return fund_per_share * HBD_price

    def get_token_per_mvest(
        self, time_stamp: datetime | int | None = None, use_stored_data: bool = True
    ) -> float:
        return self.get_hive_per_mvest(time_stamp=time_stamp, use_stored_data=use_stored_data)

    def get_hive_per_mvest(
        self, time_stamp: datetime | int | None = None, use_stored_data: bool = True
    ) -> float:
        """Returns the MVEST to HIVE ratio

        :param int time_stamp: (optional) if set, return an estimated
            HIVE per MVEST ratio for the given time stamp. If unset the
            current ratio is returned (default). (can also be a datetime object)
        """
        if self.offline and time_stamp is None:
            time_stamp = datetime.now(timezone.utc)

        if time_stamp is not None:
            if isinstance(time_stamp, (datetime, date)):
                time_stamp = formatToTimeStamp(time_stamp)
            a = 2.1325476281078992e-05
            b = -31099.685481490847
            a2 = 2.9019227739473682e-07
            b2 = 48.41432402074669

            if time_stamp < (b2 - b) / (a - a2):
                return a * time_stamp + b
            else:
                return a2 * time_stamp + b2
        global_properties = self.get_dynamic_global_properties(use_stored_data=use_stored_data)
        if not global_properties or not isinstance(global_properties, dict):
            return 0.0
        return float(
            Amount(global_properties["total_vesting_fund_hive"], blockchain_instance=self)
        ) / (
            float(Amount(global_properties["total_vesting_shares"], blockchain_instance=self)) / 1e6
        )

    def vests_to_hp(
        self,
        vests: Amount | float,
        timestamp: datetime | int | None = None,
        use_stored_data: bool = True,
    ) -> float:
        """Converts vests to HP

        :param amount.Amount vests/float vests: Vests to convert
        :param int timestamp: (Optional) Can be used to calculate
            the conversion rate from the past

        """
        if isinstance(vests, Amount):
            vests = float(vests)
        return float(
            float(vests)
            / 1e6
            * float(self.get_hive_per_mvest(timestamp, use_stored_data=use_stored_data))
        )

    def vests_to_token_power(
        self,
        vests: Amount | float,
        timestamp: datetime | int | None = None,
        use_stored_data: bool = True,
    ) -> float:
        return self.vests_to_hp(vests, timestamp=timestamp, use_stored_data=use_stored_data)

    def hp_to_vests(
        self,
        hp: Amount | float,
        timestamp: datetime | int | None = None,
        use_stored_data: bool = True,
    ) -> float:
        """Converts HP to vests

        :param float hp: Hive power to convert
        :param datetime timestamp: (Optional) Can be used to calculate
            the conversion rate from the past
        """
        return (
            float(hp)
            * 1e6
            / float(self.get_hive_per_mvest(timestamp, use_stored_data=use_stored_data))
        )

    def token_power_to_vests(
        self,
        token_power: Amount | float,
        timestamp: datetime | int | None = None,
        use_stored_data: bool = True,
    ) -> float:
        return self.hp_to_vests(token_power, timestamp=timestamp, use_stored_data=use_stored_data)

    def token_power_to_token_backed_dollar(
        self,
        token_power: Amount | float,
        post_rshares: int = 0,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        not_broadcasted_vote: bool = True,
        use_stored_data: bool = True,
    ) -> float:
        """
        Convert token power (Hive Power) to its token-backed dollar equivalent (HBD).

        Parameters:
            token_power: Hive Power amount (numeric or Amount-like) to convert.
            post_rshares (int): Optional existing rshares on the post to include when estimating payout.
            voting_power (int): Voter's current voting power (use HIVE_100_PERCENT for full power).
            vote_pct (int): Vote weight to apply (use HIVE_100_PERCENT for 100%).
            not_broadcasted_vote (bool): If True, include the vote as not-yet-broadcasted when computing reward pool effects.
            use_stored_data (bool): If True, prefer cached chain data when available.

        Returns:
            The estimated HBD value (token-backed dollar) corresponding to the provided token power.
        """
        return self.hp_to_hbd(
            token_power,
            post_rshares=post_rshares,
            voting_power=voting_power,
            vote_pct=vote_pct,
            not_broadcasted_vote=not_broadcasted_vote,
            use_stored_data=use_stored_data,
        )

    def hp_to_hbd(
        self,
        hp: Amount | float,
        post_rshares: int = 0,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        not_broadcasted_vote: bool = True,
        use_stored_data: bool = True,
    ) -> float:
        """
        Convert Hive Power (HP) to the estimated HBD payout this vote would produce.

        Parameters:
            hp (number): Amount of Hive Power to convert.
            post_rshares (int): Current post rshares to include when computing marginal effect of this vote.
            voting_power (int): Voter's current voting power (100% = 10000).
            vote_pct (int): Vote percentage to apply (100% = 10000).
            not_broadcasted_vote (bool): If True, treat the vote as not yet broadcast — the function will account for the vote reducing the available reward pool when applicable.
            use_stored_data (bool): If True, use cached chain/state data when available.

        Returns:
            HBD value corresponding to the provided HP under the current reward pool and price conditions (same type/format as the library's Amount/HBD results).
        """
        vesting_shares = int(self.hp_to_vests(hp, use_stored_data=use_stored_data))
        return self.vests_to_hbd(
            vesting_shares,
            post_rshares=post_rshares,
            voting_power=voting_power,
            vote_pct=vote_pct,
            not_broadcasted_vote=not_broadcasted_vote,
            use_stored_data=use_stored_data,
        )

    def vests_to_hbd(
        self,
        vests: Amount | float,
        post_rshares: int = 0,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        not_broadcasted_vote: bool = True,
        use_stored_data: bool = True,
    ) -> float:
        """
        Convert vesting shares to their equivalent HBD payout for a single vote.

        Given vesting shares, computes the vote's r-shares (taking into account post r-shares,
        voter power and percentage) and converts that r-shares value to an HBD payout.

        Parameters:
            vests: Vesting shares to use for the vote (number or Amount-like).
            post_rshares (int): Existing r-shares of the post being voted on; affects the r-shares calculation.
            voting_power (int): Voter's current voting power (units where 100% == HIVE_100_PERCENT).
            vote_pct (int): Vote percentage to apply (units where 100% == HIVE_100_PERCENT).
            not_broadcasted_vote (bool): If True, treat this as a not-yet-broadcast vote (it reduces the effective reward pool);
                if False, treat as already-applied (affects conversion math for very large votes).
            use_stored_data (bool): Whether to use cached chain parameters/reward state or query fresh data.

        Returns:
            The estimated HBD value (same type returned by rshares_to_hbd) for the vote.
        """
        vote_rshares = self.vests_to_rshares(
            vests, post_rshares=post_rshares, voting_power=voting_power, vote_pct=vote_pct
        )
        return self.rshares_to_hbd(
            vote_rshares, not_broadcasted_vote=not_broadcasted_vote, use_stored_data=use_stored_data
        )

    def hp_to_rshares(
        self,
        hive_power: Amount | float,
        post_rshares: int = 0,
        voting_power: int = HIVE_100_PERCENT,
        vote_pct: int = HIVE_100_PERCENT,
        use_stored_data: bool = True,
    ) -> float:
        """
        Convert Hive Power (HP) to r-shares used for voting.

        Given a Hive Power amount, computes the equivalent vesting shares and then the r-shares that a vote with the specified voting_power and vote_pct would produce against a post that currently has post_rshares. `voting_power` and `vote_pct` use the chain-normalized scale (100% == HIVE_100_PERCENT).

        Parameters:
            hive_power (number): Hive Power (HP) value to convert.
            post_rshares (int, optional): Current r-shares of the post being voted on; used to adjust the resulting r-shares. Defaults to 0.
            voting_power (int, optional): Voter's current voting power on the HIVE_100_PERCENT scale. Defaults to HIVE_100_PERCENT.
            vote_pct (int, optional): Vote percentage to apply on the HIVE_100_PERCENT scale. Defaults to HIVE_100_PERCENT.
            use_stored_data (bool, optional): Whether to use cached chain data when performing conversions. Defaults to True.

        Returns:
            int: The computed r-shares produced by the specified vote.
        """
        # calculate our account voting shares (from vests)
        vesting_shares = int(self.hp_to_vests(hive_power, use_stored_data=use_stored_data))
        rshares = self.vests_to_rshares(
            vesting_shares,
            post_rshares=post_rshares,
            voting_power=voting_power,
            vote_pct=vote_pct,
            use_stored_data=use_stored_data,
        )
        return rshares

    def hbd_to_rshares(
        self,
        hbd: str | int | Amount,
        not_broadcasted_vote: bool = False,
        use_stored_data: bool = True,
    ) -> float:
        """Obtain the r-shares from HBD

        :param hbd: HBD
        :type hbd: str, int, amount.Amount
        :param bool not_broadcasted_vote: not_broadcasted or already broadcasted vote (True = not_broadcasted vote).
         Only impactful for very high amounts of HBD. Slight modification to the value calculation, as the not_broadcasted
         vote rshares decreases the reward pool.

        """
        if isinstance(hbd, Amount):
            hbd = Amount(hbd, blockchain_instance=self)
        elif isinstance(hbd, str):
            hbd = Amount(hbd, blockchain_instance=self)
        else:
            hbd = Amount(hbd, self.hbd_symbol, blockchain_instance=self)
        if hbd["symbol"] != self.hbd_symbol:
            raise AssertionError("Should input HBD, not any other asset!")

        # If the vote was already broadcasted we can assume the blockchain values to be true
        if not not_broadcasted_vote:
            return int(float(hbd) / self.get_hbd_per_rshares(use_stored_data=use_stored_data))

        # If the vote wasn't broadcasted (yet), we have to calculate the rshares while considering
        # the change our vote is causing to the recent_claims. This is more important for really
        # big votes which have a significant impact on the recent_claims.
        reward_fund = self.get_reward_funds(use_stored_data=use_stored_data)
        median_price = self.get_median_price(use_stored_data=use_stored_data)
        if (
            not reward_fund
            or not isinstance(reward_fund, dict)
            or not median_price
            or (isinstance(median_price, dict) and not isinstance(median_price, Price))
        ):
            return int(float(hbd) / self.get_hbd_per_rshares(use_stored_data=use_stored_data))
        recent_claims = int(reward_fund["recent_claims"])
        reward_balance = Amount(reward_fund["reward_balance"], blockchain_instance=self)
        reward_pool_hbd = median_price * reward_balance
        if hbd > reward_pool_hbd:
            raise ValueError("Provided more HBD than available in the reward pool.")

        # This is the formula we can use to determine the "true" rshares.
        # We get this formula by some math magic using the previous used formulas
        # FundsPerShare = (balance / (claims + newShares)) * Price
        # newShares = amount / FundsPerShare
        # We can now resolve both formulas for FundsPerShare and set the formulas to be equal
        # (balance / (claims + newShares)) * price = amount / newShares
        # Now we resolve for newShares resulting in:
        # newShares = claims * amount / (balance * price - amount)
        rshares = (
            recent_claims
            * float(hbd)
            / ((float(reward_balance) * float(median_price)) - float(hbd))
        )
        return int(rshares)

    def rshares_to_vote_pct(
        self,
        rshares: int | float,
        post_rshares: int = 0,
        hive_power: Amount | float | None = None,
        vests: Amount | float | None = None,
        voting_power: int = HIVE_100_PERCENT,
        use_stored_data: bool = True,
    ) -> float:
        """
        Compute the voting percentage required to achieve a target r-shares value.

        Given a desired r-shares (positive for upvotes, negative for downvotes) and either
        hive_power or vests (exactly one must be provided), return the voting percentage
        where 100% = 10000. The calculation accounts for post-vote r-shares adjustments,
        current dust-threshold behavior (post-hardfork), and the configured voting power.

        Parameters:
            rshares (int | float): Target r-shares value (signed).
            post_rshares (int, optional): R-shares already present on the post (positive
                for existing upvotes, negative for downvotes). Defaults to 0.
            hive_power (float, optional): Hive Power to use for the calculation. Provide
                this or `vests`, not both. If given, it is converted to vesting shares.
            vests (int, optional): Vesting shares (in micro-vests, i.e., vest*1e6). Provide
                this or `hive_power`, not both.
            voting_power (int, optional): Voter's current voting power where 100% = 10000.
                Defaults to HIVE_100_PERCENT.
            use_stored_data (bool, optional): Whether to use cached chain properties when
                available. Defaults to True.

        Returns:
            int: Signed voting percentage required (100% = 10000). The sign matches the
            sign of `rshares`.

        Raises:
            ValueError: If neither or both of `hive_power` and `vests` are provided.
        """
        if hive_power is None and vests is None:
            raise ValueError("Either hive_power or vests has to be set!")
        if hive_power is not None and vests is not None:
            raise ValueError("Either hive_power or vests has to be set. Not both!")
        if hive_power is not None:
            vests_value = self.hp_to_vests(hive_power, use_stored_data=use_stored_data)
            vests = int(vests_value) if vests_value is not None else 0

        # Parse version as tuple for reliable comparison
        version_parts = self.hardfork.split(".")
        try:
            major, minor = (
                int(version_parts[0]),
                int(version_parts[1]) if len(version_parts) > 1 else 0,
            )
        except (ValueError, IndexError):
            major, minor = 1, 20  # Default to current behavior
        if (major, minor) >= (1, 20):
            rshares += math.copysign(
                self.get_dust_threshold(use_stored_data=use_stored_data), rshares
            )

        if post_rshares >= 0 and rshares > 0:
            rshares = math.copysign(
                self._calc_revert_vote_claim(abs(rshares), post_rshares), rshares
            )
        elif post_rshares < 0 and rshares < 0:
            rshares = math.copysign(
                self._calc_revert_vote_claim(abs(rshares), abs(post_rshares)), rshares
            )
        elif post_rshares < 0 and rshares > 0:
            rshares = math.copysign(self._calc_revert_vote_claim(abs(rshares), 0), rshares)
        elif post_rshares > 0 and rshares < 0:
            rshares = math.copysign(
                self._calc_revert_vote_claim(abs(rshares), post_rshares), rshares
            )

        # Invert the chain-accurate power model used above:
        # rshares ≈ sign * (vests*1e6 * used_power / HIVE_100_PERCENT)
        # used_power ≈ abs(rshares) * HIVE_100_PERCENT / (vests*1e6)
        # and used_power ≈ ceil((voting_power * abs(vote_pct) / HIVE_100_PERCENT * 86400) / max_vote_denom)
        if vests == 0 or voting_power == 0:
            return 0
        max_vote_denom = self._max_vote_denom(use_stored_data=use_stored_data)
        vests_value = vests if vests is not None else 0
        used_power_est = (abs(rshares) * HIVE_100_PERCENT) / (vests_value * 1e6)
        # Invert the linear relation (ignoring ceil):
        vote_pct_abs = used_power_est * max_vote_denom * HIVE_100_PERCENT / (86400 * voting_power)
        return round(math.copysign(vote_pct_abs, rshares))

    def hbd_to_vote_pct(
        self,
        hbd: str | int | Amount,
        post_rshares: int = 0,
        hive_power: Amount | float | None = None,
        vests: Amount | float | None = None,
        voting_power: int = HIVE_100_PERCENT,
        not_broadcasted_vote: bool = True,
        use_stored_data: bool = True,
    ) -> float:
        """
        Calculate the voting percentage required to achieve a target HBD payout for a given voting power and stake.

        Given a desired HBD amount, this returns the vote percentage (100% == 10000) that, when applied from the provided Hive Power or vesting shares, would produce approximately that payout. Exactly one of `hive_power` or `vests` must be provided.

        Parameters:
            hbd (str|int|Amount): Desired HBD payout. Accepts an Amount, numeric value, or asset string; will be converted to an Amount in the chain's HBD symbol.
            hive_power (number, optional): Voter's Hive Power. Mutually exclusive with `vests`.
            vests (number, optional): Voter's vesting shares. Mutually exclusive with `hive_power`.
            voting_power (int, optional): Current voting power normalization constant (default HIVE_100_PERCENT).
            not_broadcasted_vote (bool, optional): If True, treat the vote as not yet broadcast; this slightly changes calculations for very large HBD amounts because an unbroadcasted vote reduces the available reward pool.
            post_rshares (int, optional): rshares already present on the post (used when calculating required vote to reach a target).
            use_stored_data (bool, optional): Use cached chain properties when available.

        Returns:
            int: Required vote percentage where 100% == 10000. Values >10000 or < -10000 indicate the requested HBD is too large for a single vote.

        Raises:
            AssertionError: If the provided `hbd` cannot be interpreted as the chain's HBD asset.
        """
        if isinstance(hbd, Amount):
            hbd = Amount(hbd, blockchain_instance=self)
        elif isinstance(hbd, str):
            hbd = Amount(hbd, blockchain_instance=self)
        else:
            hbd = Amount(hbd, self.hbd_symbol, blockchain_instance=self)
        if hbd["symbol"] != self.hbd_symbol:
            raise AssertionError()
        rshares = self.hbd_to_rshares(
            hbd, not_broadcasted_vote=not_broadcasted_vote, use_stored_data=use_stored_data
        )
        return self.rshares_to_vote_pct(
            rshares,
            post_rshares=post_rshares,
            hive_power=hive_power,
            vests=vests,
            voting_power=voting_power,
            use_stored_data=use_stored_data,
        )

    @property
    def chain_params(self) -> dict[str, Any] | None:
        if self.offline or self.rpc is None:
            return known_chains["HIVE"]
        else:
            return self.get_network()

    @property
    def hardfork(self) -> str:
        if self.offline or self.rpc is None:
            versions = known_chains["HIVE"]["min_version"]
        else:
            hf_prop = self.get_hardfork_properties()
            if hf_prop and isinstance(hf_prop, dict) and "current_hardfork_version" in hf_prop:
                versions = hf_prop["current_hardfork_version"]
            else:
                versions = known_chains["HIVE"]["min_version"]
        return versions

    @property
    def is_hive(self) -> bool:
        return True

    @property
    def hbd_symbol(self) -> str:
        params = self.chain_params
        if params and isinstance(params, dict):
            return params.get("backed_token_symbol", "HBD")
        return "HBD"

    @property
    def hive_symbol(self) -> str:
        params = self.chain_params
        if params and isinstance(params, dict):
            return params.get("token_symbol", "HIVE")
        return "HIVE"

    @property
    def vests_symbol(self) -> str:
        """get the current chains symbol for VESTS"""
        return self.vest_token_symbol
