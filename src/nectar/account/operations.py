from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any

from nectar.account.models import extract_account_name
from nectar.amount import Amount
from nectar.constants import HIVE_1_PERCENT
from nectar.exceptions import OfflineHasNoRPCException
from nectar.utils import addTzInfo, formatTimeString
from nectarapi.exceptions import MissingRequiredActiveAuthority
from nectarbase import operations
from nectargraphenebase.account import PasswordKey, PublicKey

if TYPE_CHECKING:
    from nectar.account import Account

log = logging.getLogger(__name__)


class AccountOperationsMixin:
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
            account_obj = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)

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
            account_obj = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)

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
            account = self.__class__(account, blockchain_instance=self.blockchain)

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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if not skip_account_check:
            to = Account(to, blockchain_instance=self.blockchain)

        to_name = extract_account_name(to)
        account_name = extract_account_name(account)
        if memo and memo[0] == "#":
            from nectar.memo import Memo

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
            account = self.__class__(account, blockchain_instance=self.blockchain)
        amount = Amount(amount, asset, blockchain_instance=self.blockchain)
        if not skip_account_check:
            to = Account(to, blockchain_instance=self.blockchain)

        to_name = extract_account_name(to)
        account_name = extract_account_name(account)
        if memo and memo[0] == "#":
            from nectar.memo import Memo

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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)

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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)

        if permission not in ["owner", "posting", "active"]:
            raise ValueError("Permission needs to be either 'owner', 'posting', or 'active")
        account = self.__class__(account, blockchain_instance=self.blockchain)

        if permission not in account:
            account = self.__class__(
                account, blockchain_instance=self.blockchain, lazy=False, full=True
            )
            account.clear_cache()
            account.refresh()
        if permission not in account:
            account = self.__class__(account, blockchain_instance=self.blockchain)
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
            account = self.__class__(account, blockchain_instance=self.blockchain)

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
            except Exception as err:
                raise ValueError("Unknown foreign account or invalid public key") from err

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
