from __future__ import annotations

import json
import logging
from datetime import date, datetime, time

from prettytable import PrettyTable

from nectar.blockchainobject import BlockchainObject
from nectar.exceptions import AccountDoesNotExistsException, OfflineHasNoRPCException
from nectar.instance import shared_blockchain_instance
from nectar.utils import (
    addTzInfo,
    formatTimeString,
)

log = logging.getLogger(__name__)


class Community(BlockchainObject):
    """A class representing a Hive community with methods to interact with it.

    This class provides an interface to access and manipulate community data on the Hive blockchain.
    It extends BlockchainObject and provides additional community-specific functionality.

    Args:
        community: Either a community name (str) or a dictionary containing community data
        observer: Observer account for personalized results (default: "")
        full: If True, fetch full community data (default: True)
        lazy: If True, use lazy loading (default: False)
        blockchain_instance: Blockchain instance for RPC access

    Attributes:
        type_id (int): Type identifier for blockchain objects (2 for communities)

    Example:
        >>> from nectar.community import Community
        >>> from nectar import Hive
        >>> from nectar.nodelist import NodeList
        >>> nodelist = NodeList()
        >>> nodelist.update_nodes()
        >>> hv = Hive(node=nodelist.get_hive_nodes())
        >>> community = Community("hive-139531", blockchain_instance=hv)
        >>> print(community)
        <Community hive-139531>

    Note:
        This class includes caching to reduce API server load. Use refresh() to update
        the data and clear_cache() to clear the cache.
    """

    type_id = 2

    def __init__(
        self,
        community: str | dict,
        observer: str = "",
        full: bool = True,
        lazy: bool = False,
        blockchain_instance=None,
    ) -> None:
        """
        Create a Community wrapper for the given community identifier or raw data.

        If `community` is a dict, it will be normalized via _parse_json_data before initialization.
        This sets instance flags (full, lazy, observer) and resolves the blockchain instance used
        for RPC calls (falls back to the shared global instance). The object is constructed with
        its identifier field set to "name".

        Parameters:
            community: Community name (str) or a dict with community data.
            observer: Account name used to request personalized data (optional).
            full: If True, load complete community data when available.
            lazy: If True, defer loading detail until accessed.
        """
        self.full = full
        self.lazy = lazy
        self.observer = observer
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        if isinstance(community, dict):
            community = self._parse_json_data(community)
        super().__init__(
            community, lazy=lazy, full=full, id_item="name", blockchain_instance=self.blockchain
        )

    def refresh(self) -> None:
        """
        Refresh the community's data from the blockchain.

        Fetches the latest community record for this community's name via the bridge RPC and
        reinitializes the Community object with the returned data (updating identifier and all fields).
        If the instance is offline, the method returns without performing any RPC call.

        Raises:
            AccountDoesNotExistsException: If no community data is returned for this community name.
        """
        if not self.blockchain.is_connected():
            return
        self.blockchain.rpc.set_next_node_on_empty_reply(True)
        community = self.blockchain.rpc.get_community(
            {"name": self.identifier, "observer": self.observer}
        )

        if not community:
            raise AccountDoesNotExistsException(self.identifier)
        community = self._parse_json_data(community)
        self.identifier = community["name"]
        # self.blockchain.refresh_data()

        super().__init__(
            community,
            id_item="name",
            lazy=self.lazy,
            full=self.full,
            blockchain_instance=self.blockchain,
        )

    def _parse_json_data(self, community: dict) -> dict:
        """Parse and convert community JSON data into proper Python types.

        This internal method converts string representations of numbers to integers
        and parses date strings into datetime objects with timezone information.

        Args:
            community: Dictionary containing raw community data from the API

        Returns:
            dict: Processed community data with proper Python types
        """
        # Convert string numbers to integers
        int_fields = [
            "sum_pending",
            "subscribers",
            "num_pending",
            "num_authors",
        ]
        for field in int_fields:
            if field in community and isinstance(community.get(field), str):
                community[field] = int(community.get(field, 0))

        # Parse date strings into datetime objects
        date_fields = ["created_at"]
        for field in date_fields:
            if field in community and isinstance(community.get(field), str):
                community[field] = addTzInfo(
                    datetime.strptime(
                        community.get(field, "1970-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S"
                    )
                )

        return community

    def json(self) -> dict:
        """Convert the community data to a JSON-serializable dictionary.

        This method prepares the community data for JSON serialization by converting
        non-JSON-serializable types (like datetime objects) to strings.

        Returns:
            dict: A dictionary containing the community data in a JSON-serializable format
        """
        output = self.copy()

        # Convert integer fields to strings for JSON serialization
        int_fields = [
            "sum_pending",
            "subscribers",
            "num_pending",
            "num_authors",
        ]

        # Fields that should only be converted if non-zero
        int_non_zero_fields = []

        # Convert regular integer fields
        for field in int_fields:
            if field in output and isinstance(output[field], int):
                output[field] = str(output[field])

        # Convert non-zero integer fields
        for field in int_non_zero_fields:
            if field in output and isinstance(output[field], int) and output[field] != 0:
                output[field] = str(output[field])

        # Convert datetime fields to ISO format strings
        date_fields = ["created_at"]
        for field in date_fields:
            if field in output:
                date_val = output.get(field, datetime(1970, 1, 1, 0, 0))
                if isinstance(date_val, (datetime, date, time)):
                    output[field] = formatTimeString(date_val).replace("T", " ")
                else:
                    output[field] = date_val
        return json.loads(str(json.dumps(output)))

    def get_community_roles(self, limit: int = 100, last: str | None = None) -> list:
        """Lists community roles

        Args:
            limit: Maximum number of roles to return (default: 100)
            last: Account name of the last role from previous page for pagination

        Returns:
            list: List of community roles

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
        """
        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        params = {"community": community, "limit": limit}
        if last is not None:
            params["last"] = last

        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.list_community_roles(params)

    def get_subscribers(self, limit: int = 100, last: str | None = None) -> list:
        """Returns subscribers

        Args:
            limit: Maximum number of subscribers to return (default: 100)
            last: Account name of the last subscriber from previous page for pagination

        Returns:
            list: List of subscribers

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
        """
        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        params = {"community": community, "limit": limit}
        if last is not None:
            params["last"] = last

        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.list_subscribers(params)

    def get_activities(self, limit: int = 100, last_id: str | None = None) -> list:
        """Returns community activity

        Args:
            limit: Maximum number of activities to return (default: 100)
            last_id: ID of the last activity from previous page for pagination

        Returns:
            list: List of community activities

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
        """
        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        params = {"account": community, "limit": limit}
        if last_id is not None:
            params["last_id"] = last_id

        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.account_notifications(params)

    def get_ranked_posts(
        self,
        observer: str | None = None,
        limit: int = 100,
        start_author: str | None = None,
        start_permlink: str | None = None,
        sort: str = "created",
    ) -> list:
        """Returns community posts

        Args:
            observer: Account name of the observer (optional)
            limit: Maximum number of posts to return (default: 100)
            start_author: Author of the post to start from for pagination (optional)
            start_permlink: Permlink of the post to start from for pagination (optional)
            sort: Sort order (default: "created")

        Returns:
            list: List of community posts

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
        """
        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        params = {"tag": community, "limit": limit, "sort": sort}

        if observer is not None:
            params["observer"] = observer
        if start_author is not None:
            params["start_author"] = start_author
        if start_permlink is not None:
            params["start_permlink"] = start_permlink

        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        return self.blockchain.rpc.get_ranked_posts(params)

    def set_role(self, account: str, role: str, mod_account: str) -> dict:
        """Set role for a given account in the community.

        Args:
            account: Account name to set the role for
            role: Role to assign (member, mod, admin, owner, or guest)
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If role is not one of the allowed values
        """
        valid_roles = {"member", "mod", "admin", "owner", "guest"}
        if role.lower() not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "setRole",
            {
                "community": community,
                "account": account,
                "role": role.lower(),
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def set_user_title(self, account: str, title: str, mod_account: str) -> dict:
        """Set the title for a given account in the community.

        Args:
            account: Account name to set the title for
            title: Title to assign to the account
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If account or title is empty
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")

        if not title or not isinstance(title, str):
            raise ValueError("Title must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "setUserTitle",
            {
                "community": community,
                "account": account,
                "title": title.strip(),
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def mute_post(self, account: str, permlink: str, notes: str, mod_account: str) -> dict:
        """Mutes a post in the community.

        Args:
            account: Author of the post to mute
            permlink: Permlink of the post to mute
            notes: Reason for muting the post
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")
        if not permlink or not isinstance(permlink, str):
            raise ValueError("Permlink must be a non-empty string")
        if not isinstance(notes, str):
            raise ValueError("Notes must be a string")
        if not mod_account or not isinstance(mod_account, str):
            raise ValueError("Moderator account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "mutePost",
            {
                "community": community,
                "account": account,
                "permlink": permlink,
                "notes": notes.strip(),
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def unmute_post(self, account: str, permlink: str, notes: str, mod_account: str) -> dict:
        """Unmute a previously muted post in the community.

        Args:
            account: Author of the post to unmute
            permlink: Permlink of the post to unmute
            notes: Reason for unmuting the post
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")
        if not permlink or not isinstance(permlink, str):
            raise ValueError("Permlink must be a non-empty string")
        if not isinstance(notes, str):
            raise ValueError("Notes must be a string")
        if not mod_account or not isinstance(mod_account, str):
            raise ValueError("Moderator account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "unmutePost",
            {
                "community": community,
                "account": account,
                "permlink": permlink,
                "notes": notes.strip(),
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def update_props(
        self,
        title: str,
        about: str,
        is_nsfw: bool,
        description: str,
        flag_text: str,
        admin_account: str,
    ) -> dict:
        """Update community properties.

        Args:
            title: New title for the community (must be non-empty)
            about: Brief description of the community
            is_nsfw: Whether the community contains NSFW content
            description: Detailed description of the community
            flag_text: Text shown when flagging content in this community
            admin_account: Account name of the admin performing this action

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not title or not isinstance(title, str):
            raise ValueError("Title must be a non-empty string")
        if not isinstance(about, str):
            about = ""
        if not isinstance(description, str):
            description = ""
        if not isinstance(flag_text, str):
            flag_text = ""
        if not admin_account or not isinstance(admin_account, str):
            raise ValueError("Admin account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "updateProps",
            {
                "community": community,
                "props": {
                    "title": title.strip(),
                    "about": about.strip(),
                    "is_nsfw": bool(is_nsfw),
                    "description": description.strip(),
                    "flag_text": flag_text.strip(),
                },
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[admin_account]
        )

    def subscribe(self, account: str) -> dict:
        """Subscribe an account to this community.

        The account that calls this method will be subscribed to the community.
        The same account must be used to sign the transaction.

        Args:
            account: Account name that wants to subscribe to the community

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If account is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "subscribe",
            {
                "community": community,
            },
        ]
        return self.blockchain.custom_json("community", json_body, required_posting_auths=[account])

    def pin_post(self, account: str, permlink: str, mod_account: str) -> dict:
        """Pin a post to the top of the community feed.

        This method allows community moderators to pin a specific post to the top of the
        community's feed. The post will remain pinned until it is manually unpinned.

        Args:
            account: Author of the post to pin
            permlink: Permlink of the post to pin
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")
        if not permlink or not isinstance(permlink, str):
            raise ValueError("Permlink must be a non-empty string")
        if not mod_account or not isinstance(mod_account, str):
            raise ValueError("Moderator account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "pinPost",
            {
                "community": community,
                "account": account,
                "permlink": permlink,
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def unsubscribe(self, account: str) -> dict:
        """Unsubscribe an account from this community.

        The account that calls this method will be unsubscribed from the community.
        The same account must be used to sign the transaction.

        Args:
            account: Account name that wants to unsubscribe from the community

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If account is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "unsubscribe",
            {
                "community": community,
            },
        ]
        return self.blockchain.custom_json("community", json_body, required_posting_auths=[account])

    def unpin_post(self, account: str, permlink: str, mod_account: str) -> dict:
        """Remove a post from being pinned at the top of the community feed.

        This method allows community moderators to unpin a previously pinned post.
        After unpinning, the post will return to its normal position in the feed.

        Args:
            account: Author of the post to unpin
            permlink: Permlink of the post to unpin
            mod_account: Account name of the moderator performing this action (must be mod or higher)

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")
        if not permlink or not isinstance(permlink, str):
            raise ValueError("Permlink must be a non-empty string")
        if not mod_account or not isinstance(mod_account, str):
            raise ValueError("Moderator account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "unpinPost",
            {
                "community": community,
                "account": account,
                "permlink": permlink,
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[mod_account]
        )

    def flag_post(self, account: str, permlink: str, notes: str, reporter: str) -> dict:
        """Report a post to the community moderators for review.

        This method allows community members to flag posts that may violate
        community guidelines. The post will be added to the community's
        review queue for moderators to evaluate.

        Args:
            account: Author of the post being reported
            permlink: Permlink of the post being reported
            notes: Explanation of why the post is being reported
            reporter: Account name of the user reporting the post

        Returns:
            dict: Transaction result

        Raises:
            OfflineHasNoRPCException: If not connected to the blockchain
            ValueError: If any required parameter is invalid
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account must be a non-empty string")
        if not permlink or not isinstance(permlink, str):
            raise ValueError("Permlink must be a non-empty string")
        if not notes or not isinstance(notes, str):
            raise ValueError("Notes must be a string")
        if not reporter or not isinstance(reporter, str):
            raise ValueError("Reporter account must be a non-empty string")

        community = self["name"]
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")

        json_body = [
            "flagPost",
            {
                "community": community,
                "account": account,
                "permlink": permlink,
                "notes": notes.strip(),
            },
        ]
        return self.blockchain.custom_json(
            "community", json_body, required_posting_auths=[reporter]
        )


class CommunityObject(list):
    """A list-like container for Community objects with additional utility methods."""

    def printAsTable(self) -> None:
        """Print a formatted table of communities with key metrics.

        The table includes the following columns:
        - Nr.: Sequential number
        - Name: Community name
        - Title: Community title
        - lang: Language code
        - subscribers: Number of subscribers
        - sum_pending: Sum of pending payouts
        - num_pending: Number of pending posts
        - num_authors: Number of unique authors
        """
        t = PrettyTable(
            [
                "Nr.",
                "Name",
                "Title",
                "lang",
                "subscribers",
                "sum_pending",
                "num_pending",
                "num_authors",
            ]
        )
        t.align = "l"
        count = 0
        for community in self:
            count += 1
            t.add_row(
                [
                    str(count),
                    community["name"],
                    community["title"],
                    community["lang"],
                    community["subscribers"],
                    community["sum_pending"],
                    community["num_pending"],
                    community["num_authors"],
                ]
            )
        print(t)


class Communities(CommunityObject):
    """A list of communities with additional querying capabilities.

    This class extends CommunityObject to provide methods for fetching and
    searching communities from the blockchain.

    Args:
        sort: Sort order for communities (default: "rank")
        observer: Observer account for personalized results (optional)
        last: Last community name for pagination (optional)
        limit: Maximum number of communities to fetch (default: 100)
        lazy: If True, use lazy loading (default: False)
        full: If True, fetch full community data (default: True)
        blockchain_instance: Blockchain instance to use for RPC access
    """

    def __init__(
        self,
        sort: str = "rank",
        observer: str | None = None,
        last: str | None = None,
        limit: int = 100,
        lazy: bool = False,
        full: bool = True,
        blockchain_instance=None,
    ) -> None:
        """
        Initialize a Communities collection by querying the blockchain for community metadata.

        Fetches up to `limit` communities from the resolved blockchain instance using paginated bridge RPC calls and constructs Community objects from the results.

        Parameters:
            sort (str): Sort order for results (e.g., "rank"). Defaults to "rank".
            observer (str | None): Account used to personalize results; passed through to the RPC call.
            last (str | None): Starting community name for pagination; used as the RPC `last` parameter.
            limit (int): Maximum number of communities to fetch (clamped per-request to 100). Defaults to 100.
            lazy (bool): If True, created Community objects will use lazy loading. Defaults to False.
            full (bool): If True, created Community objects will request full data. Defaults to True.

        Notes:
            - If no blockchain instance is connected, initialization returns early and yields an empty collection.
            - The constructor ensures at most `limit` Community objects are created.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        if not self.blockchain.is_connected():
            return

        communities = []
        community_cnt = 0
        batch_limit = min(100, limit)  # Ensure we don't exceed the limit

        while community_cnt < limit:
            self.blockchain.rpc.set_next_node_on_empty_reply(False)
            batch = self.blockchain.rpc.list_communities(
                {"sort": sort, "observer": observer, "last": last, "limit": batch_limit},
            )
            if not batch:  # No more communities to fetch
                break

            communities.extend(batch)
            community_cnt += len(batch)
            last = communities[-1]["name"]

            # Adjust batch size for the next iteration if needed
            if community_cnt + batch_limit > limit:
                batch_limit = limit - community_cnt

        super().__init__(
            [
                Community(x, lazy=lazy, full=full, blockchain_instance=self.blockchain)
                for x in communities[:limit]  # Ensure we don't exceed the limit
            ]
        )

    def search_title(self, title: str) -> CommunityObject:
        """Search for communities with titles containing the given string.

        The search is case-insensitive.

        Args:
            title: Text to search for in community titles

        Returns:
            CommunityObject: A new CommunityObject containing matching communities
        """
        if not title or not isinstance(title, str):
            raise ValueError("Title must be a non-empty string")

        ret = CommunityObject()
        title_lower = title.lower()
        for community in self:
            if title_lower in community["title"].lower():
                ret.append(community)
        return ret
