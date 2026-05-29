from __future__ import annotations

from nectar.account.calculator import AccountCalculatorMixin
from nectar.account.models import (
    AccountModelBase,
)
from nectar.account.models import (
    Accounts as Accounts,
)
from nectar.account.models import (
    AccountsObject as AccountsObject,
)
from nectar.account.models import (
    extract_account_name as extract_account_name,
)
from nectar.account.operations import AccountOperationsMixin
from nectar.account.queries import AccountQueriesMixin


class Account(
    AccountModelBase,
    AccountCalculatorMixin,
    AccountQueriesMixin,
    AccountOperationsMixin,
):
    pass
