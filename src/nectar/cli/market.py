import json
import logging

import click
from prettytable import PrettyTable

from nectar.account import Account
from nectar.amount import Amount
from nectar.asset import Asset
from nectar.cli import cli
from nectar.cli.utils import (
    asset_callback,
    export_trx,
    unlock_wallet,
)
from nectar.instance import shared_blockchain_instance
from nectar.market import Market
from nectar.price import Price
from nectar.transactionbuilder import TransactionBuilder
from nectar.utils import formatTimeString
from nectarbase import operations
from nectargraphenebase.account import PrivateKey

log = logging.getLogger(__name__)


@cli.command()
@click.argument("to", nargs=1)
@click.argument("amount", nargs=1)
@click.argument("asset", nargs=1, callback=asset_callback)
@click.argument("memo", nargs=1, required=False)
@click.option("--account", "-a", help="Transfer from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def transfer(to, amount, asset, memo, account, export):
    """Transfer HBD or HIVE"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not bool(memo):
        memo = ""
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.transfer(to, amount, asset, memo)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.option("--account", "-a", help="Powerup from this account")
@click.option("--to", "-t", help="Powerup this account", default=None)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def powerup(amount, account, to, export):
    """Power up (vest HIVE into Hive Power)"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    try:
        amount = float(amount)
    except Exception:
        amount = str(amount)
    tx = acc.transfer_to_vesting(amount, to=to)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.option("--account", "-a", help="Powerup from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def powerdown(amount, account, export):
    """Power down (start withdrawing VESTS from Hive Power)

    amount is in VESTS
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    try:
        amount = float(amount)
    except Exception:
        amount = str(amount)
    tx = acc.withdraw_vesting(amount)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.argument("to_account", nargs=1)
@click.option("--account", "-a", help="Delegate from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def delegate(amount, to_account, account, export):
    """Delegate (start delegating VESTS to another account)

    amount is in VESTS / HIVE Power
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    if hv.token_symbol is not None:
        amount = Amount(amount, blockchain_instance=hv)
    else:
        amount = Amount(amount, blockchain_instance=hv)
    if isinstance(amount, Amount):
        if amount.symbol == hv.token_symbol:
            amount = hv.hp_to_vests(float(amount))

    tx = acc.delegate_vesting_shares(to_account, amount)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.option("--account", "-a", help="List outgoing delegations from this account")
def listdelegations(account):
    """List all outgoing delegations from an account.

    The default account is used if no other account name is given as
        option to this command.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    acc = Account(account, blockchain_instance=hv)
    pt = PrettyTable(["Delegatee", hv.vests_symbol, "%s Power" % (hv.token_symbol)])
    pt.align = "r"
    start_account = ""
    limit = 100
    stop = False
    while stop is False:
        delegations = acc.get_vesting_delegations(start_account=start_account, limit=limit)
        if len(delegations) < limit:
            stop = True
        if start_account != "" and len(delegations) > 0:
            # skip first entry if it was already part of the previous call
            delegations = delegations[1:]
        for deleg in delegations:
            vests = Amount(deleg["vesting_shares"], blockchain_instance=hv)
            token_power = "%.3f" % (hv.vests_to_token_power(vests))
            pt.add_row([deleg["delegatee"], str(vests), token_power])
            start_account = deleg["delegatee"]
    print(pt)


@cli.command()
@click.argument("to", nargs=1)
@click.option(
    "--percentage", default=100, help='The percent of the withdraw to go to the "to" account'
)
@click.option("--account", "-a", help="Powerup from this account")
@click.option(
    "--auto_vest",
    help="Set to true if the from account should receive the VESTS as"
    "VESTS, or false if it should receive them as HIVE.",
    is_flag=True,
)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def powerdownroute(to, percentage, account, auto_vest, export):
    """Setup a powerdown route"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = acc.set_withdraw_vesting_route(to, percentage, auto_vest=auto_vest)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("new_recovery_account", nargs=1)
@click.option("--account", "-a", help="Change the recovery account from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def changerecovery(new_recovery_account, account, export):
    """Changes the recovery account with the owner key (needs 30 days to be active)"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    new_recovery_account = Account(new_recovery_account, blockchain_instance=hv)
    account = Account(account, blockchain_instance=hv)
    op = operations.Change_recovery_account(
        **{
            "account_to_recover": account["name"],
            "new_recovery_account": new_recovery_account["name"],
            "extensions": [],
        }
    )

    tb = TransactionBuilder(blockchain_instance=hv)
    tb.appendOps([op])
    if hv.unsigned:
        tb.addSigningInformation(account["name"], "owner")
        tx = tb
    else:
        key = click.prompt(
            "Owner key for %s" % account["name"], confirmation_prompt=False, hide_input=True
        )
        owner_key = PrivateKey(wif=key)
        tb.appendWif(str(owner_key))
        tb.sign()
        tx = tb.broadcast()
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.option("--account", "-a", help="Powerup from this account")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def convert(amount, account, export):
    """Convert HBD to HIVE (takes ~1 week to settle)"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    try:
        amount = float(amount)
    except Exception:
        amount = str(amount)
    tx = acc.convert(amount)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.argument("asset", nargs=1)
@click.argument("price", nargs=1, required=False)
@click.option("--account", "-a", help='Buy with this account (defaults to "default_account")')
@click.option("--orderid", help="Set an orderid")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def buy(amount, asset, price, account, orderid, export):
    """Buy HIVE or HBD from the internal market

    Limit buy price denoted in (HBD per HIVE)
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if account is None:
        account = hv.config["default_account"]
    if asset == hv.backed_token_symbol:
        market = Market(
            base=Asset(hv.token_symbol),
            quote=Asset(hv.backed_token_symbol),
            blockchain_instance=hv,
        )
    else:
        market = Market(
            base=Asset(hv.backed_token_symbol),
            quote=Asset(hv.token_symbol),
            blockchain_instance=hv,
        )
    if price is None:
        orderbook = market.orderbook(limit=1, raw_data=False)
        if asset == hv.token_symbol and len(orderbook["bids"]) > 0:
            p = Price(
                orderbook["bids"][0]["base"], orderbook["bids"][0]["quote"], blockchain_instance=hv
            ).invert()
            p_show = p
        elif len(orderbook["asks"]) > 0:
            p = Price(
                orderbook["asks"][0]["base"], orderbook["asks"][0]["quote"], blockchain_instance=hv
            ).invert()
            p_show = p
        price_ok = click.prompt("Is the following Price ok: %s [y/n]" % (str(p_show)))
        if price_ok not in ["y", "ye", "yes"]:
            return
    else:
        p = Price(
            float(price),
            "{}:{}".format(hv.backed_token_symbol, hv.token_symbol),
            blockchain_instance=hv,
        )
    if not unlock_wallet(hv):
        return

    a = Amount(float(amount), asset, blockchain_instance=hv)
    acc = Account(account, blockchain_instance=hv)
    tx = market.buy(p, a, account=acc, orderid=orderid)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("amount", nargs=1)
@click.argument("asset", nargs=1)
@click.argument("price", nargs=1, required=False)
@click.option("--account", "-a", help='Sell with this account (defaults to "default_account")')
@click.option("--orderid", help="Set an orderid")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def sell(amount, asset, price, account, orderid, export):
    """Sell HIVE or HBD from the internal market

    Limit sell price denoted in (HBD per HIVE)
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if asset == hv.backed_token_symbol:
        market = Market(
            base=Asset(hv.token_symbol),
            quote=Asset(hv.backed_token_symbol),
            blockchain_instance=hv,
        )
    else:
        market = Market(
            base=Asset(hv.backed_token_symbol),
            quote=Asset(hv.token_symbol),
            blockchain_instance=hv,
        )
    if not account:
        account = hv.config["default_account"]
    if not price:
        orderbook = market.orderbook(limit=1, raw_data=False)
        if asset == hv.backed_token_symbol and len(orderbook["bids"]) > 0:
            p = Price(
                orderbook["bids"][0]["base"], orderbook["bids"][0]["quote"], blockchain_instance=hv
            ).invert()
            p_show = p
        else:
            p = Price(
                orderbook["asks"][0]["base"], orderbook["asks"][0]["quote"], blockchain_instance=hv
            ).invert()
            p_show = p
        price_ok = click.prompt("Is the following Price ok: %s [y/n]" % (str(p_show)))
        if price_ok not in ["y", "ye", "yes"]:
            return
    else:
        p = Price(
            float(price),
            "{}:{}".format(hv.backed_token_symbol, hv.token_symbol),
            blockchain_instance=hv,
        )
    if not unlock_wallet(hv):
        return
    a = Amount(float(amount), asset, blockchain_instance=hv)
    acc = Account(account, blockchain_instance=hv)
    tx = market.sell(p, a, account=acc, orderid=orderid)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("orderid", nargs=1)
@click.option("--account", "-a", help='Sell with this account (defaults to "default_account")')
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def cancel(orderid, account, export):
    """Cancel order in the internal market"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    market = Market(blockchain_instance=hv)
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    tx = market.cancel(orderid, account=acc)
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("account", nargs=1, required=False)
def openorders(account):
    """Show open orders"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    market = Market(blockchain_instance=hv)
    if not account:
        account = hv.config["default_account"]
    acc = Account(account, blockchain_instance=hv)
    openorders = market.accountopenorders(account=acc)
    t = PrettyTable(["Orderid", "Created", "Order", "Account"], hrules=0)
    t.align = "r"
    for order in openorders:
        t.add_row(
            [order["orderid"], formatTimeString(order["created"]), str(order["order"]), account]
        )
    print(t)
