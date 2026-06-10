import json
import logging
import time
from datetime import datetime, timedelta, timezone

import click
from prettytable import PrettyTable

from nectar import exceptions
from nectar.account import Account, Accounts
from nectar.amount import Amount
from nectar.cli import cli
from nectar.cli.utils import (
    export_trx,
    unlock_wallet,
)
from nectar.comment import Comment
from nectar.instance import shared_blockchain_instance
from nectar.market import Market
from nectar.price import Price
from nectar.profile import Profile
from nectar.rc import RC
from nectar.utils import (
    construct_authorperm,
    derive_beneficiaries,
    formatTimeString,
    generate_password,
    import_coldcard_wif,
    import_pubkeys,
)
from nectar.vote import AccountVotes, ActiveVotes, Vote
from nectar.witness import Witness, WitnessesRankedByVote, WitnessesVotedByAccount

log = logging.getLogger(__name__)


@cli.command()
@click.argument("account", nargs=-1)
def power(account):
    """Shows vote power and bandwidth"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if len(account) == 0:
        if "default_account" in hv.config:
            account = [hv.config["default_account"]]
    for name in account:
        a = Account(name, blockchain_instance=hv)
        print("\n@%s" % a.name)
        a.print_info(use_table=True)


@cli.command()
@click.argument("account", nargs=-1)
def balance(account):
    """Shows balance"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if len(account) == 0:
        if "default_account" in hv.config:
            account = [hv.config["default_account"]]
    for name in account:
        a = Account(name, blockchain_instance=hv)
        print("\n@%s" % a.name)
        t = PrettyTable(["Account", hv.token_symbol, hv.backed_token_symbol, "VESTS"])
        t.align = "r"
        t.add_row(
            [
                "Available",
                str(a.balances["available"][0]),
                str(a.balances["available"][1]),
                str(a.balances["available"][2]),
            ]
        )
        t.add_row(
            [
                "Rewards",
                str(a.balances["rewards"][0]),
                str(a.balances["rewards"][1]),
                str(a.balances["rewards"][2]),
            ]
        )
        t.add_row(
            [
                "Savings",
                str(a.balances["savings"][0]),
                str(a.balances["savings"][1]),
                "N/A",
            ]
        )
        t.add_row(
            [
                "TOTAL",
                str(a.balances["total"][0]),
                str(a.balances["total"][1]),
                str(a.balances["total"][2]),
            ]
        )
        print(t)


@cli.command()
@click.argument("account", nargs=-1, required=False)
def interest(account):
    """Get information about interest payment"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        if "default_account" in hv.config:
            account = [hv.config["default_account"]]

    t = PrettyTable(
        ["Account", "Last Interest Payment", "Next Payment", "Interest rate", "Interest"]
    )
    t.align = "r"
    for a in account:
        a = Account(a, blockchain_instance=hv)
        i = a.interest()
        t.add_row(
            [
                a["name"],
                i["last_payment"],
                "in %s" % (i["next_payment_duration"]),
                "%.1f%%" % i["interest_rate"],
                "{:.3f} {}".format(i["interest"], hv.backed_token_symbol),
            ]
        )
    print(t)


@cli.command()
@click.argument("follow-type")
@click.option("--account", "-a", help="Get follow list for this account")
@click.option("--limit", "-l", help="Liimts the returned accounts", default=100)
def followlist(follow_type, account, limit):
    """Get information about followed lists

    follow_type can be blog
    On Hive, follow type can also be one the following: blacklisted, follow_blacklist, muted, or follow_muted
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        if "default_account" in hv.config:
            account = hv.config["default_account"]
    account = Account(account, blockchain_instance=hv)
    if follow_type == "blog":
        name_list = account.get_following(limit=limit)
    else:
        name_list = account.get_follow_list(follow_type)
        if limit and len(name_list) > limit:
            name_list = name_list[:limit]
    t = PrettyTable(["index", "name"])
    t.align = "r"
    i = 0
    for name in name_list:
        i += 1
        t.add_row([str(i), name])
    print(t)


@cli.command()
@click.argument("account", nargs=-1, required=False)
def follower(account):
    """Get information about followers"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    accounts = list(account or [])
    if not accounts and "default_account" in hv.config:
        accounts = [hv.config["default_account"]]
    for a in accounts:
        a = Account(a, blockchain_instance=hv)
        print("\nFollowers statistics for @%s (please wait...)" % a.name)
        followers = a.get_followers(False)
        if isinstance(followers, list) and not isinstance(followers, Accounts):
            raise TypeError("Expected Accounts object when raw_name_list is False")
        followers.print_summarize_table(tag_type="Followers")


@cli.command()
@click.argument("account", nargs=-1, required=False)
def following(account):
    """Get information about following"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    accounts = list(account or [])
    if not accounts and "default_account" in hv.config:
        accounts = [hv.config["default_account"]]
    for a in accounts:
        a = Account(a, blockchain_instance=hv)
        print("\nFollowing statistics for @%s (please wait...)" % a.name)
        following = a.get_following(False)
        if isinstance(following, list) and not isinstance(following, Accounts):
            raise TypeError("Expected Accounts object when raw_name_list is False")
        following.print_summarize_table(tag_type="Following")


@cli.command()
@click.argument("account", nargs=-1, required=False)
def muter(account):
    """Get information about muter"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    accounts = list(account or [])
    if not accounts and "default_account" in hv.config:
        accounts = [hv.config["default_account"]]
    for a in accounts:
        a = Account(a, blockchain_instance=hv)
        print("\nMuters statistics for @%s (please wait...)" % a.name)
        muters = a.get_muters(False)
        if isinstance(muters, list) and not isinstance(muters, Accounts):
            raise TypeError("Expected Accounts object when raw_name_list is False")
        muters.print_summarize_table(tag_type="Muters")


@cli.command()
@click.argument("account", nargs=-1, required=False)
def muting(account):
    """Get information about muting"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    accounts = list(account or [])
    if not accounts and "default_account" in hv.config:
        accounts = [hv.config["default_account"]]
    for a in accounts:
        a = Account(a, blockchain_instance=hv)
        print("\nMuting statistics for @%s (please wait...)" % a.name)
        muting = a.get_mutings(False)
        if isinstance(muting, list) and not isinstance(muting, Accounts):
            raise TypeError("Expected Accounts object when raw_name_list is False")
        muting.print_summarize_table(tag_type="Muting")


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--limit", "-l", help="Limits shown notifications")
@click.option(
    "--all",
    "-a",
    help="Show all notifications (when not set, only unread are shown)",
    is_flag=True,
    default=False,
)
@click.option(
    "--mark_as_read",
    "-m",
    help="Broadcast a mark all as read custom json",
    is_flag=True,
    default=False,
)
@click.option("--replies", "-r", help="Show only replies", is_flag=True, default=False)
@click.option("--mentions", "-t", help="Show only mentions", is_flag=True, default=False)
@click.option("--follows", "-f", help="Show only follows", is_flag=True, default=False)
@click.option("--votes", "-v", help="Show only upvotes", is_flag=True, default=False)
@click.option("--reblogs", "-b", help="Show only reblogs", is_flag=True, default=False)
@click.option(
    "--reverse", "-s", help="Reverse sorting of notifications", is_flag=True, default=False
)
def notifications(
    account, limit, all, mark_as_read, replies, mentions, follows, votes, reblogs, reverse
):
    """Show notifications of an account"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if account is None or account == "":
        if "default_account" in hv.config:
            account = hv.config["default_account"]
    if mark_as_read and not unlock_wallet(hv):
        return
    if not replies and not mentions and not follows and not votes and not reblogs:
        show_all = True
    else:
        show_all = False
    account = Account(account, blockchain_instance=hv)
    t = PrettyTable(["Date", "Type", "Message"], hrules=0)
    t.align = "r"
    last_read = None
    if limit is not None:
        limit = int(limit)
    all_notifications = account.get_notifications(only_unread=not all, limit=limit)
    if reverse:
        all_notifications = all_notifications[::-1]
    for note in all_notifications:
        if not show_all:
            if note["type"] == "reblog" and not reblogs:
                continue
            elif note["type"] == "reply" and not replies:
                continue
            elif note["type"] == "reply_comment" and not replies:
                continue
            elif note["type"] == "mention" and not mentions:
                continue
            elif note["type"] == "follow" and not follows:
                continue
            elif note["type"] == "vote" and not votes:
                continue
        # Handle date field which might be string or datetime
        date_obj = note["date"]
        if isinstance(date_obj, str):
            # Parse ISO format date string
            from datetime import datetime

            date_obj = datetime.fromisoformat(date_obj.replace("Z", "+00:00"))
        t.add_row(
            [
                str(date_obj),
                note["type"],
                note["msg"],
            ]
        )
        last_read = date_obj
    print(t)
    if mark_as_read:
        account.mark_notifications_as_read(last_read=last_read)


@cli.command()
@click.argument("account", nargs=1, required=False)
def permissions(account):
    """Show permissions of an account"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        if "default_account" in hv.config:
            account = hv.config["default_account"]
    account = Account(account, blockchain_instance=hv)
    t = PrettyTable(["Permission", "Threshold", "Key/Account"], hrules=0)
    t.align = "r"
    for permission in ["owner", "active", "posting"]:
        auths = []
        for type_ in ["account_auths", "key_auths"]:
            for authority in account[permission][type_]:
                auths.append("%s (%d)" % (authority[0], authority[1]))
        t.add_row(
            [
                permission,
                account[permission]["weight_threshold"],
                "\n".join(auths),
            ]
        )
    print(t)


@cli.command()
@click.argument("foreign_account", nargs=1, required=False)
@click.option(
    "--permission", default="posting", help='The permission to grant (defaults to "posting")'
)
@click.option("--account", "-a", help="The account to allow action for")
@click.option(
    "--weight",
    "-w",
    help="The weight to use instead of the (full) threshold. "
    "If the weight is smaller than the threshold, "
    "additional signatures are required",
)
@click.option(
    "--threshold",
    "-t",
    help="The permission's threshold that needs to be reached by signatures to be able to interact",
)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def allow(foreign_account, permission, account, weight, threshold, export):
    """Allow an account/key to interact with your account

    foreign_account: The account or key that will be allowed to interact with account.
        When not given, password will be asked, from which a public key is derived.
        This derived key will then interact with your account.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    if permission not in ["posting", "active", "owner"]:
        print("Wrong permission, please use: posting, active or owner!")
        return
    acc = Account(account, blockchain_instance=hv)
    if not foreign_account:
        from nectargraphenebase.account import PasswordKey

        pwd = click.prompt("Password for Key Derivation", confirmation_prompt=True, hide_input=True)
        foreign_account = format(PasswordKey(account, pwd, permission).get_public(), hv.prefix)
    if threshold is not None:
        threshold = int(threshold)
    tx = acc.allow(foreign_account, weight=weight, permission=permission, threshold=threshold)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("foreign_account", nargs=1, required=False)
@click.option(
    "--permission", "-p", default="posting", help='The permission to grant (defaults to "posting")'
)
@click.option("--account", "-a", help="The account to disallow action for")
@click.option(
    "--weight",
    "-w",
    type=int,
    help="The weight to use instead of the (full) threshold. "
    "If the weight is smaller than the threshold, "
    "additional signatures are required",
)
@click.option(
    "--threshold",
    "-t",
    help="The permission's threshold that needs to be reached by signatures to be able to interact",
)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def disallow(foreign_account, permission, account, weight, threshold, export):
    """Remove allowance an account/key to interact with your account"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    if permission not in ["posting", "active", "owner"]:
        print("Wrong permission, please use: posting, active or owner!")
        return
    if threshold is not None:
        threshold = int(threshold)
    acc = Account(account, blockchain_instance=hv)
    if not foreign_account:
        from nectargraphenebase.account import PasswordKey

        pwd = click.prompt("Password for Key Derivation", confirmation_prompt=True)
        foreign_account = format(PasswordKey(account, pwd, permission).get_public(), hv.prefix)
    elif isinstance(foreign_account, (list, tuple)):
        foreign_account = foreign_account[0]
    tx = acc.disallow(foreign_account, permission=permission, weight=weight, threshold=threshold)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.option("--role", "-r", help="When set, limits the shown keys for this role")
@click.option(
    "--max-account-index",
    "-a",
    help="Set maximum account index to check pubkeys (only when using ledger)",
    default=5,
)
@click.option(
    "--max-sequence",
    "-s",
    help="Set maximum key sequence to check pubkeys (only when using ledger)",
    default=2,
)
def listaccounts(role, max_account_index, max_sequence):
    """Show stored accounts

    Can be used with the ledger to obtain all accounts that uses pubkeys derived from this ledger
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if hv.use_ledger:
        t = PrettyTable(["Name", "Type", "Available Key", "Path"])
        t.align = "l"
        ledgertx = hv.new_tx()
        ledgertx.constructTx()
        key_found = False
        path = None
        current_account_index = 0
        current_key_index = 0
        role_list = ["owner", "active", "posting", "memo"]
        if role:
            role_list = [role]
        while not key_found and current_account_index < max_account_index:
            for perm in role_list:
                path = ledgertx.ledgertx.build_path(perm, current_account_index, current_key_index)
                current_pubkey = ledgertx.ledgertx.get_pubkey(path)
                account = hv.wallet.getAccountFromPublicKey(str(current_pubkey))
                if account is not None:
                    t.add_row([str(account), perm, str(current_pubkey), path])
            if current_key_index < max_sequence:
                current_key_index += 1
            else:
                current_key_index = 0
                current_account_index += 1
    else:
        t = PrettyTable(["Name", "Type", "Available Key"])
        t.align = "l"
        for account in hv.wallet.getAccounts():
            t.add_row([account["name"] or "n/a", account["type"] or "n/a", account["pubkey"]])
    print(t)


@cli.command()
@click.argument("creator", nargs=1, required=True)
@click.option(
    "--fee",
    help="When fee is 0 (default) a subsidized account is claimed and can be created later with create_claimed_account",
    default=0.0,
)
@click.option(
    "--number",
    "-n",
    help="Number of subsidized accounts to be claimed (default = 1), when fee = 0 HIVE",
    default=1,
)
@click.option(
    "--export",
    "-e",
    help="When set, transaction is stored in a file (should be used with number = 1)",
)
def claimaccount(creator, fee, number, export):
    """Claim account for claimed account creation."""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not creator:
        creator = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    creator = Account(creator, blockchain_instance=hv)
    fee = Amount(f"{float(fee):.3f} {hv.token_symbol}", blockchain_instance=hv)
    tx = None
    if float(fee) > 0:
        tx = hv.claim_account(creator, fee=fee)
    elif float(fee) == 0:
        rc = RC(blockchain_instance=hv)
        current_costs = rc.claim_account(tx_size=200)
        current_mana = creator.get_rc_manabar()["current_mana"]
        last_mana = current_mana
        cnt = 0
        print(
            "Current costs %.2f G RC - current mana %.2f G RC"
            % (current_costs / 1e9, current_mana / 1e9)
        )
        print("Account can claim %d accounts" % (int(current_mana / current_costs)))
        while current_costs + 10 < current_mana and cnt < number:
            if cnt > 0:
                print(
                    "Current costs %.2f G RC - current mana %.2f G RC"
                    % (current_costs / 1e9, current_mana / 1e9)
                )
                tx = json.dumps(tx, indent=4)
                print(tx)
            cnt += 1
            tx = hv.claim_account(creator, fee=fee)
            time.sleep(10)
            creator.refresh()
            current_mana = creator.get_rc_manabar()["current_mana"]
            print("Account claimed and %.2f G RC paid." % ((last_mana - current_mana) / 1e9))
            last_mana = current_mana
        if cnt == 0:
            print("Not enough RC for a claim!")
    else:
        tx = hv.claim_account(creator, fee=fee)
    if tx is not None:
        export_trx(tx, export)
        tx = json.dumps(tx, indent=4)
        print(tx)


@cli.command()
@click.argument("account", nargs=1, required=True)
@click.option(
    "--owner", help="Main owner public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--active", help="Active public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--posting", help="posting public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--memo", help="Memo public key - when not given, a passphrase is used to create keys."
)
@click.option("--import-pub", "-i", help="Load public keys from file.")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def changekeys(account, owner, active, posting, memo, import_pub, export):
    """Changes all keys for the specified account
    Keys are given in their public form.
    Asks for the owner key for broadcasting the op to the chain."""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    account = Account(account, blockchain_instance=hv)

    if import_pub and import_pub != "":
        owner, active, posting, memo = import_pubkeys(import_pub)

    if owner is None and active is None and memo is None and posting is None:
        raise ValueError("All pubkeys are None or empty!")
    if owner == "" or owner is None:
        owner = account["owner"]["key_auths"][0][0]
    if active == "" or active is None:
        active = account["active"]["key_auths"][0][0]
    if posting == "" or posting is None:
        posting = account["posting"]["key_auths"][0][0]
    if memo == "" or memo is None:
        memo = account["memo_key"]

    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    t.add_row(["account", account["name"]])
    t.add_row(["new owner pubkey", str(owner)])
    t.add_row(["new active pubkey", str(active)])
    t.add_row(["new posting pubkey", str(posting)])
    t.add_row(["new memo pubkey", str(memo)])
    print(t)
    if not hv.unsigned:
        wif = click.prompt(
            "Owner key for %s" % account["name"], confirmation_prompt=False, hide_input=True
        )
        hv.wallet.setKeys([wif])

    tx = hv.update_account(
        account,
        owner_key=owner,
        active_key=active,
        posting_key=posting,
        memo_key=memo,
        password=None,
    )
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("accountname", nargs=1, required=True)
@click.option("--account", "-a", help="Account that pays the fee or uses account tickets")
@click.option(
    "--owner", help="Main public owner key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--active", help="Active public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--memo", help="Memo public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--posting", help="posting public key - when not given, a passphrase is used to create keys."
)
@click.option(
    "--wif",
    "-w",
    help="Defines how many times the password is replaced by its WIF representation for password based keys (default = 0).",
    default=0,
)
@click.option(
    "--create-claimed-account",
    "-c",
    help="Instead of paying the account creation fee a subsidized account is created.",
    is_flag=True,
    default=False,
)
@click.option("--import-pub", "-i", help="Load public keys from file.")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def newaccount(
    accountname,
    account,
    owner,
    active,
    memo,
    posting,
    wif,
    create_claimed_account,
    import_pub,
    export,
):
    """Create a new account
    Default setting is that a fee is payed for account creation
    Use --create-claimed-account for free account creation

    Please use keygen and set public keys
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    if import_pub and import_pub != "":
        owner, active, posting, memo = import_pubkeys(import_pub)
        if create_claimed_account:
            tx = hv.create_claimed_account(
                accountname,
                creator=acc,
                owner_key=owner,
                active_key=active,
                memo_key=memo,
                posting_key=posting,
            )
        else:
            tx = hv.create_account(
                accountname,
                creator=acc,
                owner_key=owner,
                active_key=active,
                memo_key=memo,
                posting_key=posting,
            )
    elif owner is None or active is None or memo is None or posting is None:
        import_password = click.prompt(
            "Keys were not given - Passphrase is used to create keys\n New Account Passphrase",
            confirmation_prompt=True,
            hide_input=True,
        )
        if not import_password:
            print("You cannot chose an empty password")
            return
        password = generate_password(import_password, wif)
        if create_claimed_account:
            tx = hv.create_claimed_account(accountname, creator=acc, password=password)
        else:
            tx = hv.create_account(accountname, creator=acc, password=password)
    else:
        if create_claimed_account:
            tx = hv.create_claimed_account(
                accountname,
                creator=acc,
                owner_key=owner,
                active_key=active,
                memo_key=memo,
                posting_key=posting,
            )
        else:
            tx = hv.create_account(
                accountname,
                creator=acc,
                owner_key=owner,
                active_key=active,
                memo_key=memo,
                posting_key=posting,
            )
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("variable", nargs=1, required=False)
@click.argument("value", nargs=1, required=False)
@click.option("--account", "-a", help="setprofile as this user")
@click.option("--pair", "-p", help='"Key=Value" pairs', multiple=True)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def setprofile(variable, value, account, pair, export):
    """Set a variable in an account\'s profile"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    keys = []
    values = []
    if pair:
        for p in pair:
            key, value = p.split("=")
            keys.append(key)
            values.append(value)
    if variable and value:
        keys.append(variable)
        values.append(value)

    profile = Profile(keys, values)

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)

    json_metadata = Profile(acc["json_metadata"] if acc["json_metadata"] else {})
    json_metadata.update(profile)
    tx = acc.update_account_profile(json_metadata)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("variable", nargs=-1, required=True)
@click.option("--account", "-a", help="delprofile as this user")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def delprofile(variable, account, export):
    """Delete a variable in an account's profile"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    json_metadata = Profile(acc["json_metadata"])

    for var in variable:
        json_metadata.remove(var)

    tx = acc.update_account_profile(json_metadata)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("account", nargs=1, required=True)
@click.option(
    "--roles",
    "-r",
    help="Import specified keys (owner, active, posting, memo).",
    default=["active", "posting", "memo"],
)
@click.option(
    "--import-coldcard",
    "-i",
    help="Text file with a BIP85 WIF generated by a coldcard. The imported WIF is used as passphrase",
)
@click.option(
    "--wif",
    "-w",
    help="Defines how many times the password is replaced by its WIF representation for password based keys (default = 0 or 1 when importing a cold card wif).",
)
def importaccount(account, roles, import_coldcard, wif):
    """Import an account using a passphrase"""
    from nectargraphenebase.account import PasswordKey

    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv):
        return
    account = Account(account, blockchain_instance=hv)
    imported = False
    if import_coldcard is None:
        password = click.prompt("Account Passphrase", confirmation_prompt=False, hide_input=True)
        if not password:
            print("You cannot chose an empty Passphrase")
            return
    else:
        password, path = import_coldcard_wif(import_coldcard)
    if wif is not None:
        wif = int(wif)
    elif import_coldcard is not None:
        wif = 1
    else:
        wif = 0

    password = generate_password(password, wif)

    if "owner" in roles:
        owner_key = PasswordKey(account["name"], password, role="owner")
        owner_pubkey = format(owner_key.get_public_key(), hv.prefix)
        if owner_pubkey in [x[0] for x in account["owner"]["key_auths"]]:
            print("Importing owner key!")
            owner_privkey = owner_key.get_private_key()
            hv.wallet.addPrivateKey(owner_privkey)
            imported = True

    if "active" in roles:
        active_key = PasswordKey(account["name"], password, role="active")
        active_pubkey = format(active_key.get_public_key(), hv.prefix)
        if active_pubkey in [x[0] for x in account["active"]["key_auths"]]:
            print("Importing active key!")
            active_privkey = active_key.get_private_key()
            hv.wallet.addPrivateKey(active_privkey)
            imported = True

    if "posting" in roles:
        posting_key = PasswordKey(account["name"], password, role="posting")
        posting_pubkey = format(posting_key.get_public_key(), hv.prefix)
        if posting_pubkey in [x[0] for x in account["posting"]["key_auths"]]:
            print("Importing posting key!")
            posting_privkey = posting_key.get_private_key()
            hv.wallet.addPrivateKey(posting_privkey)
            imported = True

    if "memo" in roles:
        memo_key = PasswordKey(account["name"], password, role="memo")
        memo_pubkey = format(memo_key.get_public_key(), hv.prefix)
        if memo_pubkey == account["memo_key"]:
            print("Importing memo key!")
            memo_privkey = memo_key.get_private_key()
            hv.wallet.addPrivateKey(memo_privkey)
            imported = True

    if not imported:
        print("No matching key(s) found. Password correct?")


@cli.command()
@click.option("--account", "-a", help="The account to updatememokey action for")
@click.option("--key", help="The new memo key")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def updatememokey(account, key, export):
    """Update an account\'s memo key"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    if not key:
        from nectargraphenebase.account import PasswordKey

        pwd = click.prompt(
            "Password for Memo Key Derivation", confirmation_prompt=True, hide_input=True
        )
        memo_key = PasswordKey(account, pwd, "memo")
        key = format(memo_key.get_public_key(), hv.prefix)
        memo_privkey = memo_key.get_private_key()
        if not hv.nobroadcast:
            hv.wallet.addPrivateKey(memo_privkey)
    tx = acc.update_memo_key(key)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("authorperm", nargs=1)
@click.argument("beneficiaries", nargs=-1)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def beneficiaries(authorperm, beneficiaries, export):
    """Set beneficaries"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    c = Comment(authorperm, blockchain_instance=hv)
    account = c["author"]

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return

    options = {
        "author": c["author"],
        "permlink": c["permlink"],
        "max_accepted_payout": c["max_accepted_payout"],
        "allow_votes": c["allow_votes"],
        "allow_curation_rewards": c["allow_curation_rewards"],
    }
    if "percent_hbd" in c:
        options["percent_hbd"] = c["percent_hbd"]

    if isinstance(beneficiaries, tuple) and len(beneficiaries) == 1:
        beneficiaries = beneficiaries[0].split(",")
    beneficiaries_list_sorted = derive_beneficiaries(beneficiaries)
    for b in beneficiaries_list_sorted:
        Account(b["account"], blockchain_instance=hv)
    tx = hv.comment_options(options, authorperm, beneficiaries_list_sorted, account=account)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.option("--account", "-a", help="Your account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def approvewitness(witness, account, export):
    """Approve a witnesses"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.approvewitness(witness, approve=True)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.option("--account", "-a", help="Your account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def disapprovewitness(witness, account, export):
    """Disapprove a witnesses"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.disapprovewitness(witness)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("proxy", nargs=1)
@click.option("--account", "-a", help="Your account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def setproxy(proxy, account, export):
    """Set your witness/proposal system proxy"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.setproxy(proxy, account)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.option("--account", "-a", help="Your account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def delproxy(account, export):
    """Delete your witness/proposal system proxy"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.setproxy("", account)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.option("--witness", help="Witness name")
@click.option("--maximum_block_size", help="Max block size")
@click.option("--account_creation_fee", help="Account creation fee")
@click.option("--hbd_interest_rate", help="HBD interest rate in percent")
@click.option("--url", help="Witness URL")
@click.option("--signing_key", help="Signing Key")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def witnessupdate(
    witness,
    maximum_block_size,
    account_creation_fee,
    hbd_interest_rate,
    url,
    signing_key,
    export,
):
    """Change witness properties"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not witness:
        witness = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    witness = Witness(witness, blockchain_instance=hv)
    props = witness["props"]
    if account_creation_fee is not None:
        props["account_creation_fee"] = str(
            Amount(
                f"{float(account_creation_fee):.3f} {hv.token_symbol}",
                blockchain_instance=hv,
            )
        )
    if maximum_block_size is not None:
        props["maximum_block_size"] = int(maximum_block_size)
    if hbd_interest_rate is not None:
        props["hbd_interest_rate"] = int(float(hbd_interest_rate) * 100)
    tx = witness.update(signing_key or witness["signing_key"], url or witness["url"], props)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def witnessdisable(witness, export):
    """Disable a witness"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not witness:
        witness = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    witness = Witness(witness, blockchain_instance=hv)
    if not witness.is_active:
        print("Cannot disable a disabled witness!")
        return
    props = witness["props"]
    null_key = ("%s" + "1111111111111111111111111111111114T1Anm") % hv.prefix
    tx = witness.update(null_key, witness["url"], props)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.argument("signing_key", nargs=1)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def witnessenable(witness, signing_key, export):
    """Enable a witness"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not witness:
        witness = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    witness = Witness(witness, blockchain_instance=hv)
    props = witness["props"]
    tx = witness.update(signing_key, witness["url"], props)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.argument("pub_signing_key", nargs=1)
@click.option("--maximum_block_size", help="Max block size", default=65536)
@click.option("--account_creation_fee", help="Account creation fee", default=0.1)
@click.option("--hbd_interest_rate", help="HBD interest rate in percent", default=0.0)
@click.option("--url", help="Witness URL", default="")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def witnesscreate(
    witness,
    pub_signing_key,
    maximum_block_size,
    account_creation_fee,
    hbd_interest_rate,
    url,
    export,
):
    """Create a witness"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv):
        return
    props = {
        "account_creation_fee": Amount(
            f"{float(account_creation_fee):.3f} {hv.token_symbol}", blockchain_instance=hv
        ),
        "maximum_block_size": int(maximum_block_size),
        "hbd_interest_rate": int(hbd_interest_rate * 100),
    }

    tx = hv.witness_update(pub_signing_key, url, props, account=witness)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.argument("wif", nargs=1)
@click.option("--account_creation_fee", help="Account creation fee (float)")
@click.option("--account_subsidy_budget", help="Account subisidy per block")
@click.option("--account_subsidy_decay", help="Per block decay of the account subsidy pool")
@click.option("--maximum_block_size", help="Max block size")
@click.option("--hbd_interest_rate", help="HBD interest rate in percent")
@click.option("--new_signing_key", help="Set new signing key (pubkey)")
@click.option("--url", help="Witness URL")
def witnessproperties(
    witness,
    wif,
    account_creation_fee,
    account_subsidy_budget,
    account_subsidy_decay,
    maximum_block_size,
    hbd_interest_rate,
    new_signing_key,
    url,
):
    """Update witness properties of witness WITNESS with the witness signing key WIF"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    props = {}
    if account_creation_fee is not None:
        props["account_creation_fee"] = Amount(
            f"{float(account_creation_fee):.3f} {hv.token_symbol}", blockchain_instance=hv
        )
    if account_subsidy_budget is not None:
        props["account_subsidy_budget"] = int(account_subsidy_budget)
    if account_subsidy_decay is not None:
        props["account_subsidy_decay"] = int(account_subsidy_decay)
    if maximum_block_size is not None:
        props["maximum_block_size"] = int(maximum_block_size)
    if hbd_interest_rate is not None:
        props["hbd_interest_rate"] = int(float(hbd_interest_rate) * 100)
    if new_signing_key is not None:
        props["new_signing_key"] = new_signing_key
    if url is not None:
        props["url"] = url

    tx = hv.witness_set_properties(wif, witness, props)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
@click.argument("wif", nargs=1, required=False)
@click.option(
    "--base", "-b", help="Set base manually, when not set the base is automatically calculated."
)
@click.option(
    "--quote",
    "-q",
    help="HBD/HIVE quote manually; when not set, the base is automatically calculated.",
)
@click.option(
    "--support-peg",
    help="Supports peg adjusting the quote, is overwritten by --set-quote!",
    is_flag=True,
    default=False,
)
def witnessfeed(witness, wif, base, quote, support_peg):
    """Publish price feed for a witness"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if wif is None:
        if not unlock_wallet(hv):
            return
    witness = Witness(witness, blockchain_instance=hv)
    market = Market(blockchain_instance=hv)
    # Prefer HBD exchange rate (Hive-only)
    if "hbd_exchange_rate" in witness:
        old_base = witness["hbd_exchange_rate"]["base"]
        old_quote = witness["hbd_exchange_rate"]["quote"]
        last_published_price = Price(witness["hbd_exchange_rate"], blockchain_instance=hv)
    else:
        # Fallback to current median price if no prior feed
        median = hv.get_current_median_history()
        old_base = median["base"]
        old_quote = median["quote"]
        last_published_price = Price(median, blockchain_instance=hv)

    hive_usd = None
    print(
        "Old price {:.3f} (base: {}, quote {})".format(
            float(last_published_price), old_base, old_quote
        )
    )
    if quote is None and not support_peg:
        quote = Amount("1.000 %s" % hv.token_symbol, blockchain_instance=hv)
    elif quote is None:
        latest_price = market.ticker()["latest"]
        if hive_usd is None:
            hive_usd = market.hive_usd_implied()
        hbd_usd = float(latest_price.as_base(hv.backed_token_symbol)) * hive_usd
        quote = Amount(1.0 / hbd_usd, hv.token_symbol, blockchain_instance=hv)
    else:
        if str(quote[-5:]).upper() == hv.token_symbol:
            quote = Amount(quote, blockchain_instance=hv)
        else:
            quote = Amount(quote, hv.token_symbol, blockchain_instance=hv)
    if base is None:
        if hive_usd is None:
            hive_usd = market.hive_usd_implied()
        base = Amount(hive_usd, hv.backed_token_symbol, blockchain_instance=hv)
    else:
        if str(quote[-3:]).upper() == hv.backed_token_symbol:
            base = Amount(base, blockchain_instance=hv)
        else:
            base = Amount(base, hv.backed_token_symbol, blockchain_instance=hv)
    new_price = Price(base=base, quote=quote, blockchain_instance=hv)
    print(f"New price {float(new_price):.3f} (base: {base}, quote {quote})")
    if wif is not None:
        props = {"hbd_exchange_rate": new_price}
        tx = hv.witness_set_properties(wif, witness["owner"], props)
    else:
        tx = witness.feed_publish(base, quote=quote)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("witness", nargs=1)
def witness(witness):
    """List witness information"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    witness = Witness(witness, blockchain_instance=hv)
    witness_json = witness.json()
    witness_schedule = hv.get_witness_schedule()
    config = hv.get_config()
    if "VIRTUAL_SCHEDULE_LAP_LENGTH2" in config:
        lap_length = int(config["VIRTUAL_SCHEDULE_LAP_LENGTH2"])
    elif "HIVE_VIRTUAL_SCHEDULE_LAP_LENGTH2" in config:
        lap_length = int(config["HIVE_VIRTUAL_SCHEDULE_LAP_LENGTH2"])
    else:
        lap_length = int(
            config.get(
                "HIVE_VIRTUAL_SCHEDULE_LAP_LENGTH2", config.get("VIRTUAL_SCHEDULE_LAP_LENGTH2")
            )
        )
    rank = 0
    active_rank = 0
    found = False
    witnesses_list = WitnessesRankedByVote(limit=250, blockchain_instance=hv)
    vote_sum = witnesses_list.get_votes_sum()
    for w in witnesses_list:
        rank += 1
        if w.is_active:
            active_rank += 1
        if w["owner"] == witness["owner"]:
            found = True
            break
    virtual_time_to_block_num = int(witness_schedule["num_scheduled_witnesses"]) / (
        lap_length / (vote_sum + 1)
    )
    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    for key in sorted(witness_json):
        value = witness_json[key]
        if key in ["props", "hbd_exchange_rate"]:
            value = json.dumps(value, indent=4)
        t.add_row([key, value])
    if found:
        t.add_row(["rank", rank])
        t.add_row(["active_rank", active_rank])
    virtual_diff = int(witness_json["virtual_scheduled_time"]) - int(
        witness_schedule["current_virtual_time"]
    )
    block_diff_est = virtual_diff * virtual_time_to_block_num
    if active_rank > 20:
        t.add_row(["virtual_time_diff", virtual_diff])
        t.add_row(["block_diff_est", int(block_diff_est)])
        next_block_s = int(block_diff_est) * 3
        next_block_min = next_block_s / 60
        next_block_h = next_block_min / 60
        next_block_d = next_block_h / 24
        time_diff_est = ""
        if next_block_d > 1:
            time_diff_est = "%.2f days" % next_block_d
        elif next_block_h > 1:
            time_diff_est = "%.2f hours" % next_block_h
        elif next_block_min > 1:
            time_diff_est = "%.2f minutes" % next_block_min
        else:
            time_diff_est = "%.2f seconds" % next_block_s
        t.add_row(["time_diff_est", time_diff_est])
    print(t)


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--limit", help="How many witnesses should be shown", default=100)
def witnesses(account, limit):
    """List witnesses"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if account:
        account = Account(account, blockchain_instance=hv)
        account_name = account["name"]
        if account["proxy"] != "":
            account_name = account["proxy"]
            account_type = "Proxy"
        else:
            account_type = "Account"
        witnesses_list = WitnessesVotedByAccount(account_name, blockchain_instance=hv)
        print("%s: @%s (%d of 30)" % (account_type, account_name, len(witnesses_list)))
    else:
        witnesses_list = WitnessesRankedByVote(limit=limit, blockchain_instance=hv)
    witnesses_list.printAsTable()


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--direction", default=None, help="in or out")
@click.option("--outgoing", "-o", help="Show outgoing votes", is_flag=True, default=False)
@click.option("--incoming", "-i", help="Show incoming votes", is_flag=True, default=False)
@click.option(
    "--days", "-d", default=2.0, help="Limit shown vote history by this amount of days (default: 2)"
)
@click.option("--export", "-e", default=None, help="Export results to TXT-file")
def votes(account, direction, outgoing, incoming, days, export):
    """List outgoing/incoming account votes"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if direction is None and not incoming and not outgoing:
        direction = "in"
    limit_time = datetime.now(timezone.utc) - timedelta(days=days)
    out_votes_str = ""
    in_votes_str = ""
    if direction == "out" or outgoing:
        votes_list = AccountVotes(account, start=limit_time, blockchain_instance=hv)
        out_votes_str = votes_list.printAsTable(start=limit_time, return_str=True)
    if direction == "in" or incoming:
        account = Account(account, blockchain_instance=hv)
        votes_list = []
        for v in account.history(start=limit_time, only_ops=["vote"]):
            vote = Vote(v, blockchain_instance=hv)
            vote.refresh()
            votes_list.append(vote)
        active_votes = ActiveVotes(votes_list, blockchain_instance=hv)
        in_votes_str = active_votes.printAsTable(votee=account["name"], return_str=True)
    if export:
        with open(export, "w") as w:
            w.write(out_votes_str)
            w.write("\n")
            w.write(in_votes_str)
    else:
        print(out_votes_str)
        print(in_votes_str)


@cli.command()
@click.argument("authorperm", nargs=1, required=False)
@click.option("--account", "-a", help="Show only curation for this account")
@click.option("--limit", "-m", help="Show only the first minutes")
@click.option("--min-vote", "-v", help="Show only votes higher than the given value")
@click.option("--max-vote", "-w", help="Show only votes lower than the given value")
@click.option(
    "--min-performance",
    "-x",
    help="Show only votes with performance higher than the given value in HBD",
)
@click.option(
    "--max-performance",
    "-y",
    help="Show only votes with performance lower than the given value in HBD",
)
@click.option(
    "--payout", default=None, help="Show the curation for a potential payout in HBD as float"
)
@click.option("--export", "-e", default=None, help="Export results to HTML-file")
@click.option("--short", "-s", is_flag=True, default=False, help="Show only Curation without sum")
@click.option("--length", "-l", help="Limits the permlink character length", default=None)
@click.option(
    "--permlink", "-p", help="Show the permlink for each entry", is_flag=True, default=False
)
@click.option("--title", "-t", help="Show the title for each entry", is_flag=True, default=False)
@click.option(
    "--days",
    "-d",
    default=7.0,
    help="Limit shown rewards by this amount of days (default: 7), max is 7 days.",
)
def curation(
    authorperm,
    account,
    limit,
    min_vote,
    max_vote,
    min_performance,
    max_performance,
    payout,
    export,
    short,
    length,
    permlink,
    title,
    days,
):
    """Lists curation rewards of all votes for authorperm

    When authorperm is empty or "all", the curation rewards
    for all account votes are shown.

    authorperm can also be a number. e.g. 5 is equivalent to
    the fifth account vote in the given time duration (default is 7 days)
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    try:
        HP_symbol = "HP"
        if authorperm is None:
            authorperm = "all"
        if account is None and authorperm != "all":
            show_all_voter = True
        else:
            show_all_voter = False
        if authorperm == "all" or authorperm.isdigit():
            if not account:
                account = hv.config["default_account"]
            _days = min(float(days), 7.0)
            limit_time = datetime.now(timezone.utc) - timedelta(days=_days)
            votes_list = AccountVotes(account, start=limit_time, blockchain_instance=hv)
            authorperm_list = [vote.authorperm for vote in votes_list]
            if authorperm.isdigit():
                if len(authorperm_list) < int(authorperm):
                    raise ValueError(
                        "Authorperm id must be lower than %d" % (len(authorperm_list) + 1)
                    )
                authorperm_list = [authorperm_list[int(authorperm) - 1]]
                all_posts = False
            else:
                all_posts = True
        else:
            authorperm_list = [authorperm]
            all_posts = False
        if (all_posts) and permlink:
            t = PrettyTable(
                [
                    "Author",
                    "permlink",
                    "Voting time",
                    "Vote",
                    "Early vote loss",
                    "Curation",
                    "Performance",
                ]
            )
            t.align = "l"
        elif (all_posts) and title:
            t = PrettyTable(
                [
                    "Author",
                    "permlink",
                    "Voting time",
                    "Vote",
                    "Early vote loss",
                    "Curation",
                    "Performance",
                ]
            )
            t.align = "l"
        elif all_posts:
            t = PrettyTable(
                ["Author", "Voting time", "Vote", "Early vote loss", "Curation", "Performance"]
            )
            t.align = "l"
        elif (export) and permlink:
            t = PrettyTable(
                [
                    "Author",
                    "permlink",
                    "Voter",
                    "Voting time",
                    "Vote",
                    "Early vote loss",
                    "Curation",
                    "Performance",
                ]
            )
            t.align = "l"
        elif (export) and title:
            t = PrettyTable(
                [
                    "Author",
                    "permlink",
                    "Voter",
                    "Voting time",
                    "Vote",
                    "Early vote loss",
                    "Curation",
                    "Performance",
                ]
            )
            t.align = "l"
        elif export:
            t = PrettyTable(
                [
                    "Author",
                    "Voter",
                    "Voting time",
                    "Vote",
                    "Early vote loss",
                    "Curation",
                    "Performance",
                ]
            )
            t.align = "l"
        else:
            t = PrettyTable(
                ["Voter", "Voting time", "Vote", "Early vote loss", "Curation", "Performance"]
            )
            t.align = "l"
        index = 0
        for authorperm in authorperm_list:
            index += 1
            comment = Comment(authorperm, blockchain_instance=hv)
            if payout is not None and comment.is_pending():
                payout = float(payout)
            elif payout is not None:
                payout = None
            curation_rewards_HBD = comment.get_curation_rewards(
                pending_payout_hbd=True, pending_payout_value=payout
            )
            curation_rewards_HP = comment.get_curation_rewards(
                pending_payout_hbd=False, pending_payout_value=payout
            )
            rows = []
            sum_curation = [0, 0, 0, 0]
            max_curation = [0, 0, 0, 0, 0, 0]
            highest_vote = [0, 0, 0, 0, 0, 0]
            for vote in comment.get_votes():
                vote_time = vote["time"]

                vote_HBD = hv.rshares_to_token_backed_dollar(int(vote["rshares"]))
                curation_HBD = curation_rewards_HBD["active_votes"][vote["voter"]]
                curation_HP = curation_rewards_HP["active_votes"][vote["voter"]]
                if vote_HBD > 0:
                    penalty = (comment.get_curation_penalty(vote_time=vote_time)) * vote_HBD
                    performance = float(curation_HBD) / vote_HBD * 100
                else:
                    performance = 0
                    penalty = 0
                vote_befor_min = ((vote_time) - comment["created"]).total_seconds() / 60
                sum_curation[0] += vote_HBD
                sum_curation[1] += penalty
                sum_curation[2] += float(curation_HP)
                sum_curation[3] += float(curation_HBD)
                row = [
                    vote["voter"],
                    vote_befor_min,
                    vote_HBD,
                    penalty,
                    float(curation_HP),
                    performance,
                ]

                rows.append(row)
            sortedList = sorted(rows, key=lambda row: row[1], reverse=False)
            new_row = []
            new_row2 = []
            voter = []
            voter2 = []
            if (all_posts or export) and permlink:
                if length:
                    new_row = [comment.author, comment.permlink[: int(length)]]
                else:
                    new_row = [comment.author, comment.permlink]
                new_row2 = ["", ""]
            elif (all_posts or export) and title:
                if length:
                    new_row = [comment.author, comment.title[: int(length)]]
                else:
                    new_row = [comment.author, comment.title]
                new_row2 = ["", ""]
            elif all_posts or export:
                new_row = [comment.author]
                new_row2 = [""]
            if not all_posts:
                voter = [""]
                voter2 = [""]
            found_voter = False
            for row in sortedList:
                if limit is not None and row[1] > float(limit):
                    continue
                if min_vote is not None and float(row[2]) < float(min_vote):
                    continue
                if max_vote is not None and float(row[2]) > float(max_vote):
                    continue
                if min_performance is not None and float(row[5]) < float(min_performance):
                    continue
                if max_performance is not None and float(row[5]) > float(max_performance):
                    continue
                if row[-1] > max_curation[-1]:
                    max_curation = row
                if row[2] > highest_vote[2]:
                    highest_vote = row
                if show_all_voter or account == row[0]:
                    if not all_posts:
                        voter = [row[0]]
                    if all_posts:
                        new_row[0] = "%d. %s" % (index, comment.author)
                    if not found_voter:
                        found_voter = True
                    t.add_row(
                        new_row
                        + voter
                        + [
                            "%.1f min" % row[1],
                            f"{float(row[2]):.3f} {hv.backed_token_symbol}",
                            f"{float(row[3]):.3f} {hv.backed_token_symbol}",
                            f"{row[4]:.3f} {HP_symbol}",
                            "%.1f %%" % (row[5]),
                        ]
                    )
                    if len(authorperm_list) == 1:
                        new_row = new_row2
            if not short and found_voter:
                t.add_row(new_row2 + voter2 + ["", "", "", "", ""])
                if sum_curation[0] > 0:
                    curation_sum_percentage = sum_curation[3] / sum_curation[0] * 100
                else:
                    curation_sum_percentage = 0
                sum_line = new_row2 + voter2
                sum_line[-1] = "High. vote"

                t.add_row(
                    sum_line
                    + [
                        "%.1f min" % highest_vote[1],
                        f"{float(highest_vote[2]):.3f} {hv.backed_token_symbol}",
                        f"{float(highest_vote[3]):.3f} {hv.backed_token_symbol}",
                        f"{highest_vote[4]:.3f} {HP_symbol}",
                        "%.1f %%" % (highest_vote[5]),
                    ]
                )
                sum_line[-1] = "High. Cur."
                t.add_row(
                    sum_line
                    + [
                        "%.1f min" % max_curation[1],
                        f"{float(max_curation[2]):.3f} {hv.backed_token_symbol}",
                        f"{float(max_curation[3]):.3f} {hv.backed_token_symbol}",
                        f"{max_curation[4]:.3f} {HP_symbol}",
                        "%.1f %%" % (max_curation[5]),
                    ]
                )
                sum_line[-1] = "Sum"
                t.add_row(
                    sum_line
                    + [
                        "-",
                        f"{sum_curation[0]:.3f} {hv.backed_token_symbol}",
                        f"{sum_curation[1]:.3f} {hv.backed_token_symbol}",
                        f"{sum_curation[2]:.3f} {HP_symbol}",
                        "%.2f %%" % curation_sum_percentage,
                    ]
                )
                if all_posts or export:
                    t.add_row(new_row2 + voter2 + ["-", "-", "-", "-", "-"])
            if not (all_posts or export):
                print("curation for %s" % (authorperm))
                print(t)
        if export:
            with open(export, "w") as w:
                w.write(str(t.get_html_string()))
        elif all_posts:
            print("curation for @%s" % account)
            print(t)
    except Exception as e:
        print(str(e))
        raise e


@cli.command()
@click.argument("accounts", nargs=-1, required=False)
@click.option("--only-sum", "-s", help="Show only the sum", is_flag=True, default=False)
@click.option("--post", "-p", help="Show post payout", is_flag=True, default=False)
@click.option("--comment", "-c", help="Show comments payout", is_flag=True, default=False)
@click.option("--curation", "-v", help="Shows  curation", is_flag=True, default=False)
@click.option("--length", "-l", help="Limits the permlink character length", default=None)
@click.option("--author", "-a", help="Show the author for each entry", is_flag=True, default=False)
@click.option(
    "--permlink", "-e", help="Show the permlink for each entry", is_flag=True, default=False
)
@click.option("--title", "-t", help="Show the title for each entry", is_flag=True, default=False)
@click.option(
    "--days", "-d", default=7.0, help="Limit shown rewards by this amount of days (default: 7)"
)
@click.option(
    "--witness",
    "-w",
    help="Show witness (producer) rewards",
    is_flag=True,
    default=False,
)
def rewards(
    accounts, only_sum, post, comment, curation, length, author, permlink, title, days, witness
):
    """Lists received rewards"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not accounts:
        accounts = [hv.config["default_account"]]
    if not witness and not comment and not curation and not post:
        post = True
        permlink = True
    if days < 0:
        days = 1

    now = datetime.now(timezone.utc)
    limit_time = now - timedelta(days=days)
    hp_symbol = f"{hv.token_symbol[0]}P"
    current_median_history = hv.get_current_median_history()
    median_price_fallback = (
        float(Price(current_median_history, blockchain_instance=hv))
        if current_median_history
        else 0.0
    )

    def _render_witness_rewards(account_obj, median_price_obj):
        t = PrettyTable(["Received", hp_symbol, "Invested USD"])
        t.align = "l"
        rows = []
        sum_hp = 0.0
        sum_invested = 0.0
        start_op = account_obj.estimate_virtual_op_num(limit_time)
        if start_op > 0:
            start_op -= 1
        progress_length = (account_obj.virtual_op_count() - start_op) / 1000
        try:
            median_price_value = float(median_price_obj)
        except Exception:
            median_price_value = median_price_fallback
        with click.progressbar(
            account_obj.history(start=start_op, use_block_num=False),
            length=progress_length,
        ) as witness_hist:
            for v in witness_hist:
                timestamp = v.get("timestamp")
                if isinstance(timestamp, (int, float)):
                    received = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                else:
                    try:
                        received = formatTimeString(timestamp)
                        if isinstance(received, str):
                            received = datetime.fromisoformat(received.replace("Z", "+00:00"))
                        if received.tzinfo is None:
                            received = received.replace(tzinfo=timezone.utc)
                    except Exception as e:
                        if hv.debug:
                            print(f"Skipping entry due to timestamp parsing error: {e}")
                        continue
                if received < limit_time:
                    continue
                if v["type"] != "producer_reward":
                    continue
                reward_vests = hv.vests_to_token_power(
                    Amount(v["vesting_shares"], blockchain_instance=hv)
                )
                reward_hp = float(reward_vests)
                invested_usd = reward_hp * median_price_value
                sum_hp += reward_hp
                sum_invested += invested_usd
                if only_sum:
                    continue
                received_days = (now - received).total_seconds() / 86400.0
                rows.append((received_days, reward_hp, invested_usd))
        if not only_sum:
            sorted_rows = sorted(rows, key=lambda row: row[0])
            for days_ago, reward_hp, invested_usd in sorted_rows:
                t.add_row(
                    [
                        f"{days_ago:.1f} days",
                        f"{reward_hp:.3f} {hp_symbol}",
                        f"{invested_usd:.2f} $",
                    ]
                )
            if sorted_rows:
                t.add_row(["", "", ""])
        t.add_row(
            [
                "Sum",
                f"{sum_hp:.3f} {hp_symbol}",
                f"{sum_invested:.2f} $",
            ]
        )
        message = "\nShowing witness rewards for @%s" % account_obj.name
        print(message)
        print(t)

    for account in accounts:
        sum_reward = [0, 0, 0, 0, 0]
        account = Account(account, blockchain_instance=hv)
        median_price = Price(hv.get_current_median_history(), blockchain_instance=hv)
        if witness:
            _render_witness_rewards(account, median_price)
            continue
        m = Market(blockchain_instance=hv)
        latest = m.ticker()["latest"]
        if author and permlink:
            t = PrettyTable(
                [
                    "Author",
                    "Permlink",
                    "Payout",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif author and title:
            t = PrettyTable(
                [
                    "Author",
                    "Title",
                    "Payout",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif author:
            t = PrettyTable(
                [
                    "Author",
                    "Payout",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif not author and permlink:
            t = PrettyTable(
                [
                    "Permlink",
                    "Payout",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif not author and title:
            t = PrettyTable(
                [
                    "Title",
                    "Payout",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        else:
            t = PrettyTable(
                [
                    "Received",
                    hv.backed_token_symbol,
                    f"{hv.token_symbol[0]}P + {hv.token_symbol}",
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        t.align = "l"
        rows = []
        start_op = account.estimate_virtual_op_num(limit_time)
        if start_op > 0:
            start_op -= 1
        only_ops = ["author_reward", "curation_reward"]
        progress_length = (account.virtual_op_count() - start_op) / 1000
        with click.progressbar(
            account.history(start=start_op, use_block_num=False, only_ops=only_ops),
            length=progress_length,
        ) as comment_hist:
            for v in comment_hist:
                if not curation and v["type"] == "curation_reward":
                    continue
                if not post and not comment and v["type"] == "author_reward":
                    continue
                if v["type"] == "author_reward":
                    c = Comment(v, blockchain_instance=hv)
                    try:
                        c.refresh()
                    except exceptions.ContentDoesNotExistsException:
                        continue
                    if not post and not c.is_comment():
                        continue
                    if not comment and c.is_comment():
                        continue
                    payout_HBD = Amount("0.000 HBD", blockchain_instance=hv)
                    payout_HIVE = Amount("0.000 HIVE", blockchain_instance=hv)
                    if "hbd_payout" in v:
                        payout_HBD = Amount(v["hbd_payout"], blockchain_instance=hv)
                    if "hive_payout" in v:
                        payout_HIVE = Amount(v["hive_payout"], blockchain_instance=hv)
                    sum_reward[0] += float(payout_HBD)
                    sum_reward[1] += float(payout_HIVE)
                    payout_VESTS = hv.vests_to_token_power(
                        Amount(v["vesting_payout"], blockchain_instance=hv)
                    )
                    sum_reward[2] += float(payout_VESTS)
                    liquid_USD = float(payout_HBD) / float(latest) * float(median_price) + float(
                        payout_HIVE
                    ) * float(median_price)
                    sum_reward[3] += liquid_USD
                    invested_USD = float(payout_VESTS) * float(median_price)
                    sum_reward[4] += invested_USD
                    if c.is_comment():
                        permlink_row = c.parent_permlink
                    else:
                        if title:
                            permlink_row = c.title
                        else:
                            permlink_row = c.permlink
                    rows.append(
                        [
                            c["author"],
                            permlink_row,
                            (
                                (now - formatTimeString(v["timestamp"])).total_seconds()
                                / 60
                                / 60
                                / 24
                            ),
                            (payout_HBD),
                            (payout_HIVE),
                            (payout_VESTS),
                            (liquid_USD),
                            (invested_USD),
                        ]
                    )
                elif v["type"] == "curation_reward":
                    reward = Amount(v["reward"], blockchain_instance=hv)
                    payout_VESTS = hv.vests_to_token_power(reward)
                    liquid_USD = 0
                    invested_USD = float(payout_VESTS) * float(median_price)
                    sum_reward[2] += float(payout_VESTS)
                    sum_reward[4] += invested_USD
                    comment_author = v.get("comment_author", v.get("author", ""))
                    comment_permlink = v.get("comment_permlink", v.get("permlink", ""))
                    permlink_row = comment_permlink
                    if title and comment_author and comment_permlink:
                        try:
                            c = Comment(
                                construct_authorperm(comment_author, comment_permlink),
                                blockchain_instance=hv,
                            )
                            permlink_row = c.title
                        except Exception:
                            permlink_row = comment_permlink
                    rows.append(
                        [
                            comment_author,
                            permlink_row,
                            (
                                (now - formatTimeString(v["timestamp"])).total_seconds()
                                / 60
                                / 60
                                / 24
                            ),
                            0.000,
                            0.000,
                            payout_VESTS,
                            (liquid_USD),
                            (invested_USD),
                        ]
                    )
        sortedList = sorted(rows, key=lambda row: row[2], reverse=False)
        if only_sum:
            sortedList = []
        for row in sortedList:
            if length:
                permlink_row = row[1][: int(length)]
            else:
                permlink_row = row[1]
            if author and (permlink or title):
                t.add_row(
                    [
                        row[0],
                        permlink_row,
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % (float(row[4]) + float(row[5])),
                        "%.2f $" % (row[6]),
                        "%.2f $" % (row[7]),
                    ]
                )
            elif author and not (permlink or title):
                t.add_row(
                    [
                        row[0],
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % (float(row[4]) + float(row[5])),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )
            elif not author and (permlink or title):
                t.add_row(
                    [
                        permlink_row,
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % (float(row[4]) + float(row[5])),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )
            else:
                t.add_row(
                    [
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % (float(row[4]) + float(row[5])),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )

        if author and (permlink or title):
            if not only_sum:
                t.add_row(["", "", "", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    "-",
                    "-",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1] + sum_reward[2]:.2f} {hv.token_symbol[0]}P",
                    "%.2f $" % (sum_reward[3]),
                    "%.2f $" % (sum_reward[4]),
                ]
            )
        elif not author and not (permlink or title):
            t.add_row(["", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1] + sum_reward[2]:.2f} {hv.token_symbol[0]}P",
                    "%.2f $" % (sum_reward[2]),
                    "%.2f $" % (sum_reward[3]),
                ]
            )
        else:
            t.add_row(["", "", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    "-",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1] + sum_reward[2]:.2f} {hv.token_symbol[0]}P",
                    "%.2f $" % (sum_reward[3]),
                    "%.2f $" % (sum_reward[4]),
                ]
            )
        message = "\nShowing "
        if post:
            if comment + curation == 0:
                message += "post "
            elif comment + curation == 1:
                message += "post and "
            else:
                message += "post, "
        if comment:
            if curation == 0:
                message += "comment "
            else:
                message += "comment and "
        if curation:
            message += "curation "
        message += "rewards for @%s" % account.name
        print(message)
        print(t)


@cli.command()
@click.argument("accounts", nargs=-1, required=False)
@click.option("--only-sum", "-s", help="Show only the sum", is_flag=True, default=False)
@click.option("--post", "-p", help="Show pending post payout", is_flag=True, default=False)
@click.option("--comment", "-c", help="Show pending comments payout", is_flag=True, default=False)
@click.option("--curation", "-v", help="Shows  pending curation", is_flag=True, default=False)
@click.option("--length", "-l", help="Limits the permlink character length", default=None)
@click.option("--author", "-a", help="Show the author for each entry", is_flag=True, default=False)
@click.option(
    "--permlink", "-e", help="Show the permlink for each entry", is_flag=True, default=False
)
@click.option("--title", "-t", help="Show the title for each entry", is_flag=True, default=False)
@click.option(
    "--days",
    "-d",
    default=7.0,
    help="Limit shown rewards by this amount of days (default: 7), max is 7 days.",
)
@click.option(
    "--from",
    "-f",
    "_from",
    default=0.0,
    help="Start day from which on rewards are shown (default: 0), max is 7 days.",
)
def pending(
    accounts, only_sum, post, comment, curation, length, author, permlink, title, days, _from
):
    """Lists pending rewards"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not accounts:
        accounts = [hv.config["default_account"]]
    if not comment and not curation and not post:
        post = True
        permlink = True
    if days < 0:
        days = 1
    if days > 7:
        days = 7
    if _from < 0:
        _from = 0
    if _from > 7:
        _from = 7
    if _from + days > 7:
        days = 7 - _from
    sp_symbol = "HP"

    max_limit_time = datetime.now(timezone.utc) - timedelta(days=7)
    limit_time = datetime.now(timezone.utc) - timedelta(days=_from + days)
    start_time = datetime.now(timezone.utc) - timedelta(days=_from)
    for account in accounts:
        sum_reward = [0, 0, 0, 0]
        account = Account(account, blockchain_instance=hv)
        median_price = Price(hv.get_current_median_history(), blockchain_instance=hv)
        m = Market(blockchain_instance=hv)
        latest = m.ticker()["latest"]
        if author and permlink:
            t = PrettyTable(
                [
                    "Author",
                    "Permlink",
                    "Cashout",
                    hv.backed_token_symbol,
                    sp_symbol,
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif author and title:
            t = PrettyTable(
                [
                    "Author",
                    "Title",
                    "Cashout",
                    hv.backed_token_symbol,
                    sp_symbol,
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif author:
            t = PrettyTable(
                [
                    "Author",
                    "Cashout",
                    hv.backed_token_symbol,
                    sp_symbol,
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif not author and permlink:
            t = PrettyTable(
                [
                    "Permlink",
                    "Cashout",
                    hv.backed_token_symbol,
                    sp_symbol,
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        elif not author and title:
            t = PrettyTable(
                [
                    "Title",
                    "Cashout",
                    hv.backed_token_symbol,
                    sp_symbol,
                    "Liquid USD",
                    "Invested USD",
                ]
            )
        else:
            t = PrettyTable(
                ["Cashout", hv.backed_token_symbol, sp_symbol, "Liquid USD", "Invested USD"]
            )
        t.align = "l"
        rows = []
        c_list = {}
        start_op = account.estimate_virtual_op_num(limit_time)
        stop_op = account.estimate_virtual_op_num(start_time)
        if start_op > 0:
            start_op -= 1
        progress_length = (stop_op - start_op) / 1000
        with click.progressbar(
            map(
                Comment,
                account.history(
                    start=start_op, stop=stop_op, use_block_num=False, only_ops=["comment"]
                ),
            ),
            length=progress_length,
        ) as comment_hist:
            for v in comment_hist:
                try:
                    v.refresh()
                except exceptions.ContentDoesNotExistsException:
                    continue
                author_reward = v.get_author_rewards()
                if float(author_reward["total_payout_HBD"]) < 0.001:
                    continue
                if v.permlink in c_list:
                    continue
                c_list[v.permlink] = 1
                if not v.is_pending():
                    continue
                if not post and not v.is_comment():
                    continue
                if not comment and v.is_comment():
                    continue
                if v["author"] != account["name"]:
                    continue
                payout_HBD = author_reward["payout_HBD"]
                sum_reward[0] += float(payout_HBD)
                payout_HP = author_reward["payout_HP"]
                sum_reward[1] += float(payout_HP)
                liquid_USD = (
                    float(author_reward["payout_HBD"]) / float(latest) * float(median_price)
                )
                sum_reward[2] += liquid_USD
                invested_USD = float(author_reward["payout_HP"]) * float(median_price)
                sum_reward[3] += invested_USD
                if v.is_comment():
                    permlink_row = v.permlink
                else:
                    if title:
                        permlink_row = v.title
                    else:
                        permlink_row = v.permlink
                rows.append(
                    [
                        v["author"],
                        permlink_row,
                        ((v["created"] - max_limit_time).total_seconds() / 60 / 60 / 24),
                        (payout_HBD),
                        (payout_HP),
                        (liquid_USD),
                        (invested_USD),
                    ]
                )
        if curation:
            votes = AccountVotes(account, start=limit_time, stop=start_time, blockchain_instance=hv)
            for vote in votes:
                authorperm = construct_authorperm(vote["author"], vote["permlink"])
                try:
                    c = Comment(authorperm, blockchain_instance=hv)
                except exceptions.ContentDoesNotExistsException:
                    continue
                rewards_data = c.get_curation_rewards()
                if not rewards_data["pending_rewards"]:
                    continue
                days_to_payout = (c["created"] - max_limit_time).total_seconds() / 60 / 60 / 24
                if days_to_payout < 0:
                    continue
                payout_HP = rewards_data["active_votes"][account["name"]]
                liquid_USD = 0
                invested_USD = float(payout_HP) * float(median_price)
                sum_reward[1] += float(payout_HP)
                sum_reward[3] += invested_USD
                if title:
                    permlink_row = c.title
                else:
                    permlink_row = c.permlink
                rows.append(
                    [
                        c["author"],
                        permlink_row,
                        days_to_payout,
                        0.000,
                        payout_HP,
                        (liquid_USD),
                        (invested_USD),
                    ]
                )
        sortedList = sorted(rows, key=lambda row: row[2], reverse=True)
        if only_sum:
            sortedList = []
        for row in sortedList:
            if length:
                permlink_row = row[1][: int(length)]
            else:
                permlink_row = row[1]
            if author and (permlink or title):
                t.add_row(
                    [
                        row[0],
                        permlink_row,
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % float(row[4]),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )
            elif author and not (permlink or title):
                t.add_row(
                    [
                        row[0],
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % float(row[4]),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )
            elif not author and (permlink or title):
                t.add_row(
                    [
                        permlink_row,
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % float(row[4]),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )
            else:
                t.add_row(
                    [
                        "%.1f days" % row[2],
                        "%.3f" % float(row[3]),
                        "%.3f" % float(row[4]),
                        "%.2f $" % (row[5]),
                        "%.2f $" % (row[6]),
                    ]
                )

        if author and (permlink or title):
            if not only_sum:
                t.add_row(["", "", "", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    "-",
                    "-",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1]:.2f} {sp_symbol}",
                    "%.2f $" % (sum_reward[2]),
                    "%.2f $" % (sum_reward[3]),
                ]
            )
        elif not author and not (permlink or title):
            t.add_row(["", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1]:.2f} {sp_symbol}",
                    "%.2f $" % (sum_reward[2]),
                    "%.2f $" % (sum_reward[3]),
                ]
            )
        else:
            t.add_row(["", "", "", "", "", ""])
            t.add_row(
                [
                    "Sum",
                    "-",
                    f"{sum_reward[0]:.2f} {hv.backed_token_symbol}",
                    f"{sum_reward[1]:.2f} {sp_symbol}",
                    "%.2f $" % (sum_reward[2]),
                    "%.2f $" % (sum_reward[3]),
                ]
            )
        message = "\nShowing pending "
        if post:
            if comment + curation == 0:
                message += "post "
            elif comment + curation == 1:
                message += "post and "
            else:
                message += "post, "
        if comment:
            if curation == 0:
                message += "comment "
            else:
                message += "comment and "
        if curation:
            message += "curation "
        message += "rewards for @%s" % account.name
        print(message)
        print(t)


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--reward_sbd", help="Amount of HBD you would like to claim", default=0)
@click.option("--reward_vests", help="Amount of VESTS you would like to claim", default=0)
@click.option("--claim_all_sbd", help="Claim all HBD, overwrites reward_sbd", is_flag=True)
@click.option("--claim_all_vests", help="Claim all VESTS, overwrites reward_vests", is_flag=True)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def claimreward(
    account,
    reward_sbd,
    reward_vests,
    claim_all_sbd,
    claim_all_vests,
    export,
):
    """Claim reward balances

    By default, this will claim ``all`` outstanding balances.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    acc = Account(account, blockchain_instance=hv)
    r = acc.balances["rewards"]
    if len(r) == 3 and r[0].amount + r[1].amount + r[2].amount == 0:
        print("Nothing to claim.")
        return
    elif len(r) == 2 and r[0].amount + r[1].amount:
        print("Nothing to claim.")
        return
    if not unlock_wallet(hv):
        return
    if claim_all_sbd:
        reward_sbd = r[0]
    if claim_all_vests:
        reward_vests = r[1]

    tx = acc.claim_reward_balance(reward_sbd, reward_vests)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option(
    "--limit", "-l", help="Defines how many ops should be printed (default=10)", default=10
)
@click.option(
    "--sort", "-s", help="Defines the printing sorting, 1 ->, -1 <- (default=-1)", default=-1
)
@click.option("--max-length", "-m", help="Maximum printed string length", default=80)
@click.option(
    "--virtual-ops", "-v", help="When set, virtual ops are also shown", is_flag=True, default=False
)
@click.option(
    "--only-ops",
    "-o",
    help="Included komma seperated list of op types, which limits the shown operations. When set, virtual-ops is always set to true",
)
@click.option(
    "--exclude-ops",
    "-e",
    help="Excluded komma seperated list of op types, which limits the shown operations.",
)
@click.option("--json-file", "-j", help="When set, the results are written into a json file")
def history(account, limit, sort, max_length, virtual_ops, only_ops, exclude_ops, json_file):
    """Returns account history operations as table"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        if "default_account" in hv.config:
            account = hv.config["default_account"]
    account = Account(account, blockchain_instance=hv)
    t = PrettyTable(["Index", "Type", "Hist op"])
    t.align = "l"
    t._max_width = {"Hist op": max_length}
    cnt = 0
    batch_size = 1000
    if batch_size > int(limit) + 1 and int(limit) > 0:
        batch_size = int(limit) + 1
    if only_ops is None:
        only_ops = []
    else:
        only_ops = only_ops.split(",")
    if exclude_ops is None:
        exclude_ops = []
    else:
        exclude_ops = exclude_ops.split(",")
    if len(only_ops) > 0:
        virtual_ops = True
    data = []
    if int(sort) == -1:
        hist = account.history_reverse(
            batch_size=batch_size, only_ops=only_ops, exclude_ops=exclude_ops
        )
    else:
        hist = account.history(batch_size=batch_size, only_ops=only_ops, exclude_ops=exclude_ops)
    for h in hist:
        if h["virtual_op"] == 1 and not virtual_ops:
            continue

        cnt += 1
        if cnt > int(limit) and int(limit) > 0:
            break
        if json_file is not None:
            data.append(h)
        else:
            index = h.pop("index")
            op_type = h.pop("type")
            h.pop("trx_in_block")
            h.pop("op_in_trx")
            h.pop("virtual_op")
            h.pop("_id")
            if h["trx_id"] == "0000000000000000000000000000000000000000":
                h.pop("trx_id")
            for key in h:
                if isinstance(h[key], dict) and "nai" in h[key]:
                    h[key] = str(Amount(h[key], blockchain_instance=hv))
                if key == "json" or key == "json_metadata" and h[key] is not None and h[key] != "":
                    h[key] = json.loads(h[key])
            value = json.dumps(h, indent=4)
            t.add_row([str(index), op_type, value])

    if json_file is not None:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    else:
        print(t)


@cli.command()
@click.argument("follow", nargs=-1)
@click.option("--account", "-a", help="Follow from this account")
@click.option("--what", help='Follow these objects (defaults to ["blog"])', default=["blog"])
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def follow(follow, account, what, export):
    """Follow another account

    Can be blog ignore blacklist unblacklist follow_blacklist unfollow_blacklist follow_muted unfollow_muted on HIVE
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if isinstance(what, str):
        what = [what]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.follow(follow, what=what)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("mute", nargs=1)
@click.option("--account", "-a", help="Mute from this account")
@click.option("--what", help='Mute these objects (defaults to ["ignore"])', default=["ignore"])
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def mute(mute, account, what, export):
    """Mute another account"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if isinstance(what, str):
        what = [what]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.follow(mute, what=what)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("unfollow", nargs=1)
@click.option("--account", "-a", help="UnFollow/UnMute from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def unfollow(unfollow, account, export):
    """Unfollow/Unmute another account"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.unfollow(unfollow)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--signing-account", "-s", help="Signing account, when empty account is used.")
def userdata(account, signing_account):
    """Get the account's email address and phone number.

    The request has to be signed by the requested account or an admin account.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    print("'userdata' command is no longer available in the Hive-only build.")
    return


@cli.command()
@click.argument("account", nargs=1, required=False)
@click.option("--signing-account", "-s", help="Signing account, when empty account is used.")
def featureflags(account, signing_account):
    """Get the account's feature flags.

    The request has to be signed by the requested account or an admin account.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    print("'featureflags' command is no longer available in the Hive-only build.")
    return
