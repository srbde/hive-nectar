from __future__ import annotations

import json
import logging
import math
import random
import warnings
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from prettytable import PrettyTable

from nectar.amount import Amount
from nectar.constants import (
    HIVE_1_PERCENT,
    HIVE_100_PERCENT,
    HIVE_VOTE_REGENERATION_SECONDS,
    HIVE_VOTING_MANA_REGENERATION_SECONDS,
)
from nectar.instance import shared_blockchain_instance
from nectar.rc import RC
from nectarapi.exceptions import (
    FilteredItemNotFound,
    MissingRequiredActiveAuthority,
)
from nectarbase import operations
from nectargraphenebase.account import PasswordKey, PublicKey

from .blockchain import Blockchain
from .blockchainobject import BlockchainObject
from .exceptions import AccountDoesNotExistsException, OfflineHasNoRPCException
from .haf import HAF
from .utils import (
    addTzInfo,
    formatTimedelta,
    formatTimeString,
    parse_time,
    remove_from_dict,
    reputation_to_score,
)

if TYPE_CHECKING:
    from typing import Any

log = logging.getLogger(__name__)


def extract_account_name(account: str | Account | dict) -> str:
    if isinstance(account, str):
        return account
    elif isinstance(account, Account):
        return account["name"]
    elif isinstance(account, dict) and "name" in account:
        return account["name"]
    else:
        return ""


class Account(BlockchainObject):
    """This class allows to easily access Account data

    :param str account: Name of the account
    :param Blockchain blockchain_instance: Blockchain instance
    :param bool lazy: Use lazy loading
    :param bool full: Obtain all account data including orders, positions,
           etc.
    :returns: Account data
    :rtype: dictionary
    :raises nectar.exceptions.AccountDoesNotExistsException: if account
            does not exist

    Instances of this class are dictionaries that come with additional
    methods (see below) that allow dealing with an account and its
    corresponding functions.

    .. code-block:: python

        >>> from nectar.account import Account
        >>> from nectar import Hive
        >>> from nectar.nodelist import NodeList
        >>> nodelist = NodeList()
        >>> nodelist.update_nodes()
        >>> hv = Hive(node=nodelist.get_hive_nodes())
        >>> account = Account("gtg", blockchain_instance=hv)
        >>> print(account)
        <Account gtg>
        >>> print(account.balances) # doctest: +SKIP

    .. note:: This class comes with its own caching function to reduce the
              load on the API server. Instances of this class can be
              refreshed with ``Account.refresh()``. The cache can be
              cleared with ``Account.clear_cache()``

    """

    type_id = 2

    def __init__(
        self,
        account: str | dict,
        full: bool = True,
        lazy: bool = False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Create an Account wrapper for a blockchain account.

        Parameters:
            account (str | dict): Account name or raw account object/dict. If a dict is provided it will be parsed into the internal account representation.
            full (bool): If True, load complete account data (includes extended fields); if False use a lighter representation.
            lazy (bool): If True, defer fetching/processing of some fields until needed.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.full = full
        self.lazy = lazy
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if isinstance(account, dict):
            account = self._parse_json_data(account)
        super().__init__(
            account,
            lazy=lazy,
            full=full,
            id_item="name",
            blockchain_instance=self.blockchain,
        )

    def refresh(self) -> None:
        """Refresh/Obtain an account's data from the API server"""
        if not self.blockchain.is_connected():
            return
        account = self.blockchain.rpc.find_accounts({"accounts": [self.identifier]})
        if "accounts" in account:
            account = account["accounts"]
        if account and isinstance(account, list) and len(account) == 1:
            account = account[0]
        if not account:
            raise AccountDoesNotExistsException(self.identifier)
        account = self._parse_json_data(account)
        self.identifier = account["name"]

        super().__init__(
            account,
            id_item="name",
            lazy=self.lazy,
            full=self.full,
            blockchain_instance=self.blockchain,
        )

    def _parse_json_data(self, account: dict) -> dict:
        """
        Normalize and convert raw account JSON fields into proper Python types.

        Converts certain string-encoded integer fields to int, parses timestamp strings to datetime via formatTimeString, converts proxied_vsf_votes entries to ints, and wraps balance/vesting fields in Amount objects using the instance's blockchain. The input dict is modified in-place and also returned.

        Parameters:
            account (dict): Raw account JSON as returned by the node; keys like balances, timestamps, and counters will be normalized.

        Returns:
            dict: The same account dict after in-place normalization.
        """
        parse_int = [
            "sbd_seconds",
            "savings_sbd_seconds",
            "average_bandwidth",
            "lifetime_bandwidth",
            "lifetime_market_bandwidth",
            "reputation",
            "withdrawn",
            "to_withdraw",
            "hbd_seconds",
            "savings_hbd_seconds",
        ]
        for p in parse_int:
            if p in account and isinstance(account.get(p), str):
                account[p] = int(account.get(p, 0))
        if "proxied_vsf_votes" in account:
            proxied_vsf_votes = []
            for p_int in account["proxied_vsf_votes"]:
                if isinstance(p_int, str):
                    proxied_vsf_votes.append(int(p_int))
                else:
                    proxied_vsf_votes.append(p_int)
            account["proxied_vsf_votes"] = proxied_vsf_votes
        parse_times = [
            "last_owner_update",
            "last_account_update",
            "created",
            "last_owner_proved",
            "last_active_proved",
            "last_account_recovery",
            "last_vote_time",
            "next_vesting_withdrawal",
            "last_market_bandwidth_update",
            "last_post",
            "last_root_post",
            "last_bandwidth_update",
            "hbd_seconds_last_update",
            "hbd_last_interest_payment",
            "savings_hbd_seconds_last_update",
            "savings_hbd_last_interest_payment",
        ]
        for p in parse_times:
            if p in account and isinstance(account.get(p), str):
                account[p] = parse_time(account.get(p, "1970-01-01T00:00:00"))
        # Parse Amounts
        amounts = [
            "balance",
            "savings_balance",
            "hbd_balance",
            "savings_hbd_balance",
            "reward_hbd_balance",
            "reward_hive_balance",
            "reward_vesting_balance",
            "vesting_shares",
            "delegated_vesting_shares",
            "received_vesting_shares",
            "vesting_withdraw_rate",
            "vesting_balance",
        ]
        for p in amounts:
            if p in account and isinstance(account.get(p), (str, list, dict)):
                account[p] = Amount(account[p], blockchain_instance=self.blockchain)
        return account

    def json(self) -> dict:
        """
        Return a JSON-serializable representation of the account data with normalized field types.

        Converts internal Python objects to plain JSON-friendly types:
        - Specific integer fields are converted to strings (to preserve large integers) or to strings only when non-zero.
        - Elements of `proxied_vsf_votes` are converted to strings when they are non-zero integers; other elements are left unchanged.
        - Datetime, date, and time objects listed in time fields are converted to ISO-like strings via `formatTimeString`; non-datetime values are passed through.
        - Amount-like fields (e.g., balances, vesting shares) are converted by calling their `.json()` method.

        Returns:
            dict: A JSON-serializable dictionary representing the account suitable for serialization.
        """
        output = self.copy()
        parse_int = [
            "sbd_seconds",
            "savings_sbd_seconds",
            "hbd_seconds",
            "savings_hbd_seconds",
        ]
        parse_int_without_zero = [
            "withdrawn",
            "to_withdraw",
            "lifetime_bandwidth",
            "average_bandwidth",
        ]
        for p in parse_int:
            if p in output and isinstance(output[p], int):
                output[p] = str(output[p])
        for p in parse_int_without_zero:
            if p in output and isinstance(output[p], int) and output[p] != 0:
                output[p] = str(output[p])
        if "proxied_vsf_votes" in output:
            proxied_vsf_votes = []
            for p_int in output["proxied_vsf_votes"]:
                if isinstance(p_int, int) and p_int != 0:
                    proxied_vsf_votes.append(str(p_int))
                else:
                    proxied_vsf_votes.append(p_int)
            output["proxied_vsf_votes"] = proxied_vsf_votes
        parse_times = [
            "last_owner_update",
            "last_account_update",
            "created",
            "last_owner_proved",
            "last_active_proved",
            "last_account_recovery",
            "last_vote_time",
            "next_vesting_withdrawal",
            "last_market_bandwidth_update",
            "last_post",
            "last_root_post",
            "last_bandwidth_update",
            "hbd_seconds_last_update",
            "hbd_last_interest_payment",
            "savings_hbd_seconds_last_update",
            "savings_hbd_last_interest_payment",
        ]
        for p in parse_times:
            if p in output:
                p_date = output.get(p, datetime(1970, 1, 1, 0, 0))
                if isinstance(p_date, (datetime, date, time)):
                    output[p] = formatTimeString(p_date)
                else:
                    output[p] = p_date
        amounts = [
            "balance",
            "savings_balance",
            "hbd_balance",
            "savings_hbd_balance",
            "reward_hbd_balance",
            "reward_hive_balance",
            "reward_vesting_balance",
            "vesting_shares",
            "delegated_vesting_shares",
            "received_vesting_shares",
            "vesting_withdraw_rate",
            "vesting_balance",
        ]
        for p in amounts:
            if p in output:
                if p in output:
                    obj = output.get(p)
                    if obj and hasattr(obj, "json"):
                        output[p] = obj.json()
        return json.loads(str(json.dumps(output)))

    def getSimilarAccountNames(self, limit: int = 5) -> list[str] | None:
        """Deprecated, please use get_similar_account_names"""
        return self.get_similar_account_names(limit=limit)

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

    def get_similar_account_names(self, limit: int = 5) -> list[str] | None:
        """Returns ``limit`` account names similar to the current account
        name as a list

        :param int limit: limits the number of accounts, which will be
            returned
        :returns: Similar account names as list
        :rtype: list

        This is a wrapper around :func:`nectar.blockchain.Blockchain.get_similar_account_names()`
        using the current account name as reference.

        """
        b = Blockchain(blockchain_instance=self.blockchain)
        return b.get_similar_account_names(self.name, limit=limit)

    @property
    def name(self) -> str:
        """Returns the account name"""
        return self["name"]

    @property
    def profile(self) -> dict:
        """Returns the account profile"""
        metadata = self.json_metadata
        if "profile" in metadata:
            return metadata["profile"]
        else:
            return {}

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

    @property
    def json_metadata(self) -> dict:
        if self["json_metadata"] == "":
            return {}
        return json.loads(self["json_metadata"])

    @property
    def posting_json_metadata(self) -> dict:
        if self["posting_json_metadata"] == "":
            return {}
        return json.loads(self["posting_json_metadata"])

    def print_info(
        self,
        force_refresh: bool = False,
        return_str: bool = False,
        use_table: bool = False,
        **kwargs,
    ) -> str | None:
        """
        Print account summary information, either printed or returned as a string.

        If force_refresh is True the account data and shared blockchain data are refreshed before computing values.
        The summary includes reputation, voting/downvoting power and recharge times, estimated vote value (HBD),
        token power (HP), balances, and (when available) RC manabar estimates and approximate RC costs for common ops.

        Parameters:
            force_refresh (bool): If True, refresh account and blockchain data before generating the summary.
            return_str (bool): If True, return the formatted summary string instead of printing it.
            use_table (bool): If True, format the output as a two-column PrettyTable; otherwise produce a plain text block.
            **kwargs: Forwarded to PrettyTable.get_string when use_table is True (e.g., sortby, border). These are ignored for plain text output.

        Returns:
            str | None: The formatted summary string when return_str is True; otherwise None (the summary is printed).
        """
        if force_refresh:
            self.refresh()
            self.blockchain.refresh_data(True)
        bandwidth = self.get_bandwidth()
        if (
            bandwidth is not None
            and bandwidth["allocated"] is not None
            and bandwidth["allocated"] > 0
            and bandwidth["used"] is not None
        ):
            remaining = 100 - bandwidth["used"] / bandwidth["allocated"] * 100
            used_kb = bandwidth["used"] / 1024
            allocated_mb = bandwidth["allocated"] / 1024 / 1024
        last_vote_raw = self["last_vote_time"]
        if isinstance(last_vote_raw, str):
            last_vote_dt = datetime.strptime(last_vote_raw, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        else:
            last_vote_dt = addTzInfo(last_vote_raw)

        if last_vote_dt:
            last_vote_time_str = formatTimedelta(datetime.now(timezone.utc) - last_vote_dt)
        else:
            last_vote_time_str = "N/A"
        try:
            rc_mana = self.get_rc_manabar()
            rc = self.get_rc()
            rc_calc = RC(blockchain_instance=self.blockchain)
        except Exception:
            rc_mana = None
            rc_calc = None

        if use_table:
            t = PrettyTable(["Key", "Value"])
            t.align = "l"
            t.add_row(["Name (rep)", self.name + " (%.2f)" % (self.rep)])
            t.add_row(["Voting Power", "%.2f %%, " % (self.get_voting_power())])
            t.add_row(["Downvoting Power", "%.2f %%, " % (self.get_downvoting_power())])
            t.add_row(["Vote Value (HBD)", "%.2f $" % (self.get_voting_value_HBD())])
            t.add_row(["Last vote", "%s ago" % last_vote_time_str])
            t.add_row(["Full in ", "%s" % (self.get_recharge_time_str())])
            t.add_row(
                [
                    "Token Power",
                    "{:.2f} {}".format(self.get_token_power(), self.blockchain.token_symbol),
                ]
            )
            t.add_row(
                [
                    "Balance",
                    "%s, %s"
                    % (
                        str(self.balances["available"][0]),
                        str(self.balances["available"][1]),
                    ),
                ]
            )
            if (
                False
                and bandwidth is not None
                and bandwidth["allocated"] is not None
                and bandwidth["allocated"] > 0
            ):
                t.add_row(["Remaining Bandwidth", "%.2f %%" % (remaining)])
                t.add_row(
                    [
                        "used/allocated Bandwidth",
                        "({:.0f} kb of {:.0f} mb)".format(used_kb, allocated_mb),
                    ]
                )
            if rc_mana is not None:
                if isinstance(rc, dict):
                    max_rc = rc.get("max_rc", 0)
                elif rc and isinstance(rc, list) and len(rc) > 0:
                    max_rc = rc[0].get("max_rc", 0)
                else:
                    max_rc = 0
                if isinstance(max_rc, dict):
                    max_rc = max_rc.get("amount", 0)
                estimated_rc = int(max_rc) * float(rc_mana["current_pct"]) / 100
                t.add_row(["Remaining RC", "%.2f %%" % (rc_mana["current_pct"])])
                t.add_row(
                    [
                        "Remaining RC",
                        "({:.0f} G RC of {:.0f} G RC)".format(
                            estimated_rc / 10**9, int(max_rc) / 10**9
                        ),
                    ]
                )
                t.add_row(["Full in ", "%s" % (self.get_manabar_recharge_time_str(rc_mana))])
                if rc_calc is not None:
                    comment_cost = rc_calc.comment()
                    vote_cost = rc_calc.vote()
                    transfer_cost = rc_calc.transfer()
                    custom_json_cost = rc_calc.custom_json()
                    # Extract numeric values for division
                    comment_val = (
                        comment_cost.get("amount", 0)
                        if isinstance(comment_cost, dict)
                        else comment_cost
                    )
                    vote_val = (
                        vote_cost.get("amount", 0) if isinstance(vote_cost, dict) else vote_cost
                    )
                    transfer_val = (
                        transfer_cost.get("amount", 0)
                        if isinstance(transfer_cost, dict)
                        else transfer_cost
                    )
                    custom_json_val = (
                        custom_json_cost.get("amount", 0)
                        if isinstance(custom_json_cost, dict)
                        else custom_json_cost
                    )
                    t.add_row(["Est. RC for a comment", "%.2f G RC" % (comment_val / 10**9)])
                    t.add_row(["Est. RC for a vote", "%.2f G RC" % (vote_val / 10**9)])
                    t.add_row(["Est. RC for a transfer", "%.2f G RC" % (transfer_val / 10**9)])
                    t.add_row(
                        [
                            "Est. RC for a custom_json",
                            "%.2f G RC" % (custom_json_val / 10**9),
                        ]
                    )

                if estimated_rc is not None and rc_calc is not None:
                    comment_cost = rc_calc.comment()
                    vote_cost = rc_calc.vote()
                    transfer_cost = rc_calc.transfer()
                    custom_json_cost = rc_calc.custom_json()
                    # Extract numeric values from cost dictionaries if needed
                    comment_val = (
                        comment_cost.get("amount", 0)
                        if isinstance(comment_cost, dict)
                        else comment_cost
                    )
                    vote_val = (
                        vote_cost.get("amount", 0) if isinstance(vote_cost, dict) else vote_cost
                    )
                    transfer_val = (
                        transfer_cost.get("amount", 0)
                        if isinstance(transfer_cost, dict)
                        else transfer_cost
                    )
                    custom_json_val = (
                        custom_json_cost.get("amount", 0)
                        if isinstance(custom_json_cost, dict)
                        else custom_json_cost
                    )
                    t.add_row(
                        [
                            "Comments with current RC",
                            "%d comments"
                            % (int(estimated_rc / comment_val) if comment_val > 0 else 0),
                        ]
                    )
                    t.add_row(
                        [
                            "Votes with current RC",
                            "%d votes" % (int(estimated_rc / vote_val) if vote_val > 0 else 0),
                        ]
                    )
                    t.add_row(
                        [
                            "Transfers with current RC",
                            "%d transfers"
                            % (int(estimated_rc / transfer_val) if transfer_val > 0 else 0),
                        ]
                    )
                    t.add_row(
                        [
                            "Custom json with current RC",
                            "%d json ops"
                            % (int(estimated_rc / custom_json_val) if custom_json_val > 0 else 0),
                        ]
                    )

            if return_str:
                return t.get_string(**kwargs)
            else:
                print(t.get_string(**kwargs))
        else:
            ret = self.name + " (%.2f) \n" % (self.rep)
            ret += "--- Voting Power ---\n"
            ret += "%.2f %%, " % (self.get_voting_power())
            ret += " %.2f $\n" % (self.get_voting_value_HBD())
            ret += "full in %s \n" % (self.get_recharge_time_str())
            ret += "--- Downvoting Power ---\n"
            ret += "%.2f %% \n" % (self.get_downvoting_power())
            ret += "--- Balance ---\n"
            ret += "%.2f HP, " % (self.get_token_power())
            ret += "{}, {}\n".format(
                str(self.balances["available"][0]),
                str(self.balances["available"][1]),
            )
            if False and bandwidth["allocated"] > 0:
                ret += "--- Bandwidth ---\n"
                ret += "Remaining: %.2f %%" % (remaining)
                ret += " ({:.0f} kb of {:.0f} mb)\n".format(used_kb, allocated_mb)
            if rc_mana is not None:
                if isinstance(rc, dict):
                    max_rc = rc.get("max_rc", 0)
                elif rc and isinstance(rc, list) and len(rc) > 0:
                    max_rc = rc[0].get("max_rc", 0)
                else:
                    max_rc = 0
                if isinstance(max_rc, dict):
                    max_rc = max_rc.get("amount", 0)
                estimated_rc = int(max_rc) * float(rc_mana["current_pct"]) / 100
                ret += "--- RC manabar ---\n"
                ret += "Remaining: %.2f %%" % (rc_mana["current_pct"])
                ret += " ({:.0f} G RC of {:.0f} G RC)\n".format(
                    estimated_rc / 10**9,
                    int(max_rc) / 10**9,
                )
                ret += "full in %s\n" % (self.get_manabar_recharge_time_str(rc_mana))
                ret += "--- Approx Costs ---\n"
                if rc_calc is not None:
                    comment_cost = rc_calc.comment()
                    vote_cost = rc_calc.vote()
                    transfer_cost = rc_calc.transfer()
                    custom_json_cost = rc_calc.custom_json()
                    # Extract numeric values for division
                    comment_val = (
                        comment_cost.get("amount", 0)
                        if isinstance(comment_cost, dict)
                        else comment_cost
                    )
                    vote_val = (
                        vote_cost.get("amount", 0) if isinstance(vote_cost, dict) else vote_cost
                    )
                    transfer_val = (
                        transfer_cost.get("amount", 0)
                        if isinstance(transfer_cost, dict)
                        else transfer_cost
                    )
                    custom_json_val = (
                        custom_json_cost.get("amount", 0)
                        if isinstance(custom_json_cost, dict)
                        else custom_json_cost
                    )
                    ret += "comment - %.2f G RC - enough RC for %d comments\n" % (
                        comment_val / 10**9,
                        int(estimated_rc / comment_val) if comment_val > 0 else 0,
                    )
                    ret += "vote - %.2f G RC - enough RC for %d votes\n" % (
                        vote_val / 10**9,
                        int(estimated_rc / vote_val) if vote_val > 0 else 0,
                    )
                    ret += "transfer - %.2f G RC - enough RC for %d transfers\n" % (
                        transfer_val / 10**9,
                        int(estimated_rc / transfer_val) if transfer_val > 0 else 0,
                    )
                    ret += "custom_json - %.2f G RC - enough RC for %d custom_json\n" % (
                        custom_json_val / 10**9,
                        int(estimated_rc / custom_json_val) if custom_json_val > 0 else 0,
                    )
            if return_str:
                return ret
            print(ret)

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

    def get_creator(self) -> str | None:
        """Returns the account creator or `None` if the account was mined"""
        if self["mined"]:
            return None
        ops = list(self.get_account_history(1, 1))
        if not ops or "creator" not in ops[-1]:
            return None
        return ops[-1]["creator"]

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

    def get_feed(
        self,
        start_entry_id: int = 0,
        limit: int = 100,
        raw_data: bool = False,
        short_entries: bool = False,
        account=None,
    ):
        """
        Return the feed entries for an account.

        By default this returns a list of Comment objects for the account's feed. If raw_data=True the raw API dicts are returned instead. When both raw_data and short_entries are True the `get_feed_entries` API is used (returns shorter entry objects). If account is None the current Account's name is used.

        Parameters:
            start_entry_id (int): ID offset to start from (default 0).
            limit (int): Maximum number of entries to return (default 100, max 100).
            raw_data (bool): If True, return raw API dictionaries instead of Comment objects.
            short_entries (bool): If True, use get_feed_entries API (shorter entries).
            account (str, optional): Override account name to fetch feed for (default uses this Account).

        Returns:
            list: A list of feed entries (Comment objects or raw dicts depending on `raw_data`).
        """
        if short_entries or raw_data:
            return self.get_feed_entries(
                start_entry_id=start_entry_id,
                limit=limit,
                raw_data=raw_data,
                account=account,
            )
        else:
            return self.get_account_posts(
                sort="feed",
                limit=limit,
                account=account,
                observer=self["name"],
                raw_data=raw_data,
            )

    def get_feed_entries(
        self,
        start_entry_id: int = 0,
        limit: int = 100,
        raw_data: bool = True,
        account=None,
    ):
        """
        Return a list of feed entries for the account.

        If `account` is provided, entries for that account are returned; otherwise uses this Account's name. This method delegates to the internal feed retrieval implementation and requests short-form entries.

        Parameters:
            start_entry_id (int): Entry index to start from (default 0).
            limit (int): Maximum number of entries to return (default 100).
            raw_data (bool): If True, return raw API dictionaries; if False, return wrapped objects (default True).
            account (str, optional): Override account name to fetch feed for (default uses this Account).

        Returns:
            list: A list of feed entries (raw dicts or wrapped objects depending on `raw_data`).
        """
        return self.get_feed(
            start_entry_id=start_entry_id,
            limit=limit,
            raw_data=raw_data,
            short_entries=True,
            account=account,
        )

    def get_blog_entries(
        self,
        start_entry_id: int = 0,
        limit: int = 50,
        raw_data: bool = True,
        account=None,
    ):
        """
        Return the account's blog entries.

        By default returns up to `limit` entries starting at `start_entry_id` for this account. When `raw_data` is True the entries are returned as raw dictionaries from the RPC; when False they are returned as processed Comment objects.

        Parameters:
            start_entry_id (int): Entry index to start from (default 0).
            limit (int): Maximum number of entries to return (default 50, max 100).
            raw_data (bool): If True return raw RPC dicts; if False return Comment objects (default True).
            account (str): Optional account name to fetch entries for (default is this Account's name).

        Returns:
            list: A list of entries (dicts when `raw_data` is True, Comment objects when False).
        """
        # Validate and cap the limit to prevent invalid parameter errors
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if limit > 100:
            limit = 100

        return self.get_blog(
            start_entry_id=start_entry_id,
            limit=limit,
            raw_data=raw_data,
            short_entries=True,
            account=account,
        )

    def get_blog(
        self,
        start_entry_id=0,
        limit=50,
        raw_data=False,
        short_entries=False,
        account=None,
    ):
        """
        Return the blog entries for an account.

        By default this returns a list of Comment objects for the account's blog. If raw_data=True the raw API dicts are returned instead. When both raw_data and short_entries are True the `get_blog_entries` API is used (returns shorter entry objects). If account is None the current Account's name is used.

        Parameters:
            start_entry_id (int): ID offset to start from (default 0).
            limit (int): Maximum number of entries to return (default 50, max 100).
            raw_data (bool): If True, return raw API dictionaries instead of Comment objects.
            short_entries (bool): When True and raw_data is True, use the shorter `get_blog_entries` API.
            account (str|Account|dict|None): Account to query; if None uses this Account.

        Returns:
            list: A list of Comment objects (when raw_data is False) or raw entry dictionaries (when raw_data is True).

        Raises:
            OfflineHasNoRPCException: If called while offline (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)

        # Validate and cap the limit to prevent invalid parameter errors
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if limit > 100:
            limit = 100

        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)

        def _extract_blog_items(payload: Any) -> Any:
            if isinstance(payload, dict):
                for key in ("blog", "blog_entries", "result"):
                    if key in payload:
                        return payload[key]
            return payload

        try:
            if raw_data and short_entries:
                ret = self.blockchain.rpc.get_blog_entries(
                    account,
                    start_entry_id,
                    limit,
                )
                ret = _extract_blog_items(ret)
                return [c for c in ret]
            elif raw_data:
                ret = self.blockchain.rpc.get_blog(
                    account,
                    start_entry_id,
                    limit,
                )
                ret = _extract_blog_items(ret)
                return [c for c in ret]
            else:
                from .comment import Comment

                ret = self.blockchain.rpc.get_blog(
                    account,
                    start_entry_id,
                    limit,
                )
                ret = _extract_blog_items(ret)
                return [Comment(c["comment"], blockchain_instance=self.blockchain) for c in ret]
        except Exception:
            return []

    def get_notifications(
        self,
        only_unread: bool = True,
        limit: int | None = 100,
        raw_data: bool = False,
        account=None,
    ):
        """Returns account notifications

        :param bool only_unread: When True, only unread notifications are shown
        :param int limit: When set, the number of shown notifications is limited (max limit = 100)
        :param bool raw_data: When True, the raw data from the api call is returned.
        :param str account: (optional) the account for which the notification should be received
            to (defaults to ``default_account``)
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if only_unread:
            unread_notes = self.blockchain.rpc.unread_notifications({"account": account})
            if unread_notes is None:
                return []
            if limit is None or limit > unread_notes["unread"]:
                limit = unread_notes["unread"]
        if limit is None or limit == 0:
            return []
        if limit > 100:
            limit = 100
        notifications = self.blockchain.rpc.account_notifications(
            {"account": account, "limit": limit}
        )
        if raw_data:
            return notifications
        ret = []
        for note in notifications:
            note["date"] = formatTimeString(note["date"])
            ret.append(note)
        return ret

    def mark_notifications_as_read(
        self, last_read: str | None = None, account: str | None = None
    ) -> dict[str, Any]:
        """Broadcast a mark all notification as read custom_json

        :param str last_read: When set, this datestring is used to set the mark as read date
        :param str account: (optional) the account to broadcast the custom_json
            to (defaults to ``default_account``)

        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not account:
            raise ValueError("You need to provide an account")
        if last_read is None:
            last_notification = self.get_notifications(only_unread=False, limit=1, account=account)
            if len(last_notification) == 0:
                raise ValueError("Notification list is empty")
            last_read_dt = datetime.now(timezone.utc)
        else:
            last_read_dt = (
                addTzInfo(last_read) if isinstance(last_read, (datetime, date, time)) else None
            )
        if last_read_dt is None:
            # if provided as string, trust it; otherwise format our datetime
            last_read_str = str(last_read)
        else:
            last_read_str = formatTimeString(last_read_dt)
        json_body = [
            "setLastRead",
            {
                "date": last_read_str,
            },
        ]
        return self.blockchain.custom_json("notify", json_body, required_posting_auths=[account])

    def get_blog_authors(self, account: str | None = None) -> list[str]:
        """
        Return a list of author account names whose posts have been reblogged on the specified blog account.

        If `account` is omitted, uses this Account object's name. Raises OfflineHasNoRPCException if called while offline. Returns a list of strings (author account names).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        result = self.blockchain.rpc.get_blog_authors({"blog_account": account})
        if isinstance(result, dict) and "blog_authors" in result:
            return result["blog_authors"]
        return []

    def get_follow_count(self, account: str | None = None) -> dict[str, Any]:
        """get_follow_count"""
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.get_follow_count(account)

    def get_followers(self, raw_name_list: bool = True, limit: int = 100) -> list[str] | Accounts:
        """Returns the account followers as list"""
        name_list = [x["follower"] for x in self._get_followers(direction="follower", limit=limit)]
        if raw_name_list:
            return name_list
        else:
            return Accounts(name_list, blockchain_instance=self.blockchain)

    def get_following(self, raw_name_list: bool = True, limit: int = 100) -> list[str] | Accounts:
        """Returns who the account is following as list"""
        name_list = [
            x["following"] for x in self._get_followers(direction="following", limit=limit)
        ]
        if raw_name_list:
            return name_list
        else:
            return Accounts(name_list, blockchain_instance=self.blockchain)

    def get_muters(self, raw_name_list: bool = True, limit: int = 100) -> list[str] | Accounts:
        """Returns the account muters as list"""
        name_list = [
            x["follower"]
            for x in self._get_followers(direction="follower", what="ignore", limit=limit)
        ]
        if raw_name_list:
            return name_list
        else:
            return Accounts(name_list, blockchain_instance=self.blockchain)

    def get_mutings(self, raw_name_list: bool = True, limit: int = 100) -> list[str] | Accounts:
        """
        Return the list of accounts this account has muted.

        Parameters:
            raw_name_list (bool): If True (default), return a list of account names (str). If False, return an Accounts collection of Account objects.
            limit (int): Maximum number of muted accounts to fetch (default 100).

        Returns:
            list[str] | Accounts: Either a list of account names or an Accounts object containing the muted accounts.
        """
        name_list = [
            x["following"]
            for x in self._get_followers(direction="following", what="ignore", limit=limit)
        ]
        if raw_name_list:
            return name_list
        else:
            return Accounts(name_list, blockchain_instance=self.blockchain)

    def get_follow_list(
        self,
        follow_type: str,
        starting_account: str | None = None,
        raw_name_list: bool = True,
    ) -> list[dict[str, Any]] | Accounts:
        """
        Return the account follow list for a given follow_type (requires Hive HF >= 24).

        Normalizes legacy aliases ('blacklisted' -> 'follow_blacklist', 'muted' -> 'follow_muted')
        and queries the blockchain bridge API for the observer's follow list. Supports pagination
        via an optional starting_account cursor.

        Parameters:
            follow_type (str): One of 'follow_blacklist' or 'follow_muted' (aliases 'blacklisted' and 'muted' accepted).
            starting_account (Optional[str]): Optional pagination start cursor (name of the account to start from).
            raw_name_list (bool): If True, return the raw list of dicts from the bridge API (each dict typically contains a 'name' key).
                                  If False, return an Accounts collection built from the returned names.

        Returns:
            Union[List[Dict[str, Any]], Accounts]: Raw list of follow entries (dicts) when raw_name_list is True,
                                                  otherwise an Accounts instance containing the followed account names.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is in offline mode (no RPC available).
            ValueError: If follow_type is not one of the supported values or aliases.
        """
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        # Normalize follow_type to canonical values accepted by all nodes
        alias_map = {
            "blacklisted": "follow_blacklist",
            "muted": "follow_muted",
        }
        normalized_follow_type = alias_map.get(follow_type, follow_type)
        valid_types = {"follow_blacklist", "follow_muted"}
        if normalized_follow_type not in valid_types:
            raise ValueError(
                "Invalid follow_type. Use one of: 'blacklisted', 'muted', 'follow_blacklist', 'follow_muted'"
            )

        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        query = {
            "observer": self.name,
            "follow_type": normalized_follow_type,
        }
        if starting_account is not None:
            query["start"] = starting_account

            followers = self.blockchain.rpc.get_follow_list(query)

        name_list: list[dict[str, Any]] = followers or []
        if raw_name_list:
            return name_list
        else:
            # Convert list of dicts to list of account names for Accounts initializer
            account_names: list[str] = [x["name"] for x in name_list if "name" in x]
            return Accounts(account_names, blockchain_instance=self.blockchain)

    def _get_followers(
        self,
        direction: str = "follower",
        last_user: str = "",
        what: str = "blog",
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch and return the full list of follower or following entries for this account by repeatedly calling the condenser follow APIs.

        This helper paginates through get_followers/get_following RPC calls (appbase and legacy modes supported) until no more pages are returned, concatenating results into a single list. When batching, duplicate leading entries from subsequent pages are skipped so entries are not repeated.

        Parameters:
            direction (str): "follower" to fetch followers, "following" to fetch accounts this account follows.
            last_user (str): Starting username for pagination (inclusive start for the first call); subsequent pages are continued internally.
            what (str): Relationship type filter passed to the RPC (commonly "blog" or "ignore").
            limit (int): Maximum number of entries to request per RPC call (page size).

        Returns:
            list: A list of follower/following records as returned by the condenser API.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is offline.
        """
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        followers_list = []
        limit_reached = True
        cnt = 0
        while limit_reached:
            self.blockchain.rpc.set_next_node_on_empty_reply(False)
            query = (self.name, last_user, what, limit)
            if direction == "follower":
                followers = self.blockchain.rpc.get_followers(*query)
                if isinstance(followers, dict) and "followers" in followers:
                    followers = followers["followers"]
            elif direction == "following":
                followers = self.blockchain.rpc.get_following(*query)
                if isinstance(followers, dict) and "following" in followers:
                    followers = followers["following"]

            if cnt == 0:
                followers_list = followers
            elif followers is not None and len(followers) > 1:
                followers_list += followers[1:]
            if followers is not None and len(followers) >= limit:
                last_user = followers[-1][direction]
                limit_reached = True
                cnt += 1
            else:
                limit_reached = False

        return followers_list

    def list_all_subscriptions(self, account: str | None = None) -> list[dict[str, Any]]:
        """Returns all subscriptions"""
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        try:
            subscriptions = self.blockchain.rpc.list_all_subscriptions({"account": account})
            if subscriptions is None:
                return []
            return subscriptions
        except Exception:
            # The list_all_subscriptions API might not be supported on all nodes
            # Return empty list as fallback
            return []

    def get_account_posts(
        self,
        sort: str = "feed",
        limit: int = 20,
        account: str | None = None,
        observer: str | None = None,
        raw_data: bool = False,
    ) -> Any:
        """Returns account feed"""
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if observer is None:
            observer = account
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        from nectar.comment import AccountPosts

        return AccountPosts(sort, account, observer=observer, limit=limit, raw_data=raw_data)

    @property
    def available_balances(self) -> list[Amount]:
        """
        Return a list of the account's available balances as Amount objects.

        Includes liquid HIVE ("balance"), HBD ("hbd_balance") when present, and vesting shares ("vesting_shares").
        Balances are returned in that order when available and are shallow copies of the stored Amount objects.
        """
        if "hbd_balance" in self:
            amount_list = ["balance", "hbd_balance", "vesting_shares"]
        else:
            amount_list = ["balance", "vesting_shares"]
        available_amount = []
        for amount in amount_list:
            if amount in self:
                available_amount.append(self[amount].copy())
        return available_amount

    @property
    def saving_balances(self) -> list[Amount]:
        """
        Return the account's savings balances.

        Returns a list of Amount objects representing savings balances present on the account.
        Includes "savings_balance" and, if present, "savings_hbd_balance". Returns an empty list if no
        savings balances are available.
        """
        savings_amount = []
        if "savings_hbd_balance" in self:
            amount_list = ["savings_balance", "savings_hbd_balance"]
        else:
            amount_list = ["savings_balance"]
        for amount in amount_list:
            if amount in self:
                savings_amount.append(self[amount].copy())
        return savings_amount

    @property
    def reward_balances(self) -> list[Amount]:
        """
        Return the account's reward balances as a list of Amount objects.

        Checks for reward-related fields ('reward_hive_balance', 'reward_hbd_balance', 'reward_vesting_balance') on the account and returns copies of any that exist, preserving the original stored Amount objects. The list order is: reward_hive_balance, reward_hbd_balance, reward_vesting_balance (when present).

        Returns:
            list: A list of Amount instances (copies) for each available reward balance.
        """
        if "reward_hive_balance" in self and "reward_hbd_balance" in self:
            amount_list = [
                "reward_hive_balance",
                "reward_hbd_balance",
                "reward_vesting_balance",
            ]
        else:
            amount_list = []
        rewards_amount = []
        for amount in amount_list:
            if amount in self:
                rewards_amount.append(self[amount].copy())
        return rewards_amount

    @property
    def total_balances(self) -> list[Amount]:
        symbols = []
        for balance in self.available_balances:
            symbols.append(balance["symbol"])
        ret = []
        for i in range(len(symbols)):
            balance_sum = self.get_balance(self.available_balances, symbols[i])
            saving_balance = self.get_balance(self.saving_balances, symbols[i])
            reward_balance = self.get_balance(self.reward_balances, symbols[i])
            if balance_sum is not None and saving_balance is not None:
                balance_sum = balance_sum + saving_balance
            elif saving_balance is not None:
                balance_sum = saving_balance
            if balance_sum is not None and reward_balance is not None:
                balance_sum = balance_sum + reward_balance
            elif reward_balance is not None:
                balance_sum = reward_balance
            ret.append(balance_sum)
        return ret

    @property
    def balances(self) -> dict[str, list[Amount]]:
        """Returns all account balances as dictionary"""
        return self.get_balances()

    def get_balances(self) -> dict[str, list[Amount]]:
        """
        Return the account's balances grouped by category.

        Returns a dictionary with keys:
        - "available": list of Amounts currently spendable (e.g., HIVE, HBD, VESTS)
        - "savings": list of Amounts held in savings
        - "rewards": list of pending reward Amounts
        - "total": list of total Amounts combining available, savings, and rewards

        Returns:
            dict: Mapping of balance category to a list of Amount objects (or empty list for absent symbols).
        """
        return {
            "available": self.available_balances,
            "savings": self.saving_balances,
            "rewards": self.reward_balances,
            "total": self.total_balances,
        }

    def get_balance(
        self, balances: str | list[dict[str, Any]] | list[Amount], symbol: str
    ) -> Amount | None:
        """
        Return a specific balance Amount for this account.

        Accepts either a list of balance dicts or a balance category name and returns the Amount for the requested symbol. Valid balance category names are "available", "savings", "rewards", and "total". The symbol may be a string (e.g., "HBD", "HIVE", "VESTS") or a dict containing a "symbol" key.

        Parameters:
            balances (str | list[dict]): A balance category name or a list of balance dicts (each with keys "amount" and "symbol").
            symbol (str | dict): The asset symbol to look up, or a dict containing {"symbol": <str>}.

        Returns:
            nectar.amount.Amount: The matching Amount from the provided balances, or Amount(0, symbol) if no matching entry is found.
        """
        if isinstance(balances, str):
            if balances == "available":
                balances = self.available_balances
            elif balances == "savings":
                balances = self.saving_balances
            elif balances == "rewards":
                balances = self.reward_balances
            elif balances == "total":
                balances = self.total_balances
            else:
                return

        if isinstance(symbol, dict) and "symbol" in symbol:
            symbol = symbol["symbol"]

        for b in balances:
            if isinstance(b, Amount) and b.symbol == symbol:
                return b
            elif isinstance(b, dict) and b.get("symbol") == symbol:
                return Amount(b, blockchain_instance=self.blockchain)

        return Amount(0, symbol, blockchain_instance=self.blockchain)

    def interest(self) -> dict[str, float | datetime | timedelta]:
        """Calculate interest for an account

        :param str account: Account name to get interest for
        :rtype: dictionary

        Sample output:

        .. code-block:: js

            {
                'interest': 0.0,
                'last_payment': datetime.datetime(2018, 1, 26, 5, 50, 27, tzinfo=<UTC>),
                'next_payment': datetime.datetime(2018, 2, 25, 5, 50, 27, tzinfo=<UTC>),
                'next_payment_duration': datetime.timedelta(-65, 52132, 684026),
                'interest_rate': 0.0
            }

        """
        interest_amount = 0
        interest_rate = 0
        next_payment = datetime(1970, 1, 1, 0, 0, 0)
        last_payment = datetime(1970, 1, 1, 0, 0, 0)
        if "sbd_last_interest_payment" in self:
            last_payment = self["sbd_last_interest_payment"]
            next_payment = last_payment + timedelta(days=30)
            interest_rate = (
                self.blockchain.get_dynamic_global_properties()["sbd_interest_rate"] / 100
            )  # percent
            interest_amount = (
                (interest_rate / 100)
                * int(int(self["sbd_seconds"]) / (60 * 60 * 24 * 356))
                * 10**-3
            )
        elif "hbd_last_interest_payment" in self:
            last_payment = self["hbd_last_interest_payment"]
            next_payment = last_payment + timedelta(days=30)
            interest_rate = (
                self.blockchain.get_dynamic_global_properties()["hbd_interest_rate"] / 100
            )  # percent
            interest_amount = (
                (interest_rate / 100)
                * int(int(self["hbd_seconds"]) / (60 * 60 * 24 * 356))
                * 10**-3
            )
        return {
            "interest": interest_amount,
            "last_payment": last_payment,
            "next_payment": next_payment,
            "next_payment_duration": next_payment - datetime.now(timezone.utc),
            "interest_rate": interest_rate,
        }

    @property
    def is_fully_loaded(self) -> bool:
        """Is this instance fully loaded / e.g. all data available?

        :rtype: bool
        """
        return self.full

    def ensure_full(self) -> None:
        """Ensure that all data are loaded"""
        if not self.is_fully_loaded:
            self.full = True
            self.refresh()

    def get_account_bandwidth(
        self, bandwidth_type: int = 1, account: str | None = None
    ) -> dict[str, int | str]:
        """get_account_bandwidth"""
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.get_account_bandwidth(account, bandwidth_type)

    def get_bandwidth(self) -> dict[str, int | None]:
        """Returns used and allocated bandwidth

        :rtype: dictionary

        Sample output:

            .. code-block:: js

                {
                    'used': 0,
                    'allocated': 2211037
                }

        """
        account = self["name"]
        global_properties = self.blockchain.get_dynamic_global_properties()
        try:
            reserve_ratio = self.blockchain.get_reserve_ratio()
        except Exception:
            return {"used": 0, "allocated": 0}
        if "received_vesting_shares" in self:
            received_vesting_shares = self["received_vesting_shares"].amount
        else:
            received_vesting_shares = 0
        vesting_shares = self["vesting_shares"].amount
        if reserve_ratio is None or reserve_ratio["max_virtual_bandwidth"] is None:
            return {"used": None, "allocated": None}
        max_virtual_bandwidth = float(reserve_ratio["max_virtual_bandwidth"])
        total_vesting_shares = Amount(
            global_properties["total_vesting_shares"],
            blockchain_instance=self.blockchain,
        ).amount
        allocated_bandwidth = (
            max_virtual_bandwidth
            * (vesting_shares + received_vesting_shares)
            / total_vesting_shares
        )
        allocated_bandwidth = round(allocated_bandwidth / 1000000)

        try:
            account_bandwidth = self.get_account_bandwidth(bandwidth_type=1, account=account)
        except Exception:
            account_bandwidth = None
        if account_bandwidth is None:
            return {"used": 0, "allocated": allocated_bandwidth}
        from nectar.utils import parse_time

        last_bandwidth_update = parse_time(str(account_bandwidth["last_bandwidth_update"]))
        average_bandwidth = float(account_bandwidth["average_bandwidth"])
        total_seconds = 604800

        seconds_since_last_update = datetime.now(timezone.utc) - last_bandwidth_update
        seconds_since_last_update = seconds_since_last_update.total_seconds()
        used_bandwidth = 0
        if seconds_since_last_update < total_seconds:
            used_bandwidth = (
                (total_seconds - seconds_since_last_update) * average_bandwidth
            ) / total_seconds
        used_bandwidth = round(used_bandwidth / 1000000)

        return {"used": used_bandwidth, "allocated": allocated_bandwidth}
        # print("bandwidth percent used: " + str(100 * used_bandwidth / allocated_bandwidth))
        # print("bandwidth percent remaining: " + str(100 - (100 * used_bandwidth / allocated_bandwidth)))

    def get_owner_history(self, account: str | None = None) -> list[dict[str, Any]]:
        """
        Return the owner authority history for an account.

        If `account` is provided, fetches the owner history for that account; otherwise uses this Account's name.
        Returns a list of owner-authority history entries (RPC dicts, typically those under the `owner_auths` key).

        Parameters:
            account (str, optional): Account name or Account-like object to query. Defaults to this Account's name.

        Returns:
            list: Owner history entries as returned by the node RPC.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain is in offline mode (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.find_owner_histories({"owner": account})["owner_auths"]

    def get_conversion_requests(self, account: str | None = None) -> list[dict[str, Any]]:
        """
        Return the list of pending HBD conversion requests for an account.

        If `account` is omitted, the method queries conversion requests for this Account instance.

        Parameters:
            account (str, optional): Account name or Account-like object. Defaults to this account's name.

        Returns:
            list: A list of conversion request dictionaries (empty list if none).

        Raises:
            OfflineHasNoRPCException: If called while the blockchain is in offline mode (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        try:
            return self.blockchain.rpc.find_hbd_conversion_requests({"account": account})[
                "requests"
            ]
        except Exception:
            return []

    def get_vesting_delegations(
        self, start_account: str = "", limit: int = 100, account: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return the list of vesting delegations made by an account.

        If `account` is omitted, the method uses this Account object's name. Results can be paginated by specifying `start_account` (delegatee name to start from) and `limit` (maximum number of entries returned). In appbase mode the call filters returned delegations to those where the delegator matches `account`.

        Parameters:
            start_account (str): Delegatee name to start listing from (for pagination). Default is empty string (start from first).
            limit (int): Maximum number of results to return. Default is 100.
            account (str | Account, optional): Account to query; accepts an account name or Account-like object. If None, uses this Account.

        Returns:
            list: A list of delegation dictionaries as returned by the node RPC.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is offline (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        delegations = self.blockchain.rpc.list_vesting_delegations(
            {
                "start": [account, start_account],
                "limit": limit,
                "order": "by_delegation",
            },
        )["delegations"]
        return [d for d in delegations if d["delegator"] == account]

    def get_withdraw_routes(self, account: str | None = None) -> list[dict[str, Any]]:
        """
        Return the account's withdraw vesting routes.

        If `account` is omitted, uses this Account object's name. Each route is returned as a dict
        in the format provided by the node RPC (fields include destination account, percentage, auto_vest, etc.).

        Parameters:
            account (str, optional): Account name to query. Defaults to this Account's name.

        Returns:
            list: A list of withdraw-route dictionaries as returned by the node RPC.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is in offline mode.
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.find_withdraw_vesting_routes(
            {"account": account, "order": "by_withdraw_route"}
        )["routes"]

    def get_savings_withdrawals(
        self, direction: str = "from", account: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return the list of savings withdrawal requests for an account.

        If no account is provided, uses this Account's name. On nodes using the appbase/database API the node determines which withdrawals are returned; on legacy (non-appbase) nodes the `direction` parameter selects between withdrawals originating "from" the account or destined "to" the account.

        Parameters:
            account (str, optional): Account name to query. Defaults to this account.
            direction (str, optional): "from" or "to" (default "from"). Only used on non-appbase RPC nodes.

        Returns:
            list: A list of savings withdrawal records (each record is a dict as returned by the node).

        Raises:
            OfflineHasNoRPCException: If called while in offline mode (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.find_savings_withdrawals({"account": account})["withdrawals"]

    def get_recovery_request(self, account: str | None = None) -> list[dict[str, Any]]:
        """Returns the recovery request for an account

        :param str account: When set, a different account is used for the request (Default is object account name)

        :rtype: list

        .. code-block:: python

            >>> from nectar.account import Account
            >>> from nectar import Hive
            >>> from nectar.nodelist import NodeList
            >>> nodelist = NodeList()
            >>> nodelist.update_nodes()
            >>> hv = Hive(node=nodelist.get_hive_nodes())
            >>> account = Account("nectarflower", blockchain_instance=hv)
            >>> account.get_recovery_request()
            []

        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.find_account_recovery_requests({"accounts": [account]})[
            "requests"
        ]

    def get_escrow(self, escrow_id: int = 0, account: str | None = None) -> list[dict[str, Any]]:
        """
        Return escrow(s) related to this account.

        If called in appbase mode, returns all escrows for the given account (the
        legacy escrow_id parameter is ignored). In legacy (pre-appbase) mode,
        returns the escrow with the specified escrow_id for the account.

        Parameters:
            escrow_id (int): Escrow identifier used by legacy RPC (pre-appbase). Default 0.
            account (str | Account, optional): Account to query; defaults to this account's name.

        Returns:
            list[dict]: A list of escrow objects (empty if none found).

        Raises:
            OfflineHasNoRPCException: If called while the blockchain client is offline.
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.find_escrows({"from": account})["escrows"]

    def verify_account_authority(
        self, keys: list[str] | str, account: str | None = None
    ) -> dict[str, Any]:
        """
        Return whether the provided signers (public keys) are sufficient to authorize the specified account.

        If `account` is omitted, uses this Account object's name. `keys` may be a single key or a list of public keys.
        Returns a dictionary as returned by the node RPC (e.g., {"valid": True} or {"valid": False}).
        Raises OfflineHasNoRPCException when the instance is offline. If the RPC raises MissingRequiredActiveAuthority
        during verification, the method returns {"valid": False}.
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        if not isinstance(keys, list):
            keys = [keys]
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        try:
            return self.blockchain.rpc.verify_account_authority(
                {"account": account, "signers": keys}
            )
        except MissingRequiredActiveAuthority:
            return {"valid": False}

    def get_tags_used_by_author(self, account: str | None = None) -> list[dict[str, Any]]:
        """Returns a list of tags used by an author.

        :param str account: When set, a different account is used for the request (Default is object account name)

        :rtype: list

        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.get_tags_used_by_author(account)["tags"]

    def get_expiring_vesting_delegations(
        self,
        after: datetime | str | None = None,
        limit: int = 1000,
        account: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return upcoming vesting-delegation expirations for an account.

        If `account` is None the current Account's name is used. On appbase-compatible nodes this queries the
        database API and returns the list under the "delegations" key; on legacy nodes it calls the
        legacy RPC which accepts `after` (a datetime) and `limit`.

        Parameters:
            after (datetime, optional): Only used on pre-appbase nodes — include expirations after this time.
            limit (int, optional): Only used on pre-appbase nodes — maximum number of entries to return.
            account (str or object, optional): Account name or object to query. Defaults to the current account.

        Returns:
            list: A list of vesting delegation expiration records.

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is offline.
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if after is None:
            after = datetime.now(timezone.utc) - timedelta(days=8)
        return self.blockchain.rpc.find_vesting_delegation_expirations({"account": account})[
            "delegations"
        ]

    def get_account_votes(
        self,
        account: str | None = None,
        start_author: str = "",
        start_permlink: str = "",
        limit: int = 1000,
        start_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return a list of vote operations made by an account.

        Retrieves votes by paging through the node's `list_votes` (database) API ordered by voter+comment. Returns vote objects (dicts) that include fields such as `voter`, `author`, `permlink`, `weight`, and `last_update`. Results are filtered so only votes cast by `account` are included and, if `start_date` is provided, only votes with `last_update >= start_date` are returned. Pagination state is advanced using `start_author` / `start_permlink`.

        Parameters:
            account (str|dict|Account, optional): Account to query. If None, uses this Account's name.
            start_author (str, optional): Author permlink paging start key (used to continue from a previous page).
            start_permlink (str, optional): Permlink paging start key paired with `start_author`.
            limit (int, optional): Maximum number of votes to request per RPC call (page size).
            start_date (datetime.datetime, optional): If provided, stop and exclude votes older than this datetime.

        Returns:
            list[dict]: List of vote dictionaries in descending retrieval order (newest first as returned by the node).

        Raises:
            OfflineHasNoRPCException: If called while the blockchain instance is offline (no RPC available).
        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        try:
            ret = self.blockchain.rpc.list_votes(
                {
                    "start": [account, start_author, start_permlink],
                    "limit": limit,
                    "order": "by_voter_comment",
                }
            )["votes"]
        except Exception:
            return []
        vote_list = []
        for vote in ret:
            if vote.get("voter") != account:
                continue
            last_update = formatTimeString(str(vote["last_update"]))
            if (
                start_date is not None
                and isinstance(last_update, datetime)
                and last_update < start_date
            ):
                continue
            vote_list.append(vote)
        return vote_list
        # else:
        #     return vote_list

    def get_vote(self, comment: str | Any) -> dict[str, Any] | None:
        """Returns a vote if the account has already voted for comment.

        :param comment: can be a Comment object or a authorpermlink
        :type comment: str, Comment
        """
        from nectar.comment import Comment

        c = Comment(comment, blockchain_instance=self.blockchain)
        for v in c["active_votes"]:
            if v["voter"] == self["name"]:
                return v
        return None

    def has_voted(self, comment: str | Any) -> bool:
        """Returns if the account has already voted for comment

        :param comment: can be a Comment object or a authorpermlink
        :type comment: str, Comment
        """
        from nectar.comment import Comment

        c = Comment(comment, blockchain_instance=self.blockchain)
        active_votes = {v["voter"]: v for v in c["active_votes"]}
        return self["name"] in active_votes

    def virtual_op_count(self, until: int | None = None) -> int:
        """Returns the number of individual account transactions

        :rtype: list
        """
        if until is not None:
            return self.estimate_virtual_op_num(until, stop_diff=1)
        else:
            try:
                op_count = 0
                op_count = self._get_account_history(start=-1, limit=1)
                if op_count is None or len(op_count) == 0:
                    op_count = self._get_account_history(start=-1, limit=1)
                if isinstance(op_count, list) and len(op_count) > 0 and len(op_count[0]) > 0:
                    if self.blockchain.rpc.url == "https://api.hive.blog":
                        return op_count[-1][0] + 1
                    return op_count[-1][0]
                else:
                    return 0
            except IndexError:
                return 0

    def _get_account_history(
        self,
        account=None,
        start: int = -1,
        limit: int = 1,
        operation_filter_low: int | None = None,
        operation_filter_high: int | None = None,
    ) -> list | None:
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if limit < 1:
            limit = 1
        elif limit > 1000:
            limit = 1000
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        if operation_filter_low is None and operation_filter_high is None:
            ret = self.blockchain.rpc.get_account_history(
                {"account": account, "start": start, "limit": limit}
            )
            if ret is not None:
                ret = ret["history"]
        else:
            ret = self.blockchain.rpc.get_account_history(
                {
                    "account": account,
                    "start": start,
                    "limit": limit,
                    "operation_filter_low": operation_filter_low,
                    "operation_filter_high": operation_filter_high,
                },
            )
            if ret is not None:
                ret = ret["history"]
        return ret

    def _get_blocknum_from_hist(self, index: int, min_index: int = 1) -> int | None:
        if index >= 0 and index < min_index:
            index = min_index
        op = self._get_account_history(start=(index))
        if op is None or len(op) == 0:
            return None
        return op[0][1]["block"]

    def _get_first_blocknum(self) -> tuple[int | None, int]:
        min_index = 0
        try:
            created = self._get_blocknum_from_hist(0, min_index=min_index)
        except Exception:
            min_index = 1
            created = self._get_blocknum_from_hist(0, min_index=min_index)
        return created, min_index

    def estimate_virtual_op_num(
        self,
        blocktime: int | datetime | date | time,
        stop_diff: int = 0,
        max_count: int = 100,
        min_index: int | None = None,
    ) -> int:
        """Returns an estimation of an virtual operation index for a given time or blockindex

        :param blocktime: start time or start block index from which account
            operation should be fetched
        :type blocktime: int, datetime
        :param int stop_diff: Sets the difference between last estimation and
            new estimation at which the estimation stops. Must not be zero. (default is 1)
        :param int max_count: sets the maximum number of iterations. -1 disables this (default 100)

        .. testsetup::

            from nectar.account import Account
            from nectar.blockchain import Blockchain
            from datetime import datetime, timedelta
            from timeit import time as t
        .. testcode::

            start_time = datetime.now() - timedelta(days=7)
            acc = Account("gtg")
            start_op = acc.estimate_virtual_op_num(start_time)

            b = Blockchain()
            start_block_num = b.get_estimated_block_num(start_time)
            start_op2 = acc.estimate_virtual_op_num(start_block_num)

        .. testcode::

            acc = Account("gtg")
            block_num = 21248120
            start = t.time()
            op_num = acc.estimate_virtual_op_num(block_num, stop_diff=1, max_count=10)
            stop = t.time()
            print(stop - start)
            for h in acc.get_account_history(op_num, 0):
                block_est = h["block"]
            print(block_est - block_num)

        """
        max_index = self.virtual_op_count()
        if max_index < stop_diff:
            return 0

        # calculate everything with block numbers
        if min_index is None:
            created, min_index = self._get_first_blocknum()
        else:
            created = self._get_blocknum_from_hist(0, min_index=min_index)

        # convert blocktime to block number if given as a datetime/date/time
        if isinstance(blocktime, (datetime, date, time)):
            b = Blockchain(blockchain_instance=self.blockchain)
            target_blocknum = b.get_estimated_block_num(addTzInfo(blocktime), accurate=True)
        elif isinstance(blocktime, str):
            try:
                # Try to parse as a time string
                from nectar.utils import parse_time

                parsed_time = parse_time(blocktime)
                b = Blockchain(blockchain_instance=self.blockchain)
                target_blocknum = b.get_estimated_block_num(parsed_time, accurate=True)
            except (ValueError, TypeError):
                # If parsing fails, treat it as a block number string
                target_blocknum = int(blocktime)
        else:
            target_blocknum = blocktime

        # the requested blocknum/timestamp is before the account creation date
        if created is not None and target_blocknum <= created:
            return 0

        # get the block number from the account's latest operation
        latest_blocknum = self._get_blocknum_from_hist(-1, min_index=min_index)
        # requested blocknum/timestamp is after the latest account operation
        if latest_blocknum is not None and target_blocknum >= latest_blocknum:
            return max_index

        # all account ops in a single block
        if latest_blocknum is not None and created is not None and latest_blocknum - created == 0:
            return 0

        # set initial search range
        op_num = 0
        op_lower = 0
        block_lower = created
        op_upper = max_index
        block_upper = latest_blocknum
        last_op_num = None
        cnt = 0

        while True:
            # check if the maximum number of iterations was reached
            if max_count != -1 and cnt >= max_count:
                # did not converge, return the current state
                return op_num

            # linear approximation between the known upper and
            # lower bounds for the first iteration
            if cnt < 1:
                if (
                    block_lower is not None
                    and block_upper is not None
                    and block_upper != block_lower
                ):
                    op_num = int(
                        (target_blocknum - block_lower)
                        / (block_upper - block_lower)
                        * (op_upper - op_lower)
                        + op_lower
                    )
                else:
                    op_num = op_lower
            else:
                # divide and conquer for the following iterations
                op_num = int((op_upper + op_lower) / 2)
                if op_upper == op_lower + 1:  # round up if we're close to target
                    op_num += 1

            # get block number for current op number estimation
            if op_num != last_op_num:
                block_num = self._get_blocknum_from_hist(op_num, min_index=min_index)
                while block_num is None and op_num < max_index:
                    op_num += 1
                    block_num = self._get_blocknum_from_hist(op_num, min_index=min_index)
                last_op_num = op_num

            # check if the required accuracy was reached
            if op_upper - op_lower <= stop_diff or op_upper == op_lower + 1:
                return op_num

            # set new upper/lower boundaries for next iteration
            if block_num is not None and block_num < target_blocknum:
                # current op number was too low -> search upwards
                op_lower = op_num
                block_lower = block_num
            else:
                # current op number was too high or matched the target block
                # -> search downwards
                op_upper = op_num
                block_upper = block_num
            cnt += 1

    def get_curation_reward(self, days: int = 7) -> float:
        """Returns the curation reward of the last `days` days

        :param int days: limit number of days to be included int the return value
        """
        stop = datetime.now(timezone.utc) - timedelta(days=days)
        reward_vests = Amount(
            0, self.blockchain.vest_token_symbol, blockchain_instance=self.blockchain
        )
        for reward in self.history_reverse(
            stop=stop, use_block_num=False, only_ops=["curation_reward"]
        ):
            reward_vests += Amount(reward["reward"], blockchain_instance=self.blockchain)
        return self.blockchain.vests_to_token_power(float(reward_vests))

    def curation_stats(self) -> dict[str, float]:
        """Returns the curation reward of the last 24h and 7d and the average
        of the last 7 days

        :returns: Account curation
        :rtype: dictionary

        Sample output:

        .. code-block:: js

            {
                '24hr': 0.0,
                '7d': 0.0,
                'avg': 0.0
            }

        """
        return {
            "24hr": self.get_curation_reward(days=1),
            "7d": self.get_curation_reward(days=7),
            "avg": self.get_curation_reward(days=7) / 7,
        }

    def _get_operation_filter(
        self, only_ops: list[str] | tuple = [], exclude_ops: list[str] | tuple = []
    ) -> tuple[int | None, int | None]:
        from nectarbase.operationids import operations

        operation_filter_low = 0
        operation_filter_high = 0
        if len(only_ops) == 0 and len(exclude_ops) == 0:
            return None, None
        if len(only_ops) > 0:
            for op in only_ops:
                op_id = operations[op]
                if op_id <= 64:
                    operation_filter_low += 2**op_id
                else:
                    operation_filter_high += 2 ** (op_id - 64 - 1)
        else:
            for op in operations:
                op_id = operations[op]
                if op_id <= 64:
                    operation_filter_low += 2**op_id
                else:
                    operation_filter_high += 2 ** (op_id - 64 - 1)
            for op in exclude_ops:
                op_id = operations[op]
                if op_id <= 64:
                    operation_filter_low -= 2**op_id
                else:
                    operation_filter_high -= 2 ** (op_id - 64 - 1)
        return operation_filter_low, operation_filter_high

    def get_account_history(
        self,
        index: int,
        limit: int,
        order: int = -1,
        start: int | datetime | date | time | None = None,
        stop: int | datetime | date | time | None = None,
        use_block_num: bool = True,
        only_ops: list[str] | tuple = [],
        exclude_ops: list[str] | tuple = [],
        raw_output: bool = False,
    ) -> Any:
        """
        Yield account history operations for a single account.

        Generates account history entries (one at a time) between a starting index and limit, optionally filtered
        and ordered. Each yielded item is either the raw RPC (index, event) tuple when raw_output is True,
        or an enriched dict containing operation fields plus metadata (account, type, index, _id).

        Parameters:
            index (int): starting index for history retrieval (passed to underlying fetch).
            limit (int): maximum number of entries to request from the node.
            order (int): 1 for chronological, -1 for reverse chronological (default -1).
            start (int | datetime | date | time | None): inclusive start boundary. Interpreted as a block number
                when use_block_num is True, otherwise as an operation index; a datetime/value restricts by timestamp.
            stop (int | datetime | date | time | None): inclusive stop boundary, interpreted like `start`.
            use_block_num (bool): when True, treat numeric start/stop as blockchain block numbers; otherwise as op indices.
            only_ops (list[str]): if non-empty, only yield operations whose type is in this list.
            exclude_ops (list[str]): skip operations whose type is in this list.
            raw_output (bool): when True yield the raw (index, event) tuple from the RPC; when False yield an enriched dict.

        Returns:
            generator: yields history entries as described above.

        Raises:
            ValueError: if `order` is not 1 or -1.
        """
        if order != -1 and order != 1:
            raise ValueError("order must be -1 or 1!")
        # self.blockchain.rpc.set_next_node_on_empty_reply(True)
        operation_filter_low = None
        operation_filter_high = None
        if self.blockchain.rpc.url == "https://api.hive.blog":
            operation_filter_low, operation_filter_high = self._get_operation_filter(
                only_ops=only_ops, exclude_ops=exclude_ops
            )
        try:
            txs = self._get_account_history(
                start=index,
                limit=limit,
                operation_filter_low=operation_filter_low,
                operation_filter_high=operation_filter_high,
            )
        except FilteredItemNotFound:
            txs = []
        if txs is None:
            return
        # Only call addTzInfo on date/time objects, not integers
        if start is not None and isinstance(start, (datetime, date, time)):
            start = addTzInfo(start)
        if stop is not None and isinstance(stop, (datetime, date, time)):
            stop = addTzInfo(stop)

        if order == -1:
            txs_list = reversed(txs)
        else:
            txs_list = txs
        for item in txs_list:
            item_index, event = item
            if start and isinstance(start, (datetime, date, time)):
                event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                timediff = start - event_time
                if timediff.total_seconds() * float(order) > 0:
                    continue
            elif start is not None and use_block_num:
                # When use_block_num=True, start should be a block number, but if it's a time string, convert it
                if isinstance(start, str):
                    # Convert time string to block number
                    from nectar.blockchain import Blockchain
                    from nectar.utils import parse_time

                    start_dt = parse_time(start)
                    blockchain = Blockchain(blockchain_instance=self.blockchain)
                    try:
                        start_block = blockchain.get_estimated_block_num(start_dt, accurate=True)
                        if order == 1 and event["block"] < start_block:
                            continue
                        elif order == -1 and event["block"] > start_block:
                            continue
                    except Exception:
                        # If conversion fails, skip this filter
                        pass
                else:
                    # start is an integer block number
                    if order == 1 and event["block"] < start:
                        continue
                    elif order == -1 and event["block"] > start:
                        continue
            elif start is not None and not use_block_num:
                # For non-block_num mode, start can be a datetime, time string, or integer
                if isinstance(start, str):
                    # Convert time string to datetime for comparison
                    from nectar.utils import parse_time

                    start_dt = parse_time(start)
                    event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = start_dt - event_time
                    if timediff.total_seconds() * float(order) > 0:
                        continue
                elif isinstance(start, (datetime, date, time)):
                    event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = start - event_time
                    if timediff.total_seconds() * float(order) > 0:
                        continue
                else:
                    # start is an integer (virtual operation count)
                    if order == 1 and item_index < start:
                        continue
                    elif order == -1 and item_index > start:
                        continue
            if stop is not None and isinstance(stop, (datetime, date, time)):
                event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                timediff = stop - event_time
                if timediff.total_seconds() * float(order) < 0:
                    return
            elif stop is not None and use_block_num:
                # When use_block_num=True, stop should be a block number, but if it's a time string, convert it
                if isinstance(stop, str):
                    # Convert time string to block number
                    from nectar.blockchain import Blockchain
                    from nectar.utils import parse_time

                    stop_dt = parse_time(stop)
                    blockchain = Blockchain(blockchain_instance=self.blockchain)
                    try:
                        stop_block = blockchain.get_estimated_block_num(stop_dt, accurate=True)
                        if order == 1 and event["block"] > stop_block:
                            return
                        elif order == -1 and event["block"] < stop_block:
                            return
                    except Exception:
                        # If conversion fails, skip this filter
                        pass
                else:
                    # stop is an integer block number
                    if order == 1 and event["block"] > stop:
                        return
                    elif order == -1 and event["block"] < stop:
                        return
            elif stop is not None and not use_block_num:
                # For non-block_num mode, stop can be a datetime, time string, or integer
                if isinstance(stop, str):
                    # Convert time string to datetime for comparison
                    from nectar.utils import parse_time

                    stop_dt = parse_time(stop)
                    event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = stop_dt - event_time
                    if timediff.total_seconds() * float(order) < 0:
                        return
                elif isinstance(stop, (datetime, date, time)):
                    event_time = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = stop - event_time
                    if timediff.total_seconds() * float(order) < 0:
                        return
                else:
                    # stop is an integer (virtual operation count)
                    if order == 1 and item_index > stop:
                        return
                    elif order == -1 and item_index < stop:
                        return

            if isinstance(event["op"], list):
                op_type, op = event["op"]
            else:
                op_type = event["op"]["type"]
                if len(op_type) > 10 and op_type[len(op_type) - 10 :] == "_operation":
                    op_type = op_type[:-10]
                op = event["op"]["value"]
            block_props = remove_from_dict(event, keys=["op"], keep_keys=False)

            def construct_op(account_name: str) -> dict[str, Any]:
                # verbatim output from RPC node
                """
                Construct a normalized, immutable operation dictionary for an account.

                If `raw_output` is true (from outer scope), returns the original RPC `item` unchanged. Otherwise returns a copy of `op` merged with `block_props` and the following fields:
                - "account": the provided account_name
                - "type": operation type (from outer scope `op_type`)
                - "_id": a deterministic hash computed via Blockchain.hash_op(immutable)
                - "index": the operation index (from outer scope `item_index`)

                Parameters:
                    account_name (str): Account name to attach to the constructed operation.

                Returns:
                    dict: Either the raw RPC item (if `raw_output`) or an immutable operation dict augmented with account, type, _id, and index.
                """
                if raw_output:
                    return item

                # index can change during reindexing in
                # future hard-forks. Thus we cannot take it for granted.
                immutable = op.copy()
                immutable.update(block_props)
                immutable.update(
                    {
                        "account": account_name,
                        "type": op_type,
                    }
                )
                from nectar.blockchain import Blockchain

                _id = Blockchain.hash_op(immutable)
                immutable.update(
                    {
                        "_id": _id,
                        "index": item_index,
                    }
                )
                return immutable

            if exclude_ops and op_type in exclude_ops:
                continue
            if not only_ops or op_type in only_ops:
                yield construct_op(self["name"])

    def history(
        self,
        start=None,
        stop=None,
        use_block_num: bool = True,
        only_ops: list[str] | tuple = [],
        exclude_ops: list[str] | tuple = [],
        batch_size: int = 1000,
        raw_output: bool = False,
    ):
        """Returns a generator for individual account transactions. The
        earliest operation will be first. This call can be used in a
        ``for`` loop.

        :param start: start number/date of transactions to return (*optional*)
        :type start: int, datetime
        :param stop: stop number/date of transactions to return (*optional*)
        :type stop: int, datetime
        :param bool use_block_num: if true, start and stop are block numbers,
            otherwise virtual OP count numbers.
        :param array only_ops: Limit generator by these
            operations (*optional*)
        :param array exclude_ops: Exclude thse operations from
            generator (*optional*)
        :param int batch_size: internal api call batch size (*optional*)
        :param bool raw_output: if False, the output is a dict, which
            includes all values. Otherwise, the output is list.

        .. note::
            only_ops and exclude_ops takes an array of strings:
            The full list of operation ID's can be found in
            nectarbase.operationids.ops.
            Example: ['transfer', 'vote']

        .. testsetup::

            from nectar.account import Account
            from datetime import datetime

        .. testcode::

            acc = Account("gtg")
            max_op_count = acc.virtual_op_count()
            # Returns the 100 latest operations
            acc_op = []
            for h in acc.history(start=max_op_count - 99, stop=max_op_count, use_block_num=False):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            100

        .. testcode::

            acc = Account("test")
            max_block = 21990141
            # Returns the account operation inside the last 100 block. This can be empty.
            acc_op = []
            for h in acc.history(start=max_block - 99, stop=max_block, use_block_num=True):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            0

        .. testcode::

            acc = Account("test")
            start_time = datetime(2018, 3, 1, 0, 0, 0)
            stop_time = datetime(2018, 3, 2, 0, 0, 0)
            # Returns the account operation from 1.4.2018 back to 1.3.2018
            acc_op = []
            for h in acc.history(start=start_time, stop=stop_time):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            0

        """
        _limit = batch_size
        max_index = self.virtual_op_count()
        if not max_index:
            return
        # Only call addTzInfo on date/time objects, not integers
        if start is not None and isinstance(start, (datetime, date, time)):
            start = addTzInfo(start)
        if stop is not None and isinstance(stop, (datetime, date, time)):
            stop = addTzInfo(stop)
        if (
            start is not None
            and not use_block_num
            and not isinstance(start, (datetime, date, time))
            and not isinstance(start, str)
        ):
            # start is an integer (virtual operation count)
            start_index = start
        elif start is not None and max_index > batch_size:
            created, min_index = self._get_first_blocknum()
            op_est = self.estimate_virtual_op_num(start, stop_diff=1, min_index=min_index)
            if op_est < min_index:
                op_est = min_index
            est_diff = 0
            if isinstance(start, (datetime, date, time, str)):
                # start is a datetime or formatted time string
                if isinstance(start, str):
                    # Parse the time string to datetime
                    from nectar.utils import parse_time

                    start_dt = parse_time(start)
                else:
                    start_dt = start
                for h in self.get_account_history(op_est, 0):
                    block_date = datetime.strptime(h["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                while op_est > est_diff + batch_size and block_date > start_dt:
                    est_diff += batch_size
                    if op_est - est_diff < 0:
                        est_diff = op_est
                    for h in self.get_account_history(op_est - est_diff, 0):
                        block_date = datetime.strptime(h["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
            elif not isinstance(start, (datetime, date, time, str)):
                for h in self.get_account_history(op_est, 0):
                    block_num = h["block"]
                while op_est > est_diff + batch_size and block_num > start:
                    est_diff += batch_size
                    if op_est - est_diff < 0:
                        est_diff = op_est
                    for h in self.get_account_history(op_est - est_diff, 0):
                        block_num = h["block"]
            start_index = op_est - est_diff
        else:
            start_index = 0

        if stop is not None and not use_block_num and not isinstance(stop, (datetime, date, time)):
            # Check if stop is a formatted time string
            if isinstance(stop, str):
                try:
                    # Try to parse it as a time string - if successful, it should be treated as a datetime
                    from nectar.utils import parse_time

                    parse_time(stop)
                    # If parsing succeeds, this is a time string, not an integer, so skip the integer arithmetic
                    pass
                except (ValueError, TypeError):
                    # If parsing fails, treat it as an integer
                    if start_index + stop < _limit:
                        _limit = stop
            else:
                # It's an integer, do the arithmetic
                if start_index + stop < _limit:
                    _limit = stop

        first = start_index + _limit - 1
        if first > max_index:
            _limit = max_index - start_index
            first = start_index + _limit - 1
        elif first < _limit and self.blockchain.rpc.url == "https://api.hive.blog":
            first = _limit - 1
        elif first < _limit and self.blockchain.rpc.url != "https://api.hive.blog":
            first = _limit
        last_round = False

        if _limit < 0:
            return
        last_item_index = -1

        if self.blockchain.rpc.url == "https://api.hive.blog" and (
            len(only_ops) > 0 or len(exclude_ops) > 0
        ):
            operation_filter = True
        else:
            operation_filter = False

        while True:
            # RPC call
            if first < _limit - 1 and self.blockchain.rpc.url == "https://api.hive.blog":
                first = _limit - 1
            elif first < _limit and self.blockchain.rpc.url != "https://api.hive.blog":
                first = _limit
            batch_count = 0
            for item in self.get_account_history(
                first,
                _limit,
                start=None,
                stop=None,
                order=1,
                only_ops=only_ops,
                exclude_ops=exclude_ops,
                raw_output=raw_output,
            ):
                batch_count += 1
                if raw_output:
                    item_index, event = item
                    op_type, op = event["op"]
                    timestamp = event["timestamp"]
                    block_num = event["block"]
                else:
                    item_index = item["index"]
                    op_type = item["type"]
                    timestamp = item["timestamp"]
                    block_num = item["block"]
                if start is not None and isinstance(start, (datetime, date, time)):
                    event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = start - event_time
                    if timediff.total_seconds() > 0:
                        continue
                elif start is not None and use_block_num and block_num < start:
                    continue
                elif start is not None and not use_block_num:
                    # For non-block_num mode, start can be a datetime, time string, or integer
                    if isinstance(start, str):
                        # Convert time string to datetime for comparison
                        from nectar.utils import parse_time

                        start_dt = parse_time(start)
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = start_dt - event_time
                        if timediff.total_seconds() > 0:
                            continue
                    elif isinstance(start, (datetime, date, time)):
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = start - event_time
                        if timediff.total_seconds() > 0:
                            continue
                    else:
                        # start is an integer (virtual operation count)
                        if item_index < start:
                            continue
                elif last_item_index >= item_index:
                    continue
                if stop is not None and isinstance(stop, (datetime, date, time)):
                    event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = stop - event_time
                    if timediff.total_seconds() < 0:
                        first = max_index + _limit
                        return
                elif stop is not None and use_block_num and block_num > stop:
                    return
                elif stop is not None and not use_block_num:
                    # For non-block_num mode, stop can be a datetime, time string, or integer
                    if isinstance(stop, str):
                        # Convert time string to datetime for comparison
                        from nectar.utils import parse_time

                        stop_dt = parse_time(stop)
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = stop_dt - event_time
                        if timediff.total_seconds() < 0:
                            return
                    elif isinstance(stop, (datetime, date, time)):
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = stop - event_time
                        if timediff.total_seconds() < 0:
                            return
                    else:
                        # stop is an integer (virtual operation count)
                        if item_index > stop:
                            return
                if operation_filter:
                    yield item
                else:
                    if exclude_ops and op_type in exclude_ops:
                        continue
                    if not only_ops or op_type in only_ops:
                        yield item
                last_item_index = item_index
            if first < max_index and first + _limit >= max_index and not last_round:
                _limit = max_index - first
                first = max_index
                last_round = True
            else:
                if (
                    operation_filter
                    and batch_count < _limit
                    and first + 2000 < max_index
                    and _limit == 1000
                ):
                    first += 2000
                else:
                    first += _limit
                if (
                    stop is not None
                    and not use_block_num
                    and isinstance(stop, int)
                    and first >= stop + _limit + 1
                ):
                    break
                elif first > max_index or last_round:
                    break

    def history_reverse(
        self,
        start: int | datetime | date | time | None = None,
        stop: int | datetime | date | time | None = None,
        use_block_num: bool = True,
        only_ops: list[str] | tuple = [],
        exclude_ops: list[str] | tuple = [],
        batch_size: int = 1000,
        raw_output: bool = False,
    ) -> Any:
        """Returns a generator for individual account transactions. The
        latest operation will be first. This call can be used in a
        ``for`` loop.

        :param start: start number/date of transactions to
            return. If negative the virtual_op_count is added. (*optional*)
        :type start: int, datetime
        :param stop: stop number/date of transactions to
            return. If negative the virtual_op_count is added. (*optional*)
        :type stop: int, datetime
        :param bool use_block_num: if true, start and stop are block numbers,
            otherwise virtual OP count numbers.
        :param array only_ops: Limit generator by these
            operations (*optional*)
        :param array exclude_ops: Exclude thse operations from
            generator (*optional*)
        :param int batch_size: internal api call batch size (*optional*)
        :param bool raw_output: if False, the output is a dict, which
            includes all values. Otherwise, the output is list.

        .. note::
            only_ops and exclude_ops takes an array of strings:
            The full list of operation ID's can be found in
            nectarbase.operationids.ops.
            Example: ['transfer', 'vote']

        .. testsetup::

            from nectar.account import Account
            from datetime import datetime

        .. testcode::

            acc = Account("gtg")
            max_op_count = acc.virtual_op_count()
            # Returns the 100 latest operations
            acc_op = []
            for h in acc.history_reverse(start=max_op_count, stop=max_op_count - 99, use_block_num=False):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            100

        .. testcode::

            max_block = 21990141
            acc = Account("test")
            # Returns the account operation inside the last 100 block. This can be empty.
            acc_op = []
            for h in acc.history_reverse(start=max_block, stop=max_block-100, use_block_num=True):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            0

        .. testcode::

            acc = Account("test")
            start_time = datetime(2018, 4, 1, 0, 0, 0)
            stop_time = datetime(2018, 3, 1, 0, 0, 0)
            # Returns the account operation from 1.4.2018 back to 1.3.2018
            acc_op = []
            for h in acc.history_reverse(start=start_time, stop=stop_time):
                acc_op.append(h)
            len(acc_op)

        .. testoutput::

            0

        """
        _limit = batch_size
        first = self.virtual_op_count()
        if start is not None and isinstance(start, (datetime, date, time)):
            start = addTzInfo(start)
        if stop is not None and isinstance(stop, (datetime, date, time)):
            stop = addTzInfo(stop)
        if not first or not batch_size:
            return
        if start is not None and isinstance(start, int) and start < 0 and not use_block_num:
            start += first
        elif start is not None and isinstance(start, int) and not use_block_num:
            first = start
        elif start is not None and first > batch_size:
            created, min_index = self._get_first_blocknum()
            op_est = self.estimate_virtual_op_num(start, stop_diff=1, min_index=min_index)
            est_diff = 0
            if op_est < min_index:
                op_est = min_index
            if isinstance(start, (datetime, date, time, str)):
                # start is a datetime or formatted time string
                if isinstance(start, str):
                    # Parse the time string to datetime
                    from nectar.utils import parse_time

                    start_dt = parse_time(start)
                else:
                    start_dt = start
                for h in self.get_account_history(op_est, 0):
                    block_date = datetime.strptime(h["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                while op_est + est_diff + batch_size < first and block_date < start_dt:
                    est_diff += batch_size
                    if op_est + est_diff > first:
                        est_diff = first - op_est
                    for h in self.get_account_history(op_est + est_diff, 0):
                        block_date = datetime.strptime(h["timestamp"], "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
            elif not isinstance(start, (datetime, date, time, str)):
                for h in self.get_account_history(op_est, 0):
                    block_num = h["block"]
                while op_est + est_diff + batch_size < first and block_num < start:
                    est_diff += batch_size
                    if op_est + est_diff > first:
                        est_diff = first - op_est
                    for h in self.get_account_history(op_est + est_diff, 0):
                        block_num = h["block"]
            first = op_est + est_diff
        if stop is not None and isinstance(stop, int) and stop < 0 and not use_block_num:
            stop += first

        if self.blockchain.rpc.url == "https://api.hive.blog" and (
            len(only_ops) > 0 or len(exclude_ops) > 0
        ):
            operation_filter = True
        else:
            operation_filter = False

        last_item_index = first + 1
        while True:
            # RPC call
            if first - _limit < 0 and self.blockchain.rpc.url == "https://api.hive.blog":
                _limit = first + 1
            elif first - _limit < 0 and self.blockchain.rpc.url != "https://api.hive.blog":
                _limit = first
            batch_count = 0
            for item in self.get_account_history(
                first,
                _limit,
                start=None,
                stop=None,
                order=-1,
                only_ops=only_ops,
                exclude_ops=exclude_ops,
                raw_output=raw_output,
            ):
                batch_count += 1
                if raw_output:
                    item_index, event = item
                    op_type, op = event["op"]
                    timestamp = event["timestamp"]
                    block_num = event["block"]
                else:
                    item_index = item["index"]
                    op_type = item["type"]
                    timestamp = item["timestamp"]
                    block_num = item["block"]
                if start is not None and isinstance(start, (datetime, date, time)):
                    event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = start - event_time
                    if timediff.total_seconds() < 0:
                        continue
                elif start is not None and use_block_num and block_num > start:
                    continue
                elif start is not None and not use_block_num:
                    # For non-block_num mode, start can be a datetime, time string, or integer
                    if isinstance(start, str):
                        # Convert time string to datetime for comparison
                        from nectar.utils import parse_time

                        start_dt = parse_time(start)
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = start_dt - event_time
                        if timediff.total_seconds() < 0:
                            continue
                    elif isinstance(start, (datetime, date, time)):
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = start - event_time
                        if timediff.total_seconds() < 0:
                            continue
                    else:
                        # start is an integer (virtual operation count)
                        if item_index > start:
                            continue
                elif last_item_index <= item_index:
                    continue
                if stop is not None and isinstance(stop, (datetime, date, time)):
                    event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    timediff = stop - event_time
                    if timediff.total_seconds() > 0:
                        first = 0
                        return
                elif stop is not None and use_block_num and block_num < stop:
                    first = 0
                    return
                elif stop is not None and not use_block_num:
                    # For non-block_num mode, stop can be a datetime, time string, or integer
                    if isinstance(stop, str):
                        # Convert time string to datetime for comparison
                        from nectar.utils import parse_time

                        stop_dt = parse_time(stop)
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = stop_dt - event_time
                        if timediff.total_seconds() > 0:
                            first = 0
                            return
                    elif isinstance(stop, (datetime, date, time)):
                        event_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        timediff = stop - event_time
                        if timediff.total_seconds() > 0:
                            first = 0
                            return
                    else:
                        # stop is an integer (virtual operation count)
                        if item_index < stop:
                            first = 0
                            return
                if operation_filter:
                    yield item
                else:
                    if exclude_ops and op_type in exclude_ops:
                        continue
                    if not only_ops or op_type in only_ops:
                        yield item
                last_item_index = item_index
            if operation_filter and batch_count < _limit and _limit == 1000:
                first -= 2000
            else:
                first -= _limit
            if first < 1:
                break

    def mute(self, mute: str, account: str | None = None) -> dict[str, Any]:
        """Mute another account

        :param str mute: Mute this account
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        return self.follow(mute, what=["ignore"], account=account)

    def unfollow(self, unfollow: str, account: str | None = None) -> dict[str, Any]:
        """Unfollow/Unmute another account's blog

        :param str unfollow: Unfollow/Unmute this account
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        return self.follow(unfollow, what=[], account=account)

    def follow(
        self,
        other: str | list[str],
        what: list[str] = ["blog"],
        account: str | None = None,
    ) -> dict[str, Any]:
        """Follow/Unfollow/Mute/Unmute another account's blog

        .. note:: what can be one of the following on HIVE:
        blog, ignore, blacklist, unblacklist, follow_blacklist,
        unfollow_blacklist, follow_muted, unfollow_muted

        :param str/list other: Follow this account / accounts (only hive)
        :param list what: List of states to follow.
            ``['blog']`` means to follow ``other``,
            ``[]`` means to unfollow/unmute ``other``,
            ``['ignore']`` means to ignore ``other``,
            (defaults to ``['blog']``)
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        if account is None:
            account = self["name"]
        account = extract_account_name(account)
        if not account:
            raise ValueError("You need to provide an account")
        if not other:
            raise ValueError("You need to provide an account to follow/unfollow/mute/unmute")
        if isinstance(other, str) and other.find(",") > 0:
            other = other.split(",")
        json_body = ["follow", {"follower": account, "following": other, "what": what}]
        return self.blockchain.custom_json("follow", json_body, required_posting_auths=[account])

    def update_account_profile(
        self, profile: dict[str, Any], account: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Update an account's profile in json_metadata

        :param dict profile: The new profile to use
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        Sample profile structure:

        .. code-block:: js

            {
                'name': 'TheCrazyGM',
                'about': 'hive-nectar Developer',
                'location': 'United States',
                'profile_image': 'https://.jpg',
                'cover_image': 'https://.jpg',
                'website': 'https://github.com/thecrazygm'
            }

        .. code-block:: python

            from nectar.account import Account
            account = Account("test")
            profile = account.profile
            profile["about"] = "test account"
            account.update_account_profile(profile)

        """
        if account is None:
            account_name = self["name"]
        else:
            account_obj = Account(account, blockchain_instance=self.blockchain)
            account_name = account_obj["name"]  # noqa: F841

        if not isinstance(profile, dict):
            raise ValueError("Profile must be a dict type!")

        if self["json_metadata"] == "":
            metadata = {}
        else:
            metadata = json.loads(self["json_metadata"])
        metadata["profile"] = profile
        return self.update_account_metadata(metadata)

    def update_account_metadata(
        self,
        metadata: dict[str, Any] | str,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Update an account's profile in json_metadata

        :param dict metadata: The new metadata to use
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)
        elif not isinstance(metadata, str):
            raise ValueError("Profile must be a dict or string!")
        op = operations.Account_update(
            **{
                "account": account["name"],
                "memo_key": account["memo_key"],
                "json_metadata": metadata,
                "prefix": self.blockchain.prefix,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def update_account_jsonmetadata(self, metadata, account=None, **kwargs) -> dict:
        """Update an account's profile in json_metadata using the posting key

        :param dict metadata: The new metadata to use
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        # We need to preserve the existing active json_metadata
        if "json_metadata" not in account:
            account.refresh()
        current_active_meta = account.get("json_metadata", "")

        if isinstance(metadata, dict):
            # Ensure version: 2 is present for profile updates
            if "profile" in metadata and isinstance(metadata["profile"], dict):
                if "version" not in metadata["profile"]:
                    metadata["profile"]["version"] = 2
            metadata = json.dumps(metadata)
        elif not isinstance(metadata, str):
            raise ValueError("Profile must be a dict or string!")

        op = operations.Account_update2(
            **{
                "account": account["name"],
                "json_metadata": current_active_meta,
                "posting_json_metadata": metadata,
                "prefix": self.blockchain.prefix,
            }
        )
        return self.blockchain.finalizeOp(op, account, "posting", **kwargs)

    # -------------------------------------------------------------------------
    #  Approval and Disapproval of witnesses
    # -------------------------------------------------------------------------
    def approvewitness(
        self, witness: str, account: str | None = None, approve: bool = True, **kwargs
    ) -> dict[str, Any]:
        """Approve a witness

        :param list witness: list of Witness name or id
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)

        """
        if account is None:
            account_name = self["name"]
        else:
            account_obj = Account(account, blockchain_instance=self.blockchain)
            account_name = account_obj["name"]

        # if not isinstance(witnesses, (list, set, tuple)):
        #     witnesses = {witnesses}

        # for witness in witnesses:
        #     witness = Witness(witness, blockchain_instance=self)

        op = operations.Account_witness_vote(
            **{
                "account": account_name,
                "witness": witness,
                "approve": approve,
                "prefix": self.blockchain.prefix,
            }
        )
        return self.blockchain.finalizeOp(op, account_name, "active", **kwargs)

    def disapprovewitness(
        self, witness: str, account: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Disapprove a witness

        :param list witness: list of Witness name or id
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)
        """
        return self.approvewitness(witness=witness, account=account, approve=False)

    def setproxy(self, proxy: str = "", account: str | Account | None = None) -> dict[str, Any]:
        """Set the witness and proposal system proxy of an account

        :param proxy: The account to set the proxy to (Leave empty for removing the proxy)
        :type proxy: str or Account
        :param account: The account the proxy should be set for
        :type account: str or Account
        """
        if account is None:
            account = self
        elif isinstance(account, Account):
            pass
        else:
            account = Account(account)

        if isinstance(proxy, str):
            proxy_name = proxy
        else:
            proxy_name = proxy["name"]
        op = operations.Account_witness_proxy(**{"account": account.name, "proxy": proxy_name})
        return self.blockchain.finalizeOp(op, account, "active")

    def update_memo_key(
        self, key: str, account: str | Account | None = None, **kwargs
    ) -> dict[str, Any]:
        """Update an account's memo public key

        This method does **not** add any private keys to your
        wallet but merely changes the memo public key.

        :param str key: New memo public key
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        PublicKey(key, prefix=self.blockchain.prefix)

        account["memo_key"] = key
        op = operations.Account_update(
            **{
                "account": account["name"],
                "memo_key": account["memo_key"],
                "json_metadata": account["json_metadata"],
                "prefix": self.blockchain.prefix,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def update_account_keys(
        self, new_password: str, account: str | Account | None = None, **kwargs
    ) -> dict[str, Any]:
        """Updates all account keys

        This method does **not** add any private keys to your
        wallet but merely changes the public keys.

        :param str new_password: is used to derive the owner, active,
            posting and memo key
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        key_auths = {}
        for role in ["owner", "active", "posting", "memo"]:
            pk = PasswordKey(account["name"], new_password, role=role)
            key_auths[role] = format(pk.get_public_key(), self.blockchain.prefix)

        op = operations.Account_update(
            **{
                "account": account["name"],
                "owner": {
                    "account_auths": [],
                    "key_auths": [[key_auths["owner"], 1]],
                    "address_auths": [],
                    "weight_threshold": 1,
                },
                "active": {
                    "account_auths": [],
                    "key_auths": [[key_auths["active"], 1]],
                    "address_auths": [],
                    "weight_threshold": 1,
                },
                "posting": {
                    "account_auths": account["posting"]["account_auths"],
                    "key_auths": [[key_auths["posting"], 1]],
                    "address_auths": [],
                    "weight_threshold": 1,
                },
                "memo_key": key_auths["memo"],
                "json_metadata": account["json_metadata"],
                "prefix": self.blockchain.prefix,
            }
        )

        return self.blockchain.finalizeOp(op, account, "owner", **kwargs)

    def change_recovery_account(
        self, new_recovery_account: str, account: str | Account | None = None, **kwargs
    ) -> dict[str, Any]:
        """Request a change of the recovery account.

        .. note:: It takes 30 days until the change applies. Another
            request within this time restarts the 30 day period.
            Setting the current recovery account again cancels any
            pending change request.

        :param str new_recovery_account: account name of the new
            recovery account
        :param str account: (optional) the account to change the
            recovery account for (defaults to ``default_account``)

        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        # Account() lookup to make sure the new account is valid
        new_rec_acc = Account(new_recovery_account, blockchain_instance=self.blockchain)
        op = operations.Change_recovery_account(
            **{
                "account_to_recover": account["name"],
                "new_recovery_account": new_rec_acc["name"],
                "extensions": [],
            }
        )
        return self.blockchain.finalizeOp(op, account, "owner", **kwargs)

    # -------------------------------------------------------------------------
    # Simple Transfer
    # -------------------------------------------------------------------------
    def transfer(
        self,
        to: str | Account,
        amount: int | float | str | Amount,
        asset: str,
        memo: str = "",
        skip_account_check: bool = False,
        account=None,
        **kwargs,
    ) -> dict:
        """
        Transfer an asset from this account to another account.

        Creates and broadcasts a Transfer operation using the account's active authority.

        Parameters:
            to (str | Account): Recipient account name or Account object.
            amount (int | float | str | Amount): Amount to transfer; will be normalized to an Amount with the given asset.
            asset (str): Asset symbol (e.g., "HIVE", "HBD").
            memo (str, optional): Optional memo; if it starts with '#', the remainder is encrypted with the sender's and receiver's memo keys.
            skip_account_check (bool, optional): If True, skip resolving the `to` and `account` parameters to Account objects (faster for repeated transfers).
            account (str | Account, optional): Source account name or Account object; defaults to this Account instance.
            **kwargs: Passed through to finalizeOp (e.g., broadcast options).

        Returns:
            dict: Result from blockchain.finalizeOp (signed/broadcast transaction response).
        """

        if account is None:
            account = self
        elif not skip_account_check:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if not skip_account_check:
            to = Account(to, blockchain_instance=self.blockchain)

        to_name = extract_account_name(to)
        account_name = extract_account_name(account)
        if memo and memo[0] == "#":
            from .memo import Memo

            memoObj = Memo(from_account=account, to_account=to, blockchain_instance=self.blockchain)
            encrypted_memo = memoObj.encrypt(memo[1:])
            memo = encrypted_memo["message"] if encrypted_memo else ""

        op = operations.Transfer(
            **{
                "amount": amount,
                "to": to_name,
                "memo": memo,
                "from": account_name,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    # -------------------------------------------------------------------------------
    # Recurring Transfer added in hf25
    # -------------------------------------------------------------------------------
    def recurring_transfer(
        self,
        to: str | Account,
        amount: int | float | str | Amount,
        asset: str,
        recurrence: int,
        executions: int,
        memo: str = "",
        skip_account_check: bool = False,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Schedule a recurring transfer of a token from this account to another.

        Schedules a recurring on-chain transfer operation that will execute `executions` times every `recurrence` hours.

        Parameters:
            to (str | Account): Recipient account name or Account object.
            amount (int | float | str | Amount): Amount to transfer each occurrence. Must match the asset's precision (commonly 3 decimals).
            asset (str): Asset symbol (e.g., "HIVE", "HBD").
            recurrence (int): Interval between executions in hours.
            executions (int): Number of times the transfer will be executed.
            memo (str, optional): Memo for the transfer. If it starts with '#', the remainder is encrypted to the recipient.
            skip_account_check (bool, optional): If True, skip resolving/checking Account objects for `to` and `account` (faster when making many calls).
            account (str | Account, optional): Source account name or Account object; defaults to this Account.

        Returns:
            dict: The broadcasted transaction result returned by finalizeOp.
        """

        if account is None:
            account = self
        elif not skip_account_check:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if not skip_account_check:
            to = Account(to, blockchain_instance=self.blockchain)

        to_name = extract_account_name(to)
        account_name = extract_account_name(account)
        if memo and memo[0] == "#":
            from .memo import Memo

            memoObj = Memo(from_account=account, to_account=to, blockchain_instance=self.blockchain)
            encrypted_memo = memoObj.encrypt(memo[1:])
            memo = encrypted_memo["message"] if encrypted_memo else ""

        op = operations.Recurring_transfer(
            **{
                "amount": amount,
                "to": to_name,
                "memo": memo,
                "from": account_name,
                "recurrence": recurrence,
                "executions": executions,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def transfer_to_vesting(
        self,
        amount: int | float | str | Amount,
        to=None,
        account=None,
        skip_account_check: bool = False,
        **kwargs,
    ) -> dict:
        """
        Power up HIVE by converting liquid HIVE into vesting shares (VESTS).

        Performs a Transfer_to_vesting operation from the source account to the recipient (defaults to the account itself). The `amount` is normalized to the chain token symbol before broadcasting. Use `skip_account_check=True` to avoid resolving/validating Account objects for `to` or `account` when sending many transfers in a loop (faster but skips existence checks).

        Parameters:
            amount: Amount to transfer; accepts numeric, string, or Amount-like inputs and will be normalized to the blockchain token symbol.
            to (str|Account, optional): Recipient account name or Account object. Defaults to the calling account.
            account (str|Account, optional): Source account name or Account object. If omitted, the caller account is used.
            skip_account_check (bool, optional): If True, do not resolve/validate account names to Account objects (speeds up bulk transfers).

        Returns:
            The result of finalizeOp (broadcast/transaction result) for the Transfer_to_vesting operation.
        """
        if account is None:
            account = self
        elif not skip_account_check:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = self._check_amount(amount, self.blockchain.token_symbol)
        if to is None and skip_account_check:
            to = self["name"]  # powerup on the same account
        elif to is None:
            to = self
        if not skip_account_check:
            to = Account(to, blockchain_instance=self.blockchain)
        to_name = extract_account_name(to)
        account_name = extract_account_name(account)

        op = operations.Transfer_to_vesting(
            **{
                "from": account_name,
                "to": to_name,
                "amount": amount,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def convert(
        self,
        amount: int | float | str | Amount,
        account: str | Account | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Convert HBD to HIVE (takes ~3.5 days to settle).

        Parameters:
            amount: HBD amount to convert — accepts numeric, string, or Amount-compatible input; will be normalized to the chain's backed token symbol.
            account (str | Account, optional): Source account performing the conversion. If omitted, uses this account.
            request_id (int | str, optional): Numeric identifier for the conversion request. If omitted, a random request id is generated.

        Returns:
            The result of broadcasting the Convert operation (as returned by blockchain.finalizeOp).
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = self._check_amount(amount, self.blockchain.backed_token_symbol)
        if request_id:
            request_id = int(request_id)
        else:
            request_id = random.getrandbits(32)
        op = operations.Convert(
            **{
                "owner": account["name"],
                "requestid": request_id,
                "amount": amount,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )

        return self.blockchain.finalizeOp(op, account, "active")

    # Added to differentiate and match the addition of the HF25 convert operation
    def collateralized_convert(
        self,
        amount: int | float | str | Amount,
        account: str | Account | None = None,
        request_id: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Convert HBD to HIVE using the HF25 collateralized convert operation and broadcast the resulting transaction.

        This builds a Collateralized_convert operation for the specified HBD amount and finalizes it with the account's active authority. If `account` is omitted, the method uses the current Account object. If `request_id` is not provided, a random 32-bit id is generated.

        Parameters:
            amount: Amount, str, int, or float
                Amount of HBD to convert (symbol must match the chain's backed token symbol).
            account: str or Account, optional
                Source account name or Account instance; defaults to the calling account.
            request_id: int, optional
                Numeric identifier for the conversion request; if omitted a random id is used.

        Returns:
            dict
                Result of finalizeOp (the broadcasted operation response).
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = self._check_amount(amount, self.blockchain.backed_token_symbol)
        if request_id:
            request_id = int(request_id)
        else:
            request_id = random.getrandbits(32)
        op = operations.Collateralized_convert(
            **{
                "owner": account["name"],
                "requestid": request_id,
                "amount": amount,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )

        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def transfer_to_savings(
        self,
        amount: int | float | str | Amount,
        asset: str,
        memo: str,
        to: str | Account | None = None,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Transfer HBD or HIVE from an account into its savings balance (or into another account's savings) and broadcast the transfer_to_savings operation.

        Parameters:
            amount (float | str | Amount): Amount to transfer; may be numeric, string, or an Amount instance.
            asset (str): Asset symbol, must be the chain token or its backed token (e.g. "HIVE" or "HBD").
            memo (str): Memo to include with the transfer (may be empty).
            to (str | Account, optional): Destination account name or Account whose savings will receive the funds.
                If omitted, the source account's own savings is used.
            account (str | Account, optional): Source account name or Account performing the transfer.
                If omitted, `self` is used.
            **kwargs: Additional keyword arguments passed to the underlying finalizeOp call.

        Returns:
            dict: Result of finalizeOp (the broadcast/transaction result).

        Raises:
            AssertionError: If `asset` is not one of the allowed symbols.
        """
        if asset not in [
            self.blockchain.token_symbol,
            self.blockchain.backed_token_symbol,
        ]:
            raise AssertionError()

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if to is None:
            to = account  # move to savings on same account
        else:
            to = Account(to, blockchain_instance=self.blockchain)
        op = operations.Transfer_to_savings(
            **{
                "from": account["name"],
                "to": to["name"],
                "amount": amount,
                "memo": memo,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def transfer_from_savings(
        self,
        amount: int | float | str | Amount,
        asset: str,
        memo: str,
        request_id: int | None = None,
        to: str | Account | None = None,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Withdraw an amount from the account's savings into a liquid balance (HIVE or HBD).

        Creates and broadcasts a `transfer_from_savings` operation. If `request_id` is not
        provided a random 32-bit id will be generated. If `account` is omitted the
        operation will be created for the current account; if `to` is omitted the funds
        are transferred back to the same account.

        Parameters:
            amount (float|str|Amount): Amount to withdraw.
            asset (str): Symbol of the asset to withdraw, must be the chain token or its backed token (e.g., "HIVE" or "HBD").
            memo (str): Memo for the transfer (may be empty).
            request_id (int, optional): Identifier for this withdrawal request; used to cancel or track the withdrawal. If omitted one is generated.
            to (str|Account, optional): Destination account name or Account; defaults to the source account.
            account (str|Account, optional): Source account name or Account; defaults to the current account.

        Returns:
            dict: Result of finalizeOp / broadcast (operation confirmation).

        Raises:
            AssertionError: If `asset` is not a supported token symbol for this chain.
        """
        if asset not in [
            self.blockchain.token_symbol,
            self.blockchain.backed_token_symbol,
        ]:
            raise AssertionError()

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        if to is None:
            to = account  # move to savings on same account
        else:
            to = Account(to, blockchain_instance=self.blockchain)
        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if request_id:
            request_id = int(request_id)
        else:
            request_id = random.getrandbits(32)

        op = operations.Transfer_from_savings(
            **{
                "from": account["name"],
                "request_id": request_id,
                "to": to["name"],
                "amount": amount,
                "memo": memo,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def cancel_transfer_from_savings(
        self, request_id: int, account: str | Account | None = None, **kwargs
    ) -> dict[str, Any]:
        """Cancel a withdrawal from 'savings' account.

        :param str request_id: Identifier for tracking or cancelling
            the withdrawal
        :param str account: (optional) the source account for the transfer
            if not ``default_account``

        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        op = operations.Cancel_transfer_from_savings(
            **{
                "from": account["name"],
                "request_id": request_id,
                "prefix": self.blockchain.prefix,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def _check_amount(self, amount: int | float | str | Amount, symbol: str) -> Amount:
        if isinstance(amount, (float, int)):
            amount = Amount(amount, symbol, blockchain_instance=self.blockchain)
        elif isinstance(amount, str) and amount.replace(".", "", 1).replace(",", "", 1).isdigit():
            amount = Amount(float(amount), symbol, blockchain_instance=self.blockchain)
        else:
            amount = Amount(amount, blockchain_instance=self.blockchain)
        if not amount["symbol"] == symbol:
            raise AssertionError()
        return amount

    def claim_reward_balance(
        self,
        reward_hive: int | float | str | Amount = 0,
        reward_hbd: int | float | str | Amount = 0,
        reward_vests: int | float | str | Amount = 0,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Claim the account's pending reward balances (HIVE, HBD, and/or VESTS).

        If all reward amounts are left at their default (0), this will claim all outstanding rewards for the target account. Otherwise only the nonzero amounts will be claimed.

        Parameters:
            reward_hive (str|float|Amount, optional): Amount of HIVE to claim (default: 0).
            reward_hbd (str|float|Amount, optional): Amount of HBD to claim (default: 0).
            reward_vests (str|float|Amount, optional): Amount of VESTS to claim (default: 0).
            account (str|Account, optional): Account to claim rewards for; if None, uses self. Must be a valid account.

        Returns:
            dict: The broadcast/finalization result returned by the blockchain finalizeOp call.

        Raises:
            ValueError: If no account is provided or the resolved account is falsy.
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        if not account:
            raise ValueError("You need to provide an account")

        # if no values were set by user, claim all outstanding balances on
        # account

        reward_token_amount = self._check_amount(reward_hive, self.blockchain.token_symbol)
        reward_backed_token_amount = self._check_amount(
            reward_hbd, self.blockchain.backed_token_symbol
        )
        reward_vests_amount = self._check_amount(reward_vests, self.blockchain.vest_token_symbol)

        reward_token = "reward_hive"
        reward_backed_token = "reward_hbd"

        if (
            reward_token_amount.amount == 0
            and reward_backed_token_amount.amount == 0
            and reward_vests_amount.amount == 0
        ):
            if len(account.balances["rewards"]) == 3:
                reward_token_amount = account.balances["rewards"][0]
                reward_backed_token_amount = account.balances["rewards"][1]
                reward_vests_amount = account.balances["rewards"][2]
            else:
                reward_token_amount = account.balances["rewards"][0]
                reward_vests_amount = account.balances["rewards"][1]
        if len(account.balances["rewards"]) == 3:
            op = operations.Claim_reward_balance(
                **{
                    "account": account["name"],
                    reward_token: reward_token_amount,
                    reward_backed_token: reward_backed_token_amount,
                    "reward_vests": reward_vests_amount,
                    "prefix": self.blockchain.prefix,
                    "json_str": True,
                }
            )
        else:
            op = operations.Claim_reward_balance(
                **{
                    "account": account["name"],
                    reward_token: reward_token_amount,
                    "reward_vests": reward_vests_amount,
                    "prefix": self.blockchain.prefix,
                    "json_str": True,
                }
            )

        return self.blockchain.finalizeOp(op, account, "posting", **kwargs)

    def delegate_vesting_shares(
        self,
        to_account: str | Account,
        vesting_shares: str | Amount,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Delegate vesting shares (Hive Power) from one account to another.

        Parameters:
            to_account (str or Account): Receiver of the delegated vesting shares (delegatee).
            vesting_shares (str|Amount): Amount to delegate, e.g. "10000 VESTS" or an Amount-like object.
            account (str or Account, optional): Source account (delegator). If omitted, uses this Account instance.

        Returns:
            dict: Result of broadcasting the Delegate_vesting_shares operation (transaction/result object).

        Raises:
            ValueError: If `to_account` is not provided or cannot be resolved.
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        to_account = Account(to_account, blockchain_instance=self.blockchain)
        if to_account is None:
            raise ValueError("You need to provide a to_account")
        vesting_shares = self._check_amount(vesting_shares, self.blockchain.vest_token_symbol)

        op = operations.Delegate_vesting_shares(
            **{
                "delegator": account["name"],
                "delegatee": to_account["name"],
                "vesting_shares": vesting_shares,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )
        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def withdraw_vesting(
        self,
        amount: int | float | str | Amount,
        account: str | Account | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Withdraw VESTS from the vesting account.

        :param float amount: number of VESTS to withdraw over a period of
            13 weeks
        :param str account: (optional) the source account for the transfer
            if not ``default_account``

        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        amount = self._check_amount(amount, self.blockchain.vest_token_symbol)

        op = operations.Withdraw_vesting(
            **{
                "account": account["name"],
                "vesting_shares": amount,
                "prefix": self.blockchain.prefix,
                "json_str": True,
            }
        )

        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def set_withdraw_vesting_route(
        self,
        to: str | Account,
        percentage: float = 100,
        account: str | Account | None = None,
        auto_vest: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Set or update a vesting withdraw route for an account.

        When the source account withdraws vesting shares, a portion of the withdrawn amount is routed to `to` according to `percentage`. If `auto_vest` is True the recipient receives VESTS; otherwise the recipient receives liquid HIVE.

        Parameters:
            to (str): Recipient account name.
            percentage (float): Percentage of each withdraw to route to `to` (0.0–100.0). Internally converted to protocol units (multiplied by HIVE_1_PERCENT).
            account (str|Account, optional): Source account performing the route change. If omitted, `self` is used.
            auto_vest (bool): If True route is added as VESTS; if False route is converted to HIVE.

        Returns:
            dict: Result of broadcasting the `set_withdraw_vesting_route` operation (as returned by finalizeOp).

        Notes:
            - Operation is broadcast with the source account's active authority.
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        op = operations.Set_withdraw_vesting_route(
            **{
                "from_account": account["name"],
                "to_account": to,
                "percent": int(percentage * HIVE_1_PERCENT),
                "auto_vest": auto_vest,
            }
        )

        return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def allow(
        self,
        foreign: str,
        weight: int | None = None,
        permission: str = "posting",
        account: str | Account | None = None,
        threshold: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Give additional access to an account by some other public key or account.

        :param str foreign: The foreign account that will obtain access
        :param int weight: (optional) The weight to use. If not
            define, the threshold will be used. If the weight is
            smaller than the threshold, additional signatures will
            be required. (defaults to threshold)
        :param str permission: (optional) The actual permission to
            modify (defaults to ``posting``)
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)
        :param int threshold: (optional) The threshold that needs to be
            reached by signatures to be able to interact
        """
        from copy import deepcopy

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        if permission not in ["owner", "posting", "active"]:
            raise ValueError("Permission needs to be either 'owner', 'posting', or 'active")
        account = Account(account, blockchain_instance=self.blockchain)

        if permission not in account:
            account = Account(account, blockchain_instance=self.blockchain, lazy=False, full=True)
            account.clear_cache()
            account.refresh()
        if permission not in account:
            account = Account(account, blockchain_instance=self.blockchain)
        if permission not in account:
            raise AssertionError("Could not access permission")

        if not weight:
            weight = account[permission]["weight_threshold"]

        authority = deepcopy(account[permission])
        try:
            pubkey = PublicKey(foreign, prefix=self.blockchain.prefix)
            authority["key_auths"].append([str(pubkey), weight])
        except Exception:
            try:
                foreign_account = Account(foreign, blockchain_instance=self.blockchain)
                authority["account_auths"].append([foreign_account["name"], weight])
            except Exception:
                raise ValueError("Unknown foreign account or invalid public key")
        if threshold:
            authority["weight_threshold"] = threshold
            self.blockchain._test_weights_treshold(authority)

        op = operations.Account_update(
            **{
                "account": account["name"],
                permission: authority,
                "memo_key": account["memo_key"],
                "json_metadata": account["json_metadata"],
                "prefix": self.blockchain.prefix,
            }
        )
        if permission == "owner":
            return self.blockchain.finalizeOp(op, account, "owner", **kwargs)
        else:
            return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def disallow(
        self,
        foreign: str,
        permission: str = "posting",
        account: str | Account | None = None,
        weight: int | None = None,
        threshold: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Remove additional access to an account by some other public
        key or account.

        :param str foreign: The foreign account that will obtain access
        :param str permission: (optional) The actual permission to
            modify (defaults to ``posting``)
        :param str account: (optional) the account to allow access
            to (defaults to ``default_account``)
        :param int threshold: The threshold that needs to be reached
            by signatures to be able to interact
        """
        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        if permission not in ["owner", "active", "posting"]:
            raise ValueError("Permission needs to be either 'owner', 'posting', or 'active")
        authority = account[permission]

        try:
            pubkey = PublicKey(foreign, prefix=self.blockchain.prefix)
            if weight:
                affected_items = list(
                    [x for x in authority["key_auths"] if x[0] == str(pubkey) and x[1] == weight]
                )
                authority["key_auths"] = list(
                    [
                        x
                        for x in authority["key_auths"]
                        if not (x[0] == str(pubkey) and x[1] == weight)
                    ]
                )
            else:
                affected_items = list([x for x in authority["key_auths"] if x[0] == str(pubkey)])
                authority["key_auths"] = list(
                    [x for x in authority["key_auths"] if x[0] != str(pubkey)]
                )
        except Exception:
            try:
                foreign_account = Account(foreign, blockchain_instance=self.blockchain)
                if weight:
                    affected_items = list(
                        [
                            x
                            for x in authority["account_auths"]
                            if x[0] == foreign_account["name"] and x[1] == weight
                        ]
                    )
                    authority["account_auths"] = list(
                        [
                            x
                            for x in authority["account_auths"]
                            if not (x[0] == foreign_account["name"] and x[1] == weight)
                        ]
                    )
                else:
                    affected_items = list(
                        [x for x in authority["account_auths"] if x[0] == foreign_account["name"]]
                    )
                    authority["account_auths"] = list(
                        [x for x in authority["account_auths"] if x[0] != foreign_account["name"]]
                    )
            except Exception:
                raise ValueError("Unknown foreign account or invalid public key")

        if not affected_items:
            raise ValueError("Changes nothing!")
        removed_weight = affected_items[0][1]

        # Define threshold
        if threshold:
            authority["weight_threshold"] = threshold

        # Correct threshold (at most by the amount removed from the
        # authority)
        try:
            self.blockchain._test_weights_treshold(authority)
        except Exception:
            log.critical("The account's threshold will be reduced by %d" % (removed_weight))
            authority["weight_threshold"] -= removed_weight
            self.blockchain._test_weights_treshold(authority)

        op = operations.Account_update(
            **{
                "account": account["name"],
                permission: authority,
                "memo_key": account["memo_key"],
                "json_metadata": account["json_metadata"],
                "prefix": self.blockchain.prefix,
            }
        )
        if permission == "owner":
            return self.blockchain.finalizeOp(op, account, "owner", **kwargs)
        else:
            return self.blockchain.finalizeOp(op, account, "active", **kwargs)

    def feed_history(
        self,
        limit: int | None = None,
        start_author: str | None = None,
        start_permlink: str | None = None,
        account: str | Account | None = None,
    ) -> Any:
        """
        Yield feed entries for an account in reverse chronological order.

        Streams discussion entries from the account's feed using paginated calls to the discussions API. Entries are yielded one at a time until the optional limit is reached or no more entries are available. Note that RPC nodes keep only a limited feed history, so older entries may be unavailable.

        Parameters:
            limit (int, optional): Maximum number of entries to yield. If omitted, yields all available entries.
            start_author (str, optional): Author name to start from. Must be provided together with `start_permlink` to page from a specific position.
            start_permlink (str, optional): Permlink to start from. Must be provided together with `start_author`.
            account (str|Account, optional): Account whose feed to stream. If omitted, uses this Account instance.

        Raises:
            AssertionError: If `limit` is not a positive integer, or if only one of `start_author` / `start_permlink` is provided.

        Yields:
            dict or Comment-like object: Discussion/feed entries returned by the discussions API, in reverse time order.
        """
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                raise AssertionError("`limit` has to be greater than 0`")
        if (start_author is None and start_permlink is not None) or (
            start_author is not None and start_permlink is None
        ):
            raise AssertionError(
                "either both or none of `start_author` and `start_permlink` have to be set"
            )

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)
        feed_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - feed_count + 1, query_limit)
            from .discussions import Discussions_by_feed, Query

            query = Query(
                start_author=start_author,
                start_permlink=start_permlink,
                limit=query_limit,
                tag=account["name"],
            )
            results = Discussions_by_feed(query, blockchain_instance=self.blockchain)
            if len(results) == 0 or (start_permlink and len(results) == 1):
                return
            if feed_count > 0 and start_permlink:
                results = results[1:]  # strip duplicates from previous iteration
            for entry in results:
                feed_count += 1
                yield entry
                start_permlink = entry["permlink"]
                start_author = entry["author"]
                if feed_count == limit:
                    return

    def blog_history(
        self,
        limit: int | None = None,
        start: int = -1,
        reblogs: bool = True,
        account: str | Account | None = None,
    ) -> Any:
        """
        Yield blog entries for an account in reverse chronological order.

        Streams Discussion entries from the account's blog (newest first). Results are limited by RPC node history and may not include very old posts.

        Parameters:
            limit (int, optional): Maximum number of entries to yield. Must be > 0 if provided; otherwise all available entries are streamed.
            start (int, optional): (Currently ignored) kept for backward compatibility.
            reblogs (bool, optional): If True (default), include reblogs; if False, only original posts by the account are yielded.
            account (str|Account, optional): Account name or Account object to stream; defaults to this Account instance.

        Returns:
            generator: Yields discussion dicts (post objects) as returned by Discussions_by_blog.

        Raises:
            AssertionError: If limit is provided but is not an int > 0.
        """
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                raise AssertionError("`limit` has to be greater than 0`")

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        post_count = 0
        start_permlink = None
        start_author = None
        while True:
            query_limit = 100
            if limit is not None and reblogs:
                query_limit = min(limit - post_count + 1, query_limit)

            from .discussions import Discussions_by_blog

            query = {
                "start_author": start_author,
                "start_permlink": start_permlink,
                "limit": query_limit,
                "tag": account["name"],
            }
            results = Discussions_by_blog(query, blockchain_instance=self.blockchain)
            if len(results) == 0 or (start_permlink and len(results) == 1):
                return
            if start_permlink:
                results = results[1:]  # strip duplicates from previous iteration
            for post in results:
                if post["author"] == "":
                    continue
                if reblogs or post["author"] == account["name"]:
                    post_count += 1
                    yield post
                start_permlink = post["permlink"]
                start_author = post["author"]
                if post_count == limit:
                    return

    def comment_history(
        self,
        limit: int | None = None,
        start_permlink: str | None = None,
        account: str | Account | None = None,
    ) -> Any:
        """
        Yield comments authored by an account in reverse chronological order.

        Streams available comment entries from the node's discussions_by_comments index. Results are returned newest-first and may be truncated by RPC node history limits; older comments might not be available.

        Parameters:
            limit (int, optional): Maximum number of comments to yield. If None, yields all available comments.
            start_permlink (str, optional): If set, start streaming from this permlink (inclusive). If None, starts from the latest available entry.
            account (str or Account, optional): Account name or Account instance to stream comments for. Defaults to the Account instance this method is called on.

        Yields:
            dict: Discussion/comment dictionaries as returned by the Discussions_by_comments helper.

        Raises:
            AssertionError: If `limit` is provided and is not a positive integer.
        """
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                raise AssertionError("`limit` has to be greater than 0`")

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        comment_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - comment_count + 1, query_limit)
            from .discussions import Discussions_by_comments

            query = {
                "start_author": account["name"],
                "start_permlink": start_permlink,
                "limit": query_limit,
            }
            results = Discussions_by_comments(query, blockchain_instance=self.blockchain)
            if len(results) == 0 or (start_permlink and len(results) == 1):
                return
            if comment_count > 0 and start_permlink:
                results = results[1:]  # strip duplicates from previous iteration
            for comment in results:
                if comment["permlink"] == "":
                    continue
                comment_count += 1
                yield comment
                start_permlink = comment["permlink"]
                if comment_count == limit:
                    return

    def reply_history(
        self,
        limit: int | None = None,
        start_author: str | None = None,
        start_permlink: str | None = None,
        account: str | Account | None = None,
    ) -> Any:
        """Stream the replies to an account in reverse time order.

        .. note:: RPC nodes keep a limited history of entries for the
                  replies to an author. Older replies to an account may
                  not be available via this call due to
                  these node limitations.

        :param int limit: (optional) stream the latest `limit`
            replies. If unset (default), all available replies
            are streamed.
        :param str start_author: (optional) start streaming the
            replies from this author. `start_permlink=None`
            (default) starts with the latest available entry.
            If set, `start_permlink` has to be set as well.
        :param str start_permlink: (optional) start streaming the
            replies from this permlink. `start_permlink=None`
            (default) starts with the latest available entry.
            If set, `start_author` has to be set as well.
        :param str account: (optional) the account to get replies
            to (defaults to ``default_account``)

        comment_history_reverse example:

        .. code-block:: python

            from nectar.account import Account
            acc = Account("ned")
            for reply in acc.reply_history(limit=10):
                print(reply)

        """
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                raise AssertionError("`limit` has to be greater than 0`")
        if (start_author is None and start_permlink is not None) or (
            start_author is not None and start_permlink is None
        ):
            raise AssertionError(
                "either both or none of `start_author` and `start_permlink` have to be set"
            )

        if account is None:
            account = self
        else:
            account = Account(account, blockchain_instance=self.blockchain)

        if start_author is None:
            start_author = account["name"]

        reply_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - reply_count + 1, query_limit)
            from .discussions import Replies_by_last_update

            query = {
                "start_author": start_author,
                "start_permlink": start_permlink,
                "limit": query_limit,
            }
            results = Replies_by_last_update(query, blockchain_instance=self.blockchain)
            if len(results) == 0 or (start_permlink and len(results) == 1):
                return
            if reply_count > 0 and start_permlink:
                results = results[1:]  # strip duplicates from previous iteration
            for reply in results:
                if reply["author"] == "":
                    continue
                reply_count += 1
                yield reply
                start_author = reply["author"]
                start_permlink = reply["permlink"]
                if reply_count == limit:
                    return


class AccountsObject(list):
    def printAsTable(self) -> None:
        t = PrettyTable(["Name"])
        t.align = "l"
        for acc in self:
            t.add_row([acc["name"]])
        print(t)

    def print_summarize_table(
        self, tag_type: str = "Follower", return_str: bool = False, **kwargs
    ) -> str | None:
        """
        Print or return a one-line summary table aggregating metrics for the accounts in this collection.

        Calculates and reports:
        - total count of accounts,
        - summed MVest value (own vesting shares / 1e6),
        - mean and max reputation (if available),
        - summed, mean, and max effective HP (Hive Power) (if available),
        - mean time since last vote (hours) and mean time since last post (days) excluding accounts inactive >= 365 days,
        - counts of accounts without a vote or a post in the last 365 days.

        Parameters:
            tag_type (str): Label used for counting rows (default "Follower").
            return_str (bool): If True, return the formatted table as a string; if False, print it.
            **kwargs: Passed through to PrettyTable.get_string (formatting options).

        Returns:
            Optional[str]: The table string when return_str is True; otherwise None.
        """
        t = PrettyTable(["Key", "Value"])
        t.align = "r"
        t.add_row([tag_type + " count", str(len(self))])
        own_mvest = []
        eff_sp = []
        rep = []
        last_vote_h = []
        last_post_d = []
        no_vote = 0
        no_post = 0
        for f in self:
            rep.append(f.rep)
            own_mvest.append(float(f.balances["available"][2]) / 1e6)
            eff_sp.append(f.get_token_power())
            last_vote = datetime.now(timezone.utc) - (f["last_vote_time"])
            if last_vote.days >= 365:
                no_vote += 1
            else:
                last_vote_h.append(last_vote.total_seconds() / 60 / 60)
            last_post = datetime.now(timezone.utc) - (f["last_root_post"])
            if last_post.days >= 365:
                no_post += 1
            else:
                last_post_d.append(last_post.total_seconds() / 60 / 60 / 24)

        t.add_row(["Summed MVest value", "%.2f" % sum(own_mvest)])
        if len(rep) > 0:
            t.add_row(["Mean Rep.", "%.2f" % (sum(rep) / len(rep))])
            t.add_row(["Max Rep.", "%.2f" % (max(rep))])
        if len(eff_sp) > 0:
            t.add_row(["Summed eff. HP", "%.2f" % sum(eff_sp)])
            t.add_row(["Mean eff. HP", "%.2f" % (sum(eff_sp) / len(eff_sp))])
            t.add_row(["Max eff. HP", "%.2f" % max(eff_sp)])
        if len(last_vote_h) > 0:
            t.add_row(
                [
                    "Mean last vote diff in hours",
                    "%.2f" % (sum(last_vote_h) / len(last_vote_h)),
                ]
            )
        if len(last_post_d) > 0:
            t.add_row(
                [
                    "Mean last post diff in days",
                    "%.2f" % (sum(last_post_d) / len(last_post_d)),
                ]
            )
        t.add_row([tag_type + " without vote in 365 days", no_vote])
        t.add_row([tag_type + " without post in 365 days", no_post])
        if return_str:
            return t.get_string(**kwargs)
        else:
            print(t.get_string(**kwargs))


class Accounts(AccountsObject):
    """Obtain a list of accounts

    :param list name_list: list of accounts to fetch
    :param int batch_limit: (optional) maximum number of accounts
        to fetch per call, defaults to 100
    :param Blockchain blockchain_instance: Blockchain instance to use when
        accessing the RPC
    """

    def __init__(
        self,
        name_list,
        batch_limit=100,
        lazy=False,
        full=True,
        blockchain_instance=None,
    ):
        """
        Initialize an Accounts collection by batch-fetching account data and wrapping each result in an Account object.

        Parameters:
            name_list (Iterable[str]): Sequence of account names to load.
            batch_limit (int): Maximum number of accounts fetched per RPC call (default 100).
            lazy (bool): Passed to each Account; if True, create lightweight Account objects (default False).
            full (bool): Passed to each Account; if True, request full account data when available (default True).
            blockchain_instance: Optional blockchain client; when omitted, a shared instance is used.

        Behavior:
            - If the blockchain client is not connected, initialization returns early (creates an empty collection).
            - Accounts are fetched in batches via the blockchain RPC. When appbase is enabled the
              `find_accounts` (database) endpoint is used; otherwise `get_accounts` is used.
            - Each fetched account JSON is converted into an Account(name_or_dict, lazy=..., full=..., blockchain_instance=...).
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if not self.blockchain.is_connected():
            return
        accounts = []
        name_cnt = 0

        while name_cnt < len(name_list):
            self.blockchain.rpc.set_next_node_on_empty_reply(False)
            accounts += self.blockchain.rpc.find_accounts(
                {"accounts": name_list[name_cnt : batch_limit + name_cnt]}
            )["accounts"]
            name_cnt += batch_limit

        super().__init__(
            [
                Account(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                for x in accounts
            ]
        )
