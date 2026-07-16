class Query(dict):
    """Query to be used for all discussion queries

    :param int limit: limits the number of posts
    :param str tag: tag query
    :param int truncate_body:
    :param array filter_tags:
    :param array select_authors:
    :param array select_tags:
    :param str start_author:
    :param str start_permlink:
    :param str start_tag:
    :param str parent_author:
    :param str parent_permlink:
    :param str start_parent_author:
    :param str before_date:
    :param str author: Author (see Discussions_by_author_before_date)

    .. testcode::

        from nectar.discussions import Query
        query = Query(limit=10, tag="hive")

    """

    def __init__(
        self,
        limit: int = 0,
        tag: str = "",
        truncate_body: int = 0,
        filter_tags: list[str] | None = None,
        select_authors: list[str] | None = None,
        select_tags: list[str] | None = None,
        start_author: str | None = None,
        start_permlink: str | None = None,
        start_tag: str | None = None,
        parent_author: str | None = None,
        parent_permlink: str | None = None,
        start_parent_author: str | None = None,
        before_date: str | None = None,
        author: str | None = None,
        observer: str | None = None,
    ) -> None:
        """
        Initialize a Query mapping for discussion fetches.

        Creates a dict-like Query object containing normalized discussion query parameters used by the Discussions fetchers. List-valued parameters default to empty lists when None. Values are stored as keys on self (e.g. self["limit"], self["tag"], etc.).

        Parameters:
            limit (int): Maximum number of items requested (0 means no explicit client-side limit).
            tag (str): Topic tag or account (used by feed/blog where appropriate).
            truncate_body (int): Number of characters to truncate post bodies to (0 = no truncate).
            filter_tags (list|None): Tags to exclude; defaults to [].
            select_authors (list|None): Authors to include; defaults to [].
            select_tags (list|None): Tags to include; defaults to [].
            start_author (str|None): Author name used as a pagination starting point.
            start_permlink (str|None): Permlink used as a pagination starting point.
            start_tag (str|None): Tag used as a pagination starting point for tag-based queries.
            parent_author (str|None): Parent post author (used for comment/replies queries).
            parent_permlink (str|None): Parent post permlink (used for comment/replies queries).
            start_parent_author (str|None): Parent author used for pagination in replies queries.
            before_date (str|None): ISO 8601 datetime string to fetch items before this timestamp.
            author (str|None): Author name for author-scoped queries.
            observer (str|None): Observer account name for user-specific data (e.g., vote status).
        """
        self["limit"] = limit
        self["truncate_body"] = truncate_body
        self["tag"] = tag
        self["filter_tags"] = filter_tags or []
        self["select_authors"] = select_authors or []
        self["select_tags"] = select_tags or []
        self["start_author"] = start_author
        self["start_permlink"] = start_permlink
        self["start_tag"] = start_tag
        self["parent_author"] = parent_author
        self["parent_permlink"] = parent_permlink
        self["start_parent_author"] = start_parent_author
        self["before_date"] = before_date
        self["author"] = author
        self["observer"] = observer
