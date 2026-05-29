from __future__ import annotations

from nectar.comment.models import (
    AccountPosts as AccountPosts,
)
from nectar.comment.models import (
    CommentModelBase,
)
from nectar.comment.models import (
    RankedPosts as RankedPosts,
)
from nectar.comment.models import (
    RecentByPath as RecentByPath,
)
from nectar.comment.models import (
    RecentReplies as RecentReplies,
)
from nectar.comment.operations import CommentOperationsMixin


class Comment(CommentModelBase, CommentOperationsMixin):
    pass
