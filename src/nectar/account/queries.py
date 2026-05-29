from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from prettytable import PrettyTable

from nectar.account.models import Accounts, extract_account_name
from nectar.amount import Amount
from nectar.blockchain import Blockchain
from nectar.exceptions import OfflineHasNoRPCException
from nectar.rc import RC
from nectar.utils import addTzInfo, formatTimedelta, formatTimeString, parse_time, remove_from_dict
from nectarapi.exceptions import FilteredItemNotFound

if TYPE_CHECKING:
    from nectar.account import Account

log = logging.getLogger(__name__)


class AccountQueriesMixin:
    def getSimilarAccountNames(self, limit: int = 5) -> list[str] | None:
        """Deprecated, please use get_similar_account_names"""
        return self.get_similar_account_names(limit=limit)

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

    def get_creator(self) -> str | None:
        """Returns the account creator or `None` if the account was mined"""
        if self["mined"]:
            return None
        ops = list(self.get_account_history(1, 1))
        if not ops or "creator" not in ops[-1]:
            return None
        return ops[-1]["creator"]

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
                from nectar.comment import Comment

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
            account = self.__class__(account, blockchain_instance=self.blockchain)
        feed_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - feed_count + 1, query_limit)
            from nectar.discussions import Discussions_by_feed, Query

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
            account = self.__class__(account, blockchain_instance=self.blockchain)

        post_count = 0
        start_permlink = None
        start_author = None
        while True:
            query_limit = 100
            if limit is not None and reblogs:
                query_limit = min(limit - post_count + 1, query_limit)

            from nectar.discussions import Discussions_by_blog

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
            account = self.__class__(account, blockchain_instance=self.blockchain)

        comment_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - comment_count + 1, query_limit)
            from nectar.discussions import Discussions_by_comments

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
            account = self.__class__(account, blockchain_instance=self.blockchain)

        if start_author is None:
            start_author = account["name"]

        reply_count = 0
        while True:
            query_limit = 100
            if limit is not None:
                query_limit = min(limit - reply_count + 1, query_limit)
            from nectar.discussions import Replies_by_last_update

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
