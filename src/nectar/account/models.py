from __future__ import annotations

import json
import logging
import warnings
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any

from prettytable import PrettyTable

from nectar.amount import Amount
from nectar.blockchainobject import BlockchainObject
from nectar.exceptions import AccountDoesNotExistsException
from nectar.instance import shared_blockchain_instance
from nectar.utils import formatTimeString, parse_time

if TYPE_CHECKING:
    from nectar.account import Account

log = logging.getLogger(__name__)


def extract_account_name(account: str | Account | dict) -> str:
    from nectar.account import Account

    if isinstance(account, str):
        return account
    elif isinstance(account, Account):
        return account["name"]
    elif isinstance(account, dict) and "name" in account:
        return account["name"]
    else:
        return ""


class AccountModelBase(BlockchainObject):
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
    def json_metadata(self) -> dict:
        if self["json_metadata"] == "":
            return {}
        return json.loads(self["json_metadata"])

    @property
    def posting_json_metadata(self) -> dict:
        if self["posting_json_metadata"] == "":
            return {}
        return json.loads(self["posting_json_metadata"])

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
        from nectar.account import Account

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
