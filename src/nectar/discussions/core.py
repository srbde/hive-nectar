import logging
import warnings
from typing import Any, Optional

from nectar.comment import Comment
from nectar.instance import shared_blockchain_instance

log = logging.getLogger(__name__)


class Discussions:
    """Get Discussions

    :param Hive blockchain_instance: Hive instance

    """

    def __init__(
        self, lazy: bool = False, blockchain_instance: Optional[Any] = None, **kwargs: Any
    ) -> None:
        """
        Initialize the Discussions orchestrator.

        Parameters:
            lazy (bool): If True, wrap fetched items in lazy-loading Comment objects.

        Notes:
            - The resolved blockchain instance is stored on self.blockchain (falls back to shared_blockchain_instance() when none provided).
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.lazy = lazy

    def get_discussions(self, discussion_type, discussion_query, limit=1000, raw_data=False):
        """
        Yield discussions of a given type according to a Query, handling pagination.

        This generator fetches discussions in pages from the appropriate per-type helper
        and yields individual discussion entries until `limit` items have been yielded
        or no more results are available.

        Parameters:
            discussion_type (str): One of:
                "trending", "author_before_date", "payout", "post_payout", "created",
                "active", "cashout", "votes", "children", "hot", "feed", "blog",
                "comments", "promoted", "replies", "tags".
                Determines which backend/query helper is used.
            discussion_query (Query): Query-like mapping with parameters used by the
                underlying helpers (e.g., limit, tag, start_author, start_permlink,
                before_date). If `discussion_query["limit"]` is 0, it will be set to
                100 when `limit >= 100`, otherwise set to the provided `limit`.
                If `before_date` is falsy, it will be set to "1970-01-01T00:00:00".
            limit (int): Maximum number of discussion items to yield (default 1000).
            raw_data (bool): If True, helpers are requested to return raw dict data;
                if False, helpers may return wrapped Comment objects when supported.

        Yields:
            Individual discussion items as returned by the selected helper:
            - For post/comment helpers: dicts when `raw_data=True`, or Comment objects
              when `raw_data=False` and wrapping is supported.
            - For "tags": tag dictionaries.

        Behavior and notes:
            - This function mutates `discussion_query` for pagination (start_* fields)
              and may update `discussion_query["limit"]` and `before_date` as described.
            - Pagination is driven by start markers (author/permlink/tag/parent_author)
              and the function avoids yielding duplicate entries across pages.
            - Raises ValueError if `discussion_type` is not one of the supported values.
        """
        if limit >= 100 and discussion_query["limit"] == 0:
            discussion_query["limit"] = 100
        elif limit < 100 and discussion_query["limit"] == 0:
            discussion_query["limit"] = limit
        query_count = 0
        found_more_than_start_entry = True
        if "start_author" in discussion_query:
            start_author = discussion_query["start_author"]
        else:
            start_author = None
        if "start_permlink" in discussion_query:
            start_permlink = discussion_query["start_permlink"]
        else:
            start_permlink = None
        if "start_tag" in discussion_query:
            start_tag = discussion_query["start_tag"]
        else:
            start_tag = None
        if "start_parent_author" in discussion_query:
            start_parent_author = discussion_query["start_parent_author"]
        else:
            start_parent_author = None
        if not discussion_query["before_date"]:
            discussion_query["before_date"] = "1970-01-01T00:00:00"
        while query_count < limit and found_more_than_start_entry:
            rpc_query_count = 0
            dd = None
            discussion_query["start_author"] = start_author
            discussion_query["start_permlink"] = start_permlink
            discussion_query["start_tag"] = start_tag
            discussion_query["start_parent_author"] = start_parent_author
            if discussion_type == "trending":
                dd = Discussions_by_trending(
                    discussion_query, blockchain_instance=self.blockchain, lazy=self.lazy
                )
            elif discussion_type == "author_before_date":
                dd = Discussions_by_author_before_date(
                    author=discussion_query["author"],
                    start_permlink=discussion_query["start_permlink"],
                    before_date=discussion_query["before_date"],
                    limit=discussion_query["limit"],
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                )
            elif discussion_type == "payout":
                dd = Comment_discussions_by_payout(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "post_payout":
                dd = Post_discussions_by_payout(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "created":
                dd = Discussions_by_created(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "active":
                dd = Discussions_by_active(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "cashout":
                dd = Discussions_by_cashout(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "votes":
                dd = Discussions_by_votes(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "children":
                dd = Discussions_by_children(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "hot":
                dd = Discussions_by_hot(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "feed":
                dd = Discussions_by_feed(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "blog":
                dd = Discussions_by_blog(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "comments":
                dd = Discussions_by_comments(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "promoted":
                dd = Discussions_by_promoted(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "replies":
                dd = Discussions_by_replies(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                    raw_data=raw_data,
                )
            elif discussion_type == "tags":
                dd = Trending_tags(
                    discussion_query,
                    blockchain_instance=self.blockchain,
                    lazy=self.lazy,
                )
            else:
                raise ValueError("Wrong discussion_type")
            if not dd:
                return

            for d in dd:
                double_result = False
                if discussion_type == "tags":
                    if query_count != 0 and rpc_query_count == 0 and (d["name"] == start_tag):
                        double_result = True
                        if len(dd) == 1:
                            found_more_than_start_entry = False
                    start_tag = d["name"]
                elif discussion_type == "replies":
                    if (
                        query_count != 0
                        and rpc_query_count == 0
                        and (d["author"] == start_parent_author and d["permlink"] == start_permlink)
                    ):
                        double_result = True
                        if len(dd) == 1:
                            found_more_than_start_entry = False
                    start_parent_author = d["author"]
                    start_permlink = d["permlink"]
                else:
                    if (
                        query_count != 0
                        and rpc_query_count == 0
                        and (d["author"] == start_author and d["permlink"] == start_permlink)
                    ):
                        double_result = True
                        if len(dd) == 1:
                            found_more_than_start_entry = False
                    start_author = d["author"]
                    start_permlink = d["permlink"]
                rpc_query_count += 1
                if not double_result:
                    query_count += 1
                    if query_count <= limit:
                        yield d


class Discussions_by_trending(list):
    """Get Discussions by trending

    :param Query discussion_query: Defines the parameter for
        searching posts
    :param Hive blockchain_instance: Hive instance
    :param bool raw_data: returns list of comments when False, default is False

    .. testcode::

        from nectar.discussions import Query, Discussions_by_trending
        q = Query(limit=10, tag="hive")
        for h in Discussions_by_trending(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_trending iterator that fetches trending discussions.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]

        posts = []
        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "trending",
            "tag": reduced_query.get("tag", ""),
            "observer": reduced_query.get("observer", ""),
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_author_before_date(list):
    """Get Discussions by author before date

    .. note:: To retrieve discussions before date, the time of creation
              of the discussion @author/start_permlink must be older than
              the specified before_date parameter.

    :param str author: Defines the author *(required)*
    :param str start_permlink: Defines the permlink of a starting discussion
    :param str before_date: Defines the before date for query
    :param int limit: Defines the limit of discussions

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_author_before_date
        for h in Discussions_by_author_before_date(limit=10, author="gtg"):
            print(h)

    """

    def __init__(
        self,
        author="",
        start_permlink="",
        before_date="1970-01-01T00:00:00",
        limit=100,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_author_before_date container of posts by a specific author before a given date.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        posts = []
        # Try to use the bridge API first (preferred method)
        if author:
            bridge_query = {
                "sort": "posts",
                "account": author,
                "limit": limit,
            }
            if start_permlink:
                bridge_query["start_permlink"] = start_permlink
            posts = self.blockchain.rpc.get_account_posts(bridge_query)
            # Filter by before_date if provided
            if before_date and before_date != "1970-01-01T00:00:00":
                filtered_posts = []
                for post in posts:
                    if "created" in post and post["created"] < before_date:
                        filtered_posts.append(post)
                posts = filtered_posts

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Comment_discussions_by_payout(list):
    """Get comment_discussions_by_payout

    :param Query discussion_query: Defines the parameter for
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Comment_discussions_by_payout
        q = Query(limit=10)
        for h in Comment_discussions_by_payout(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Comment_discussions_by_payout iterator that fetches comment discussions sorted by payout.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []

        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "payout_comments",
            "tag": reduced_query.get("tag", ""),
            "observer": reduced_query.get("observer", ""),
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Post_discussions_by_payout(list):
    """Get post_discussions_by_payout

    :param Query discussion_query: Defines the parameter for
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Post_discussions_by_payout
        q = Query(limit=10)
        for h in Post_discussions_by_payout(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Post_discussions_by_payout: fetches post discussions sorted by payout and populates the list (raw dicts or Comment objects).
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []

        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "payout",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_created(list):
    """Get discussions_by_created

    :param Query discussion_query: Defines the parameter for
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_created
        q = Query(limit=10)
        for h in Discussions_by_created(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_created fetcher and populate it with posts matching the query.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "created",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_active(list):
    """get_discussions_by_active

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive() instance to use when accesing a RPC

    .. testcode::

        from nectar.discussions import Query, Discussions_by_active
        q = Query(limit=10)
        for h in Discussions_by_active(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_active: fetch discussions sorted by "active" and populate the sequence.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "active",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_cashout(list):
    """Get discussions_by_cashout. This query seems to be broken at the moment.
    The output is always empty.

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_cashout
        q = Query(limit=10)
        for h in Discussions_by_cashout(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_cashout fetcher.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        # Note: 'payout' is the closest sort to 'cashout' in bridge API
        bridge_query = {
            "sort": "payout",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_votes(list):
    """Get discussions_by_votes

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_votes
        q = Query(limit=10)
        for h in Discussions_by_votes(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_votes: fetch discussions approximating "votes" and store results.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        # Note: There is no direct 'votes' sort in bridge API, so we'll approximate using trending
        bridge_query = {
            "sort": "trending",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_children(list):
    """Get discussions by children

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_children
        q = Query(limit=10)
        for h in Discussions_by_children(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_children fetcher that yields child (reply) discussions for a tag/post.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]

        posts = []
        # Try to use the bridge API first (preferred method)
        # Note: There is no direct 'children' sort in bridge API, we'll use 'trending' as a fallback
        bridge_query = {
            "sort": "trending",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)
        # We could try to sort posts by their children count here if needed

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_hot(list):
    """Get discussions by hot

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_hot
        q = Query(limit=10, tag="hive")
        for h in Discussions_by_hot(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_hot iterator that fetches "hot" discussions.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "hot",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_feed(list):
    """Get discussions by feed

    :param Query discussion_query: Defines the parameter
        searching posts, tag musst be set to a username

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_feed
        q = Query(limit=10, tag="hive")
        for h in Discussions_by_feed(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_feed instance that fetches a user's feed discussions.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        account = reduced_query.get("tag", "")
        if account:
            bridge_query = {
                "sort": "feed",
                "account": account,
                "limit": reduced_query.get("limit", 20),
            }
            if "start_author" in reduced_query and "start_permlink" in reduced_query:
                bridge_query["start_author"] = reduced_query["start_author"]
                bridge_query["start_permlink"] = reduced_query["start_permlink"]
            posts = self.blockchain.rpc.get_account_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_blog(list):
    """Get discussions by blog

    :param Query discussion_query: Defines the parameter
        searching posts, tag musst be set to a username

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_blog
        q = Query(limit=10)
        for h in Discussions_by_blog(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Discussions_by_blog fetcher that retrieves a user's blog posts.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        account = reduced_query.get("tag", "")
        if account:
            bridge_query = {
                "sort": "blog",
                "account": account,
                "limit": reduced_query.get("limit", 20),
            }
            if "start_author" in reduced_query and "start_permlink" in reduced_query:
                bridge_query["start_author"] = reduced_query["start_author"]
                bridge_query["start_permlink"] = reduced_query["start_permlink"]
            posts = self.blockchain.rpc.get_account_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_comments(list):
    """Get discussions by comments

    :param Query discussion_query: Defines the parameter
        searching posts, start_author and start_permlink must be set.

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_comments
        q = Query(limit=10, start_author="hiveio", start_permlink="firstpost")
        for h in Discussions_by_comments(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_comments.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in ["start_author", "start_permlink", "limit"]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method) when permlink is provided
        if (
            "start_author" in reduced_query
            and "start_permlink" in reduced_query
            and reduced_query["start_permlink"] is not None
        ):
            # The bridge.get_discussion API retrieves an entire discussion tree
            author = reduced_query["start_author"]
            permlink = reduced_query["start_permlink"]
            bridge_query = {
                "author": author,
                "permlink": permlink,
            }
            # The bridge API returns a discussion tree, we need to flatten it
            discussion = self.blockchain.rpc.get_discussion(bridge_query)
            # Extract comments from the discussion tree
            if discussion and isinstance(discussion, dict):
                posts = []
                # Start with the main post
                main_post = discussion.get(f"@{author}/{permlink}")
                if main_post:
                    posts.append(main_post)
                # Add replies
                for key, value in discussion.items():
                    if key != f"@{author}/{permlink}" and isinstance(value, dict):
                        posts.append(value)
                # Limit the number of posts if needed
                if "limit" in reduced_query and len(posts) > reduced_query["limit"]:
                    posts = posts[: reduced_query["limit"]]
        elif "start_author" in reduced_query:
            # When start_permlink is None, we cannot use bridge API as it requires a specific permlink
            # For now, return empty list since there's no direct API to get all comments by author
            # This is a limitation of the current API structure
            posts = []

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_promoted(list):
    """Get discussions by promoted

    :param Query discussion_query: Defines the parameter
        searching posts

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_promoted
        q = Query(limit=10, tag="hive")
        for h in Discussions_by_promoted(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_promoted.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in [
            "tag",
            "limit",
            "filter_tags",
            "select_authors",
            "select_tags",
            "truncate_body",
            "start_author",
            "start_permlink",
        ]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        # Try to use the bridge API first (preferred method)
        bridge_query = {
            "sort": "promoted",
            "tag": reduced_query.get("tag", ""),
            "observer": "",
        }
        if "limit" in reduced_query:
            bridge_query["limit"] = reduced_query["limit"]
        if "start_author" in reduced_query and "start_permlink" in reduced_query:
            bridge_query["start_author"] = reduced_query["start_author"]
            bridge_query["start_permlink"] = reduced_query["start_permlink"]
        posts = self.blockchain.rpc.get_ranked_posts(bridge_query)

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Discussions_by_replies(list):
    """Get replies for an author's post

    :param Query discussion_query: Defines the parameter
        searching posts, start_parent_author, start_permlink must be set.

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Discussions_by_replies
        q = Query(limit=10, start_parent_author="hiveio", start_permlink="firstpost")
        for h in Discussions_by_replies(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize Discussions_by_replies.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        reduced_query = {}
        for key in ["start_parent_author", "start_permlink", "limit"]:
            if key in discussion_query:
                reduced_query[key] = discussion_query[key]
        posts = []
        author = reduced_query.get("start_parent_author")
        permlink = reduced_query.get("start_permlink")

        # Try to use the bridge API first (preferred method)
        if author and permlink:
            bridge_query = {"author": author, "permlink": permlink}
            discussion = self.blockchain.rpc.get_discussion(bridge_query)
            if discussion and isinstance(discussion, dict):
                # Exclude the main post itself
                posts = [
                    v
                    for k, v in discussion.items()
                    if k != f"@{author}/{permlink}" and isinstance(v, dict)
                ]
                if "limit" in reduced_query and len(posts) > reduced_query["limit"]:
                    posts = posts[: reduced_query["limit"]]

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Replies_by_last_update(list):
    """Returns a list of replies by last update

    :param Query discussion_query: Defines the parameter
        searching posts start_parent_author and start_permlink must be set.

    :param bool raw_data: returns list of comments when False, default is False
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Replies_by_last_update
        q = Query(limit=10, start_parent_author="hiveio", start_permlink="firstpost")
        for h in Replies_by_last_update(q):
            print(h)

    """

    def __init__(
        self,
        discussion_query,
        lazy=False,
        raw_data=False,
        blockchain_instance=None,
        **kwargs,
    ):
        """
        Initialize a Replies_by_last_update iterator that loads replies to a specific post.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        posts = []
        author = discussion_query.get("start_author")
        permlink = discussion_query.get("start_permlink")
        limit_value = discussion_query.get("limit", 100)

        if author and permlink:
            try:
                posts = self.blockchain.rpc.get_replies_by_last_update(
                    author,
                    permlink,
                    limit_value,
                )
            except Exception:
                posts = []

        if posts is None:
            posts = []
        if raw_data:
            super().__init__([x for x in posts])
        else:
            super().__init__(
                [Comment(x, lazy=lazy, blockchain_instance=self.blockchain) for x in posts]
            )


class Trending_tags(list):
    """Get trending tags

    :param Query discussion_query: Defines the parameter
        searching posts, start_tag is used if set
    :param Hive blockchain_instance: Hive instance

    .. testcode::

        from nectar.discussions import Query, Trending_tags
        q = Query(limit=10)
        for h in Trending_tags(q):
            print(h)

    """

    def __init__(self, discussion_query, lazy=False, blockchain_instance=None, **kwargs):
        """
        Initialize a Trending_tags iterator by fetching trending tags from the blockchain RPC.
        """
        if blockchain_instance is None and kwargs.get("hive_instance"):
            blockchain_instance = kwargs["hive_instance"]
            warnings.warn(
                "hive_instance is deprecated, use blockchain_instance instead",
                DeprecationWarning,
                stacklevel=2,
            )

        self.blockchain = blockchain_instance or shared_blockchain_instance()
        limit = discussion_query["limit"] if "limit" in discussion_query else 0
        tags = []
        try:
            tags = self.blockchain.rpc.get_trending_tags("", limit)
        except Exception:
            # If API fails, return empty list
            pass
        super().__init__(tags)
