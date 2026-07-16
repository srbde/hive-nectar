from __future__ import annotations

import logging
from typing import Any

from nectar.account import Account
from nectar.exceptions import VotingInvalidOnArchivedPost
from nectar.utils import construct_authorperm, formatToTimeStamp, make_patch, resolve_authorperm
from nectarbase import operations

log = logging.getLogger(__name__)


class CommentOperationsMixin:
    def upvote(self, weight: float = 100.0, voter: str | Account | None = None) -> dict[str, Any]:
        """Upvote the post

        :param float weight: (optional) Weight for posting (-100.0 -
            +100.0) defaults to +100.0
        :param str voter: (optional) Voting account

        """
        if weight < 0:
            raise ValueError("Weight must be >= 0.")
        last_payout = self.get("last_payout", None)
        if last_payout is not None:
            if formatToTimeStamp(last_payout) > 0:
                raise VotingInvalidOnArchivedPost
        return self.vote(weight, account=voter)

    def downvote(self, weight: float = 100.0, voter: str | Account | None = None) -> dict[str, Any]:
        """Downvote the post

        :param float weight: (optional) Weight for posting (-100.0 -
            +100.0) defaults to -100.0
        :param str voter: (optional) Voting account

        """
        if weight < 0:
            raise ValueError("Weight must be >= 0.")
        last_payout = self.get("last_payout", None)
        if last_payout is not None:
            if formatToTimeStamp(last_payout) > 0:
                raise VotingInvalidOnArchivedPost
        return self.vote(-weight, account=voter)

    def vote(
        self,
        weight: float,
        account: str | Account | None = None,
        identifier: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Vote for a post

        :param float weight: Voting weight. Range: -100.0 - +100.0.
        :param str account: (optional) Account to use for voting. If
            ``account`` is not defined, the ``default_account`` will be used
            or a ValueError will be raised
        :param str identifier: Identifier for the post to vote. Takes the
            form ``@author/permlink``.

        """
        if not identifier:
            identifier = construct_authorperm(self["author"], self["permlink"])

        return self.blockchain.vote(weight, identifier, account=account)

    def edit(self, body, meta=None, replace=False):
        """Edit an existing post

        :param str body: Body of the reply
        :param json meta: JSON meta object that can be attached to the
            post. (optional)
        :param bool replace: Instead of calculating a *diff*, replace
            the post entirely (defaults to ``False``)

        """
        if not meta:
            meta = {}
        original_post = self

        if replace:
            newbody = body
        else:
            newbody = make_patch(original_post["body"], body)
            if not newbody:
                log.info("No changes made! Skipping ...")
                return

        reply_identifier = construct_authorperm(
            original_post["parent_author"], original_post["parent_permlink"]
        )

        new_meta = {}
        if meta is not None:
            if bool(original_post["json_metadata"]):
                new_meta = original_post["json_metadata"]
                for key in meta:
                    new_meta[key] = meta[key]
            else:
                new_meta = meta

        return self.blockchain.post(
            original_post["title"],
            newbody,
            reply_identifier=reply_identifier,
            author=original_post["author"],
            permlink=original_post["permlink"],
            json_metadata=new_meta,
        )

    def reply(self, body, title="", author="", meta=None):
        """Reply to an existing post

        :param str body: Body of the reply
        :param str title: Title of the reply post
        :param str author: Author of reply (optional) if not provided
            ``default_user`` will be used, if present, else
            a ``ValueError`` will be raised.
        :param json meta: JSON meta object that can be attached to the
            post. (optional)

        """
        return self.blockchain.post(
            title, body, json_metadata=meta, author=author, reply_identifier=self.identifier
        )

    def delete(self, account=None, identifier=None):
        """
        Delete this post or comment from the blockchain.

        If `identifier` is provided it must be an author/permlink string (e.g. "@author/permlink"); otherwise the current Comment's author and permlink are used. If `account` is not provided the method will use `blockchain.config["default_account"]` when present; otherwise a ValueError is raised.

        Note: a post/comment can only be deleted if it has no replies and no positive rshares.

        Parameters:
            account (str, optional): Account name to perform the deletion. If omitted, the configured default_account is used.
            identifier (str, optional): Author/permlink of the post to delete (format "@author/permlink"). Defaults to the current Comment.

        Returns:
            dict: Result of the blockchain finalizeOp / transaction broadcast.

        Raises:
            ValueError: If no account is provided and no default_account is configured.
        """
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self.blockchain)
        if not identifier:
            post_author = self["author"]
            post_permlink = self["permlink"]
        else:
            [post_author, post_permlink] = resolve_authorperm(identifier)
        op = operations.Delete_comment(**{"author": post_author, "permlink": post_permlink})
        return self.blockchain.finalizeOp(op, account, "posting")

    def reblog(self, identifier=None, account=None):
        """
        Create a reblog (resteem) for the specified post.

        Parameters:
            identifier (str, optional): Post identifier in the form "@author/permlink". If omitted, uses this Comment's identifier.
            account (str, optional): Name of the posting account to perform the reblog. If omitted, the configured `default_account` is used.

        Returns:
            dict: Result from the blockchain custom_json operation.

        Raises:
            ValueError: If no account is provided and no `default_account` is configured.
        """
        if not account:
            account = self.blockchain.configStorage.get("default_account")
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, blockchain_instance=self.blockchain)
        if identifier is None:
            identifier = self.identifier
        if identifier is None:
            raise ValueError("No identifier available")
        author, permlink = resolve_authorperm(str(identifier))
        json_body = ["reblog", {"account": account["name"], "author": author, "permlink": permlink}]
        return self.blockchain.custom_json(
            id="follow", json_data=json_body, required_posting_auths=[account["name"]]
        )
