from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from nectar.amount import Amount
from nectar.blockchain import Blockchain
from nectar.constants import (
    HIVE_100_PERCENT,
    HIVE_VOTE_REGENERATION_SECONDS,
    HIVE_VOTING_MANA_REGENERATION_SECONDS,
)
from nectar.haf import HAF
from nectar.utils import (
    addTzInfo,
    formatTimedelta,
    reputation_to_score,
)

log = logging.getLogger(__name__)


class AccountCalculatorMixin:
    def get_rc(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Return RC of account."""
        return Blockchain(blockchain_instance=self.blockchain).find_rc_accounts(self["name"])

    def get_rc_manabar(self) -> dict[str, int | float | Amount]:
        """
        Return the account's current and maximum Resource Credit (RC) mana.

        Calculates RC mana regeneration since the stored `rc_manabar.last_update_time` and returns
        both raw and computed values.

        Returns:
            dict: {
                "last_mana" (int): stored mana at the last update (raw value from account data),
                "last_update_time" (int): UNIX timestamp (seconds) of the last manabar update,
                "current_mana" (int): estimated current mana after regeneration (capped at max_mana),
                "max_mana" (int): maximum possible mana (from `max_rc`),
                "current_pct" (float): current_mana / max_mana * 100 (0 if max_mana == 0),
                "max_rc_creation_adjustment" (Amount): Amount object representing max RC creation adjustment
            }
        """
        rc_param = self.get_rc()
        if rc_param is None or (isinstance(rc_param, list) and len(rc_param) == 0):
            return {
                "last_mana": 0,
                "last_update_time": 0,
                "current_mana": 0,
                "max_mana": 0,
                "current_pct": 0,
                "max_rc_creation_adjustment": Amount(0, blockchain_instance=self.blockchain),
            }
        if isinstance(rc_param, list):
            rc_param = rc_param[0]
        max_mana = int(rc_param["max_rc"])
        last_mana = int(rc_param["rc_manabar"]["current_mana"])
        last_update_time = rc_param["rc_manabar"]["last_update_time"]
        last_update = datetime.fromtimestamp(last_update_time, tz=timezone.utc)
        diff_in_seconds = (datetime.now(timezone.utc) - last_update).total_seconds()
        current_mana = int(
            last_mana + diff_in_seconds * max_mana / HIVE_VOTING_MANA_REGENERATION_SECONDS
        )
        if current_mana > max_mana:
            current_mana = max_mana
        if max_mana > 0:
            current_pct = current_mana / max_mana * 100
        else:
            current_pct = 0
        max_rc_creation_adjustment = Amount(
            rc_param["max_rc_creation_adjustment"], blockchain_instance=self.blockchain
        )
        return {
            "last_mana": last_mana,
            "last_update_time": last_update_time,
            "current_mana": current_mana,
            "max_mana": max_mana,
            "current_pct": current_pct,
            "max_rc_creation_adjustment": max_rc_creation_adjustment,
        }

    @property
    def rep(self) -> float:
        """Returns the account reputation"""
        return self.get_reputation()

    @property
    def sp(self) -> Amount:
        """
        Return the account's Hive Power (HP).

        This is a compatibility alias that delegates to `get_token_power()` and returns the account's effective Hive Power as computed by that method.
        """
        return self.get_token_power()

    @property
    def tp(self) -> Amount:
        """Returns the account Hive Power"""
        return self.get_token_power()

    @property
    def vp(self) -> float:
        """Returns the account voting power in the range of 0-100%"""
        return self.get_voting_power()

    def get_reputation(self) -> float:
        """
        Return the account's normalized reputation score.

        If the node is offline, returns a default reputation score. When connected, tries the HAF reputation API first
        which returns the final normalized score directly. Falls back to the cached reputation
        field if HAF fails.
        """
        if not self.blockchain.is_connected():
            return reputation_to_score(0)

        # Try HAF API first - returns final normalized score
        haf = HAF(blockchain_instance=self.blockchain)
        rep_data = haf.reputation(self["name"])
        if rep_data is not None:
            # Handle both dict and direct responses
            try:
                if isinstance(rep_data, dict):
                    if "reputation" in rep_data:
                        return float(rep_data["reputation"])
                    # Unknown dict shape; fall through to cached field.
                elif isinstance(rep_data, (int, float)):
                    return float(rep_data)
                else:
                    # Try to convert to float if it's a string-like
                    return float(rep_data)
            except (ValueError, TypeError, KeyError) as e:
                log.warning(f"Failed to parse reputation data from HAF for {self['name']}: {e}")

        # Fallback to cached reputation field (old behavior)
        if "reputation" in self:
            try:
                rep = int(self["reputation"])
                log.debug(f"Using cached reputation for {self['name']}: {rep}")
                return reputation_to_score(rep)
            except (ValueError, TypeError) as e:
                log.warning(f"Invalid cached reputation for {self['name']}: {e}")
                return reputation_to_score(0)
        else:
            log.warning(f"No reputation data available for {self['name']}")
            return reputation_to_score(0)

    def get_manabar(self) -> dict[str, int | float | Amount]:
        """
        Return the account's voting manabar state.

        Calculates current voting mana from the stored voting_manabar using the account's
        effective vesting shares as `max_mana`. If effective vesting shares are zero,
        a fallback is computed from the chain's account creation fee converted to vests.

        Returns:
            dict: Manabar values with the following keys:
                - last_mana (int): Stored `current_mana` at the last update.
                - last_update_time (int): Unix timestamp (seconds) of the last manabar update.
                - current_mana (int): Estimated current mana (capped at `max_mana`).
                - max_mana (int): Maximum mana derived from effective vesting shares.
                - current_mana_pct (float): Current mana as a percentage of `max_mana`.

        Notes:
            - Regeneration uses HIVE_VOTING_MANA_REGENERATION_SECONDS to convert elapsed
              seconds since `last_update_time` into regenerated mana.
        """
        max_mana = self.get_effective_vesting_shares()
        if max_mana == 0:
            props = self.blockchain.get_chain_properties()
            required_fee_token = Amount(
                props["account_creation_fee"], blockchain_instance=self.blockchain
            )
            max_mana = int(self.blockchain.token_power_to_vests(required_fee_token))

        last_mana = int(self["voting_manabar"]["current_mana"])
        last_update_time = self["voting_manabar"]["last_update_time"]
        last_update = datetime.fromtimestamp(last_update_time, tz=timezone.utc)
        diff_in_seconds = (datetime.now(timezone.utc) - last_update).total_seconds()
        current_mana = int(
            last_mana + diff_in_seconds * max_mana / HIVE_VOTING_MANA_REGENERATION_SECONDS
        )
        if current_mana > max_mana:
            current_mana = max_mana
        if max_mana > 0:
            current_mana_pct = float(current_mana) / float(max_mana) * 100
        else:
            current_mana_pct = 0
        return {
            "last_mana": last_mana,
            "last_update_time": last_update_time,
            "current_mana": current_mana,
            "max_mana": max_mana,
            "current_mana_pct": current_mana_pct,
        }

    def get_downvote_manabar(self) -> dict[str, int | float | Amount] | None:
        """
        Return the account's downvote manabar state and regeneration progress.

        If the account has no 'downvote_manabar' field returns None.

        Returns a dict with:
            - last_mana (int): stored mana at last update.
            - last_update_time (int): POSIX timestamp of the last update.
            - current_mana (int): estimated current mana after regeneration (clamped to max_mana).
            - max_mana (int): maximum possible downvote mana (derived from effective vesting shares or account creation fee fallback).
            - current_mana_pct (float): current_mana expressed as a percentage of max_mana (0–100).
        """
        if "downvote_manabar" not in self:
            return None
        max_mana = self.get_effective_vesting_shares() / 4
        if max_mana == 0:
            props = self.blockchain.get_chain_properties()
            required_fee_token = Amount(
                props["account_creation_fee"], blockchain_instance=self.blockchain
            )
            max_mana = int(self.blockchain.token_power_to_vests(required_fee_token) / 4)

        last_mana = int(self["downvote_manabar"]["current_mana"])
        last_update_time = self["downvote_manabar"]["last_update_time"]
        last_update = datetime.fromtimestamp(last_update_time, tz=timezone.utc)
        diff_in_seconds = (datetime.now(timezone.utc) - last_update).total_seconds()
        current_mana = int(
            last_mana + diff_in_seconds * max_mana / HIVE_VOTING_MANA_REGENERATION_SECONDS
        )
        if current_mana > max_mana:
            current_mana = max_mana
        if max_mana > 0:
            current_mana_pct = float(current_mana) / float(max_mana) * 100
        else:
            current_mana_pct = 0
        return {
            "last_mana": last_mana,
            "last_update_time": last_update_time,
            "current_mana": current_mana,
            "max_mana": max_mana,
            "current_mana_pct": current_mana_pct,
        }

    def get_voting_power(self, with_regeneration: bool = True) -> float:
        """
        Return the account's current voting power as a percentage (0–100).

        If the account stores a `voting_manabar`, the result is derived from that manabar and optionally includes regeneration. If the legacy `voting_power` field is present, the method uses that value and, when `with_regeneration` is True, adds the amount regenerated since `last_vote_time`.

        Parameters:
            with_regeneration (bool): If True (default), include regenerated voting power since the last update.

        Returns:
            float: Voting power percentage in the range 0 to 100 (clamped).
        """
        if "voting_manabar" in self:
            manabar = self.get_manabar()
            if with_regeneration:
                total_vp = manabar["current_mana_pct"]
            else:
                if manabar["max_mana"] > 0:
                    total_vp = float(manabar["last_mana"]) / float(manabar["max_mana"]) * 100
                else:
                    total_vp = 0
        elif "voting_power" in self:
            if with_regeneration:
                last_vote_time = self["last_vote_time"]
                diff_in_seconds = (datetime.now(timezone.utc) - (last_vote_time)).total_seconds()
                regenerated_vp = (
                    diff_in_seconds * HIVE_100_PERCENT / HIVE_VOTE_REGENERATION_SECONDS / 100
                )
            else:
                regenerated_vp = 0
            total_vp = self["voting_power"] / 100 + regenerated_vp
        if total_vp > 100:
            return 100.0
        if total_vp < 0:
            return 0.0
        return float(total_vp)

    def get_downvoting_power(self, with_regeneration: bool = True) -> float:
        """Returns the account downvoting power in the range of 0-100%

        :param bool with_regeneration: When True, downvoting power regeneration is
            included into the result (default True)
        """
        if "downvote_manabar" not in self:
            return 0

        manabar = self.get_downvote_manabar()
        if manabar is None:
            return 0.0
        if with_regeneration:
            total_down_vp = manabar["current_mana_pct"]
        else:
            if manabar["max_mana"] > 0:
                total_down_vp = float(manabar["last_mana"]) / float(manabar["max_mana"]) * 100
            else:
                total_down_vp = 0
        if total_down_vp > 100:
            return 100.0
        if total_down_vp < 0:
            return 0.0
        return float(total_down_vp)

    def get_vests(self, only_own_vests: bool = False) -> Amount:
        """Returns the account vests

        :param bool only_own_vests: When True, only owned vests is
            returned without delegation (default False)
        """
        vests = self["vesting_shares"]
        if (
            not only_own_vests
            and "delegated_vesting_shares" in self
            and "received_vesting_shares" in self
        ):
            vests = vests - (self["delegated_vesting_shares"]) + (self["received_vesting_shares"])

        return vests

    def get_effective_vesting_shares(self) -> int:
        """
        Return the account's effective vesting shares as an integer.

        Calculates vesting shares adjusted for active delegations and pending withdrawals:
        - Starts from `vesting_shares`.
        - Subtracts `delegated_vesting_shares` and adds `received_vesting_shares` when present.
        - If a future `next_vesting_withdrawal` exists and withdrawal fields are present,
          subtracts the remaining amount that will be withdrawn (bounded by `vesting_withdraw_rate`).

        Returns:
            int: Effective vesting shares in the same internal units stored on the account.
        """
        vesting_shares = int(self["vesting_shares"])
        if "delegated_vesting_shares" in self and "received_vesting_shares" in self:
            vesting_shares = (
                vesting_shares
                - int(self["delegated_vesting_shares"])
                + int(self["received_vesting_shares"])
            )
        next_withdraw = self["next_vesting_withdrawal"]
        if next_withdraw is None:
            return vesting_shares
        if isinstance(next_withdraw, str):
            next_withdraw_dt = datetime.strptime(next_withdraw, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        elif isinstance(next_withdraw, (datetime, date, time)):
            next_withdraw_dt = addTzInfo(next_withdraw)
            if next_withdraw_dt is None:
                return vesting_shares
            # Ensure we have a datetime object for the subtraction
            if not isinstance(next_withdraw_dt, datetime):
                next_withdraw_dt = datetime.combine(next_withdraw_dt, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
        else:
            return vesting_shares
        timestamp = (next_withdraw_dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
        if (
            timestamp > 0
            and "vesting_withdraw_rate" in self
            and "to_withdraw" in self
            and "withdrawn" in self
        ):
            vesting_shares -= min(
                int(self["vesting_withdraw_rate"]),
                int(self["to_withdraw"]) - int(self["withdrawn"]),
            )
        return vesting_shares

    def get_token_power(self, only_own_vests: bool = False, use_stored_data: bool = True) -> Amount:
        """
        Return the account's Hive Power (HP), including staked tokens and delegated amounts.

        Parameters:
            only_own_vests (bool): If True, only the account's owned vesting shares are considered (delegations excluded).
            use_stored_data (bool): If False, fetch the current vests-to-token-power conversion from the chain; if True, use cached conversion values.

        Returns:
            float: Hive Power (HP) equivalent for the account's vesting shares.
        """
        return self.blockchain.vests_to_token_power(
            self.get_vests(only_own_vests=only_own_vests),
            use_stored_data=use_stored_data,
        )

    def get_voting_value(
        self,
        post_rshares: int = 0,
        voting_weight: int | float = 100,
        voting_power: int | float | None = None,
        token_power: int | float | None = None,
        not_broadcasted_vote: bool = True,
    ) -> Amount:
        """
        Estimate the vote value expressed in HBD for a potential vote by this account.

        Detailed description:
        Computes the HBD value that a vote would produce given post rshares and voting settings. Uses the account's token power (HP) by default and delegates the numeric conversion to the blockchain instance.

        Parameters:
            post_rshares (int): The post's rshares contribution (can be 0 for an upvote-only estimate).
            voting_weight (float|int, optional): The vote weight as a percentage in the range 0–100 (default 100).
            voting_power (float|int, optional): The account's current voting power as a percentage in the range 0–100.
                If omitted, the account's current voting power is used.
            token_power (float|int, optional): Token power (HP) to use for the calculation. If omitted, the account's current HP is used.
            not_broadcasted_vote (bool, optional): If True, treat the vote as not yet broadcast when estimating (affects regeneration logic).

        Returns:
            Amount: Estimated vote value denominated in HBD.
        """
        if voting_power is None:
            voting_power = self.get_voting_power()
        if token_power is None:
            tp = self.get_token_power()
        else:
            tp = token_power
        voteValue = self.blockchain.token_power_to_token_backed_dollar(
            tp,
            post_rshares=post_rshares,
            voting_power=voting_power * 100,
            vote_pct=voting_weight * 100,
            not_broadcasted_vote=not_broadcasted_vote,
        )
        return voteValue

    def get_voting_value_HBD(
        self,
        post_rshares=0,
        voting_weight=100,
        voting_power=None,
        hive_power=None,
        not_broadcasted_vote=True,
    ):
        """
        Return the estimated voting value expressed in HBD for the account.

        This is a thin wrapper around `get_voting_value` that maps `hive_power` to the underlying `token_power` parameter.

        Parameters:
            post_rshares (int): Total rshares for the target post (default 0).
            voting_weight (int): Weight of the vote as a percentage (0-100, default 100).
            voting_power (int | None): Current voting power percentage to use; if None the account's current power is used.
            hive_power (float | None): Token power (Hive Power / HP) to use for the calculation; if None the account's current token power is used.
            not_broadcasted_vote (bool): If True, calculate value as if the vote is not yet broadcast (default True).

        Returns:
            Estimated vote value expressed in HBD.
        """
        return self.get_voting_value(
            post_rshares=post_rshares,
            voting_weight=voting_weight,
            voting_power=voting_power,
            token_power=hive_power,
            not_broadcasted_vote=not_broadcasted_vote,
        )

    def get_vote_pct_for_HBD(
        self,
        hbd,
        post_rshares=0,
        voting_power=None,
        hive_power=None,
        not_broadcasted_vote=True,
    ):
        """
        Return the voting percentage (weight) required for this account to produce a vote worth the given HBD amount.

        Parameters:
            hbd (str | int | Amount): Desired vote value in HBD (can be numeric, string, or an Amount).
            post_rshares (int): Current rshares of the post; used in the vote value calculation. Defaults to 0.
            voting_power (int | None): Current voting power to use (in internal units). If None, the account's current voting power is used.
            hive_power (Amount | None): Token power (HP) to use for the calculation. If None, the account's current HP is used.
            not_broadcasted_vote (bool): If True, accounts for a non-broadcasted (simulated) vote when estimating required percentage.

        Returns:
            int: Vote weight as an integer in the range -10000..10000 (where 10000 == 100%). Values outside that range indicate the requested HBD value is unattainable with this account (e.g., greater than 10000 or less than -10000).
        """
        return self.get_vote_pct_for_vote_value(
            hbd,
            post_rshares=post_rshares,
            voting_power=voting_power,
            token_power=hive_power,
            not_broadcasted_vote=not_broadcasted_vote,
        )

    def get_vote_pct_for_vote_value(
        self,
        token_units: int | float | Amount,
        post_rshares: int = 0,
        voting_power: int | float | None = None,
        token_power: int | float | None = None,
        not_broadcasted_vote: bool = True,
    ) -> float:
        """
        Return the voting percentage required to produce a specified vote value in the blockchain's backed token (HBD).

        Given a desired token-backed amount (token_units), compute the internal vote percentage (in the same scale used by the chain, e.g. 10000 == 100%) required to yield that payout for a post with post_rshares. If the returned value is larger than 10000 or smaller than -10000, the requested value is outside what the account can reasonably produce.

        Parameters:
            token_units (str|int|Amount): Desired vote value expressed in the blockchain's backed token (HBD). Strings and numbers will be converted to an Amount using the account's blockchain context.
            post_rshares (int, optional): Current rshares for the post; used when converting rshares to a percentage. Default 0.
            voting_power (float|int, optional): Account voting power as returned by get_voting_power (expected on a 0–100 scale). If omitted, the account's current voting power is used.
            token_power (float|int, optional): Account token power (HP). If omitted, the account's current token power is used.
            not_broadcasted_vote (bool, optional): Passed to the conversion routine when estimating rshares from HBD; controls whether broadcast-specific adjustments are applied. Default True.

        Returns:
            int: The vote percentage in chain units (e.g., 10000 == 100%). May exceed ±10000 when the requested value is unattainable.

        Raises:
            AssertionError: If token_units is not expressed in the blockchain's backed token symbol (HBD).
        """
        if voting_power is None:
            voting_power = self.get_voting_power()
        if token_power is None:
            token_power_amount = self.get_token_power()
            token_power = float(token_power_amount) if token_power_amount else 0.0

        if isinstance(token_units, Amount):
            desired_value = Amount(token_units, blockchain_instance=self.blockchain)
        elif isinstance(token_units, str):
            desired_value = Amount(token_units, blockchain_instance=self.blockchain)
        else:
            desired_value = Amount(
                token_units,
                self.blockchain.backed_token_symbol,
                blockchain_instance=self.blockchain,
            )
        if desired_value["symbol"] != self.blockchain.backed_token_symbol:
            raise AssertionError(
                "Should input %s, not any other asset!" % self.blockchain.backed_token_symbol
            )

        full_vote_value = self.get_voting_value(
            post_rshares=post_rshares,
            voting_weight=100,
            voting_power=voting_power,
            token_power=token_power,
            not_broadcasted_vote=not_broadcasted_vote,
        )

        full_vote = float(full_vote_value)
        desired = float(desired_value)
        if full_vote == 0:
            return 0

        ratio = desired / full_vote
        # Clamp to avoid returning excessively large values due to tiny full_vote
        if math.isfinite(ratio):
            ratio = max(min(ratio, 10), -10)
        else:
            ratio = 0

        vote_pct = int(round(ratio * HIVE_100_PERCENT))
        return vote_pct

    def get_recharge_time_str(
        self, voting_power_goal: float = 100, starting_voting_power: float | None = None
    ) -> str:
        """Returns the account recharge time as string

        :param float voting_power_goal: voting power goal in percentage (default is 100)
        :param float starting_voting_power: returns recharge time if current voting power is
            the provided value.

        """
        remainingTime = self.get_recharge_timedelta(
            voting_power_goal=voting_power_goal,
            starting_voting_power=starting_voting_power,
        )
        return formatTimedelta(remainingTime)

    def get_recharge_timedelta(
        self, voting_power_goal: float = 100, starting_voting_power: float | None = None
    ) -> timedelta:
        """
        Return the timedelta required to recharge the account's voting power to a target percentage.

        If `starting_voting_power` is omitted, the current voting power is used. `voting_power_goal`
        and `starting_voting_power` are percentages (e.g., 100 for full power). If the starting
        power already meets or exceeds the goal, the function returns 0.

        Parameters:
            voting_power_goal (float): Target voting power percentage (default 100).
            starting_voting_power (float | int | None): Optional starting voting power percentage to
                use instead of the account's current voting power.

        Returns:
            datetime.timedelta | int: Time required to recharge to the goal as a timedelta, or 0 if
            the starting power is already at or above the goal.

        Raises:
            ValueError: If `starting_voting_power` is provided but is not a number.
        """
        if starting_voting_power is None:
            missing_vp = voting_power_goal - self.get_voting_power()
        elif isinstance(starting_voting_power, int) or isinstance(starting_voting_power, float):
            missing_vp = voting_power_goal - starting_voting_power
        else:
            raise ValueError("starting_voting_power must be a number.")
        if missing_vp < 0:
            return timedelta(0)
        recharge_seconds = (
            missing_vp * 100 * HIVE_VOTING_MANA_REGENERATION_SECONDS / HIVE_100_PERCENT
        )
        return timedelta(seconds=recharge_seconds)

    def get_recharge_time(
        self, voting_power_goal: float = 100, starting_voting_power: float | None = None
    ) -> datetime:
        """Returns the account voting power recharge time in minutes

        :param float voting_power_goal: voting power goal in percentage (default is 100)
        :param float starting_voting_power: returns recharge time if current voting power is
            the provided value.

        """
        return datetime.now(timezone.utc) + self.get_recharge_timedelta(
            voting_power_goal, starting_voting_power
        )

    def get_manabar_recharge_time_str(
        self, manabar: dict[str, Any], recharge_pct_goal: float = 100
    ) -> str:
        """Returns the account manabar recharge time as string

        :param dict manabar: manabar dict from get_manabar() or get_rc_manabar()
        :param float recharge_pct_goal: mana recovery goal in percentage (default is 100)

        """
        remainingTime = self.get_manabar_recharge_timedelta(
            manabar, recharge_pct_goal=recharge_pct_goal
        )
        return formatTimedelta(remainingTime)

    def get_manabar_recharge_timedelta(
        self, manabar: dict[str, Any], recharge_pct_goal: float = 100
    ) -> timedelta:
        """
        Return the time remaining for a manabar to recharge to a target percentage.

        Parameters:
            manabar (dict): Manabar structure returned by get_manabar() or get_rc_manabar().
                Expected to contain either 'current_mana_pct' or 'current_pct' (value in percent).
            recharge_pct_goal (float): Target recharge percentage (0–100). Defaults to 100.

        Returns:
            datetime.timedelta or int: Time required to reach the target as a timedelta. If the
            manabar is already at or above the target, returns 0.
        """
        if "current_mana_pct" in manabar:
            missing_rc_pct = recharge_pct_goal - manabar["current_mana_pct"]
        else:
            missing_rc_pct = recharge_pct_goal - manabar["current_pct"]
        if missing_rc_pct < 0:
            return timedelta(0)
        recharge_seconds = (
            missing_rc_pct * 100 * HIVE_VOTING_MANA_REGENERATION_SECONDS / HIVE_100_PERCENT
        )
        return timedelta(seconds=recharge_seconds)

    def get_manabar_recharge_time(
        self, manabar: dict[str, Any], recharge_pct_goal: float = 100
    ) -> datetime:
        """
        Return the UTC datetime when the given manabar will reach the specified recovery percentage.

        Parameters:
            manabar (dict): Manabar state as returned by get_manabar() or get_rc_manabar().
                Expected keys include 'current_mana' (int), 'max_mana' (int) and 'last_update_time' (datetime or ISO string).
            recharge_pct_goal (float): Target recovery level as a percentage (0–100). Defaults to 100.

        Returns:
            datetime: Timezone-aware UTC datetime when the manabar is expected to reach the target percentage.
        """
        return datetime.now(timezone.utc) + self.get_manabar_recharge_timedelta(
            manabar, recharge_pct_goal
        )
