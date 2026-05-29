import ast
import hashlib
import json
import logging
import os
import random
import re
from typing import Any

import click
from prettytable import PrettyTable

from nectar import exceptions
from nectar.block import Block
from nectar.blockchain import Blockchain
from nectar.cli import cli
from nectar.comment import Comment
from nectar.instance import shared_blockchain_instance
from nectar.nodelist import NodeList
from nectar.transactionbuilder import TransactionBuilder
from nectar.utils import import_custom_json
from nectar.version import version as __version__
from nectar.wallet import Wallet
from nectargraphenebase.base58 import Base58

log = logging.getLogger(__name__)

availableConfigurationKeys = [
    "default_account",
    "default_vote_weight",
    "nodes",
    "password_storage",
    "client_id",
    "default_canonical_url",
    "default_path",
    "use_tor",
]


def prompt_callback(ctx: Any, param: Any, value: str) -> bool:
    if value in ["yes", "y", "ye"]:
        return True
    else:
        print("Please write yes, ye or y to confirm!")
        ctx.abort()
        # This line is unreachable but needed for type checker
        return False


def asset_callback(ctx: Any, param: Any, value: str) -> str:
    if value not in ["HIVE", "HBD", "TBD", "TESTS"]:
        print("Please choose HIVE/HBD (or TESTS/TBD for test assets) as asset!")
        ctx.abort()
        # This line is unreachable but needed for type checker
        return value
    else:
        return value


def prompt_flag_callback(ctx: Any, param: Any, value: bool) -> bool:
    if not value:
        ctx.abort()
        # This line is unreachable but needed for type checker
        return False
    return True


def is_keyring_available() -> bool:
    KEYRING_AVAILABLE = False
    try:
        import keyring  # type: ignore

        if not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring):  # type: ignore
            KEYRING_AVAILABLE = True
        else:
            KEYRING_AVAILABLE = False
    except ImportError:
        KEYRING_AVAILABLE = False
    return KEYRING_AVAILABLE


def unlock_wallet(hv, password=None, allow_wif=True):
    if hv.unsigned and hv.nobroadcast:
        return True
    if hv.use_ledger:
        return True
    if not hv.wallet.locked():
        return True
    if not hv.wallet.store.is_encrypted():
        return True
    password_storage = hv.config["password_storage"]
    if not password and password_storage == "keyring" and is_keyring_available():
        import keyring  # type: ignore

        password = keyring.get_password("nectar", "wallet")
    if not password and password_storage == "environment" and "UNLOCK" in os.environ:
        password = os.environ.get("UNLOCK")
    if bool(password):
        hv.wallet.unlock(password)
    else:
        if allow_wif:
            password = click.prompt(
                "Password to unlock wallet or posting/active wif",
                confirmation_prompt=False,
                hide_input=True,
            )
        else:
            password = click.prompt(
                "Password to unlock wallet", confirmation_prompt=False, hide_input=True
            )
        if hv.wallet.is_encrypted():
            try:
                hv.wallet.unlock(password)
            except Exception:
                try:
                    from nectarstorage import InRamPlainKeyStore

                    hv.wallet.store = InRamPlainKeyStore()
                    hv.wallet.setKeys([password])
                    print("Wif accepted!")
                    return True
                except Exception:
                    if allow_wif:
                        raise exceptions.WrongMasterPasswordException(
                            "entered password is not a valid password/wif"
                        )
                    else:
                        raise exceptions.WrongMasterPasswordException(
                            "entered password is not a valid password"
                        )
        else:
            try:
                hv.wallet.setKeys([password])
                print("Wif accepted!")
                return True
            except Exception:
                try:
                    from nectarstorage import SqliteEncryptedKeyStore

                    hv.wallet.store = SqliteEncryptedKeyStore(config=hv.config)
                    hv.wallet.unlock(password)
                except Exception:
                    if allow_wif:
                        raise exceptions.WrongMasterPasswordException(
                            "entered password is not a valid password/wif"
                        )
                    else:
                        raise exceptions.WrongMasterPasswordException(
                            "entered password is not a valid password"
                        )

    if hv.wallet.locked():
        if password_storage == "keyring" or password_storage == "environment":
            print("Wallet could not be unlocked with %s!" % password_storage)
            password = click.prompt(
                "Password to unlock wallet", confirmation_prompt=False, hide_input=True
            )
            if bool(password):
                unlock_wallet(hv, password=password)
                if not hv.wallet.locked():
                    return True
        else:
            print("Wallet could not be unlocked!")
        return False
    else:
        print("Wallet Unlocked!")
        return True


def export_trx(tx, export):
    if export is not None:
        with open(export, "w", encoding="utf-8") as f:
            json.dump(tx, f)


@cli.command()
@click.argument("key")
@click.argument("value")
def set(key, value):
    """Set default_account, default_vote_weight or nodes

    set [key] [value]

    Examples:

    Set the default vote weight to 50 %:
    set default_vote_weight 50
    """
    hv = shared_blockchain_instance()
    if key == "default_account":
        if hv.rpc is not None:
            hv.rpc.rpcconnect()
        hv.set_default_account(value)
    elif key == "default_vote_weight":
        hv.set_default_vote_weight(value)
    elif key == "nodes" or key == "node":
        if bool(value) or value != "default":
            hv.set_default_nodes(value)
        else:
            hv.set_default_nodes("")
    elif key == "default_chain":
        hv.config["default_chain"] = value
    elif key == "password_storage":
        hv.config["password_storage"] = value
        if is_keyring_available() and value == "keyring":
            import keyring  # type: ignore

            password = click.prompt(
                "Password to unlock wallet (Will be stored in keyring)",
                confirmation_prompt=False,
                hide_input=True,
            )
            password = keyring.set_password("nectar", "wallet", password)
        elif is_keyring_available() and value != "keyring":
            import keyring  # type: ignore

            try:
                keyring.delete_password("nectar", "wallet")
            except keyring.errors.PasswordDeleteError:
                print("")
        if value == "environment":
            print(
                "The wallet password can be stored in the UNLOCK environment variable to skip password prompt!"
            )
    elif key == "client_id":
        hv.config["client_id"] = value
    elif key == "default_path":
        hv.config["default_path"] = value
    elif key == "default_canonical_url":
        hv.config["default_canonical_url"] = value
    elif key == "use_tor":
        hv.config["use_tor"] = value in ["true", "True"]
    else:
        print("wrong key")


@cli.command()
@click.option("--results", is_flag=True, default=False, help="Shows result of changing the node.")
def nextnode(results):
    """Uses the next node in list"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    hv.move_current_node_to_front()
    node = hv.get_default_nodes()
    offline = hv.offline
    if len(node) < 2 or isinstance(node, str):
        print("At least two nodes are needed!")
        return
    node = node[1:] + [node[0]]
    if not offline:
        hv.rpc.next()
        hv.get_blockchain_version()
    while not offline and node[0] != hv.rpc.url and len(node) > 1:
        node = node[1:] + [node[0]]
    hv.set_default_nodes(node)
    if not results:
        return

    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    if not offline:
        t.add_row(["Node-Url", hv.rpc.url])
    else:
        t.add_row(["Node-Url", node[0]])
    if not offline:
        t.add_row(["Version", hv.get_blockchain_version()])
        t.add_row(["HIVE", hv.is_hive])
    else:
        t.add_row(["Version", "hive-nectar is in offline mode..."])
    print(t)


@cli.command()
@click.option("--sort", "-s", is_flag=True, default=False, help="Sort all nodes by ping value")
@click.option(
    "--remove", "-r", is_flag=True, default=False, help="Remove node with errors from list"
)
def pingnode(sort, remove):
    """Returns the answer time in milliseconds"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    nodes = hv.get_default_nodes()

    t = PrettyTable(["Node", "Answer time [ms]"])
    t.align = "l"
    if sort:
        sorted_node_list = []
        nodelist = NodeList()
        sorted_nodes = nodelist.get_node_answer_time(nodes)
        for node in sorted_nodes:
            t.add_row([node["url"], "%.2f" % (node["delay_ms"])])
            sorted_node_list.append(node["url"])
        print(t)
        hv.set_default_nodes(sorted_node_list)
    else:
        node = hv.rpc.url
        nodelist = NodeList()
        node_times = nodelist.get_node_answer_time([node], verbose=False)
        rpc_answer_time = node_times[0]["delay_ms"] / 1000 if node_times else 0
        rpc_time_str = "%.2f" % (rpc_answer_time * 1000)
        t.add_row([node, rpc_time_str])
        print(t)


@cli.command()
def about():
    """About hive-nectar"""
    print("")
    print("hive-nectar version: %s" % __version__)
    print("")
    print("By @thecrazygm")
    print("")


@cli.command()
@click.option("--version", is_flag=True, default=False, help="Returns only the raw version value")
@click.option("--url", is_flag=True, default=False, help="Returns only the raw url value")
def currentnode(version, url):
    """Sets the currently working node at the first place in the list"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    offline = hv.offline
    hv.move_current_node_to_front()
    node = hv.get_default_nodes()
    if version and not offline:
        print(hv.get_blockchain_version())
        return
    elif version and offline:
        print("Node is offline")
        return
    if url and not offline:
        print(hv.rpc.url)
        return
    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    if not offline:
        t.add_row(["Node-Url", hv.rpc.url])
    else:
        t.add_row(["Node-Url", node[0]])
    if not offline:
        t.add_row(["Version", hv.get_blockchain_version()])
        t.add_row(["Chain", hv.get_blockchain_name()])
    else:
        t.add_row(["Version", "hive-nectar is in offline mode..."])
    print(t)


@cli.command()
@click.option("--show", "-s", is_flag=True, default=False, help="Prints the updated nodes")
@click.option(
    "--test",
    "-t",
    is_flag=True,
    default=False,
    help="Do change the node list, only print the newest nodes setup.",
)
@click.option("--only-https", is_flag=True, default=False, help="Use only https nodes.")
@click.option("--only-wss", is_flag=True, default=False, help="Use only websocket nodes.")
def updatenodes(show, test, only_https, only_wss):
    """Update the nodelist from @fullnodeupdate"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    t = PrettyTable(["node", "Version", "score"])
    t.align = "l"
    nodelist = NodeList()
    try:
        nodelist.update_nodes(blockchain_instance=hv)
        # Flags are mutually exclusive; at least one transport must be enabled
        if only_https and only_wss:
            raise click.UsageError("Use at most one of --only-https or --only-wss.")
        nodes = nodelist.get_hive_nodes(wss=not only_https, https=not only_wss)
        if not nodes:
            raise RuntimeError("No nodes matched the selected filters.")
        if hv.config["default_chain"] != "hive":
            hv.config["default_chain"] = "hive"
        if show or test:
            sorted_nodes = sorted(nodelist, key=lambda node: node["score"], reverse=True)
            for node in sorted_nodes:
                if node["url"] in nodes:
                    score = float("{:.1f}".format(node["score"]))
                    t.add_row([node["url"], node["version"], score])
            print(t)
        if not test:
            hv.set_default_nodes(nodes)
            hv.rpc.nodes.set_node_urls(nodes)
            hv.rpc.rpcconnect()
    except Exception:
        log.exception("Failed to update nodes")
        raise


@cli.command()
def config():
    """Shows local configuration"""
    hv = shared_blockchain_instance()
    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    for key in hv.config:
        # hide internal config data
        if (
            key in availableConfigurationKeys
            and key != "nodes"
            and key != "node"
            and key != "use_tor"
        ):
            t.add_row([key, hv.config[key]])
    node = hv.get_default_nodes()
    blockchain = hv.config["default_chain"]
    nodes = json.dumps(node, indent=4)
    t.add_row(["default_chain", blockchain])
    t.add_row(["nodes", nodes])
    if "password_storage" not in availableConfigurationKeys:
        t.add_row(["password_storage", hv.config["password_storage"]])
    t.add_row(["data_dir", hv.config.data_dir])
    t.add_row(["use_tor", bool(hv.config["use_tor"])])
    print(t)


@cli.command()
@click.option(
    "--file", "-i", help='Load transaction from file. If "-", read from stdin (defaults to "-")'
)
@click.option(
    "--outfile", "-o", help='Load transaction from file. If "-", read from stdin (defaults to "-")'
)
def sign(file, outfile):
    """Sign a provided transaction with available and required keys"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv):
        return
    if file and file != "-":
        if not os.path.isfile(file):
            raise Exception("File %s does not exist!" % file)
        with open(file) as fp:
            tx = fp.read()
        if tx.find("\0") > 0:
            with open(file, encoding="utf-16") as fp:
                tx = fp.read()
    else:
        tx = click.get_text_stream("stdin")
    tx = ast.literal_eval(tx)
    tx = hv.sign(tx, reconstruct_tx=False)
    tx = json.dumps(tx, indent=4)
    if outfile and outfile != "-":
        with open(outfile, "w") as fp:
            fp.write(tx)
    else:
        print(tx)


@cli.command()
@click.option(
    "--file", "-f", help='Load transaction from file. If "-", read from stdin (defaults to "-")'
)
def broadcast(file):
    """broadcast a signed transaction"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if file and file != "-":
        if not os.path.isfile(file):
            raise Exception("File %s does not exist!" % file)
        with open(file) as fp:
            tx = fp.read()
        if tx.find("\0") > 0:
            with open(file, encoding="utf-16") as fp:
                tx = fp.read()
    else:
        tx = click.get_text_stream("stdin")
    tx = ast.literal_eval(tx)
    tx = hv.broadcast(tx)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.option("--lines", "-n", help="Defines how many ops should be shown", default=10)
@click.option(
    "--head",
    "-h",
    help="Stream mode: When set, it is set to head (default is irreversible)",
    is_flag=True,
    default=False,
)
@click.option("--table", "-t", help="Output as table", is_flag=True, default=False)
@click.option("--follow", "-f", help="Constantly stream output", is_flag=True, default=False)
def stream(lines, head, table, follow):
    """Stream operations"""
    from nectar.amount import Amount
    from nectar.utils import formatTimeString

    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    mode = "irreversible"
    if head:
        mode = "head"
    b = Blockchain(mode=mode, blockchain_instance=hv)
    op_count = 0
    if table:
        t = PrettyTable(["blocknum", "trx_num", "type", "content"])
        t.align = "l"
        t._max_width = {"content": 80}
        last_block_num = 0
        for ops in b.stream(raw_ops=False):
            op_count += 1
            ops.pop("_id")
            block_num = ops.pop("block_num")
            ops_type = ops.pop("type")
            if last_block_num == 0:
                last_block_num = block_num
            trx_num = ops.pop("trx_num")
            for key in ops:
                if isinstance(ops[key], dict) and "nai" in ops[key]:
                    ops[key] = str(Amount(ops[key], blockchain_instance=hv))
                elif key == "timestamp":
                    ops[key] = formatTimeString(ops[key])
            if last_block_num < block_num:
                print(t)
                t = PrettyTable(["blocknum", "trx_num", "type", "content"])
                t.align = "l"
                t._max_width = {"content": 80}
                last_block_num = block_num
            content = ops
            if ops_type == "custom_json":
                content = ops["id"]
            elif ops_type == "vote":
                content = "{:.2f}% @{}/{} - {}".format(
                    ops["weight"] / 100,
                    ops["author"],
                    ops["permlink"][:30],
                    ops["voter"],
                )
            elif ops_type == "transfer":
                content = "{}: @{} -> @{}".format(str(ops["amount"]), ops["from"], ops["to"])
            elif ops_type == "transfer_to_vesting":
                content = "{}: @{} -> @{}".format(str(ops["amount"]), ops["from"], ops["to"])
            t.add_row([str(block_num), str(trx_num), ops_type, content])
            if op_count >= lines and not follow:
                print(t)
                return
    else:
        import pprint

        for ops in b.stream(raw_ops=True):
            op_count += 1
            ops["timestamp"] = formatTimeString(ops["timestamp"])
            pprint.pprint(ops)
            if op_count >= lines and not follow:
                return


@cli.command()
@click.argument("blocknumber", nargs=1, required=False)
@click.option("--trx", "-t", help="Show only one transaction number", default=None)
@click.option(
    "--use-api",
    "-u",
    help="Uses the get_potential_signatures api call",
    is_flag=True,
    default=False,
)
def verify(blocknumber, trx, use_api):
    """Returns the public signing keys for a block"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    b = Blockchain(blockchain_instance=hv)
    i = 0
    if not blocknumber:
        blocknumber = b.get_current_block_num()
    try:
        int(blocknumber)
        block = Block(blocknumber, blockchain_instance=hv)
        if trx is not None:
            i = int(trx)
            trxs = [block.json_transactions[int(trx)]]
        else:
            trxs = block.json_transactions
    except Exception:
        trxs = [b.get_transaction(blocknumber)]
        blocknumber = trxs[0]["block_num"]
    wallet = Wallet(blockchain_instance=hv)
    t = PrettyTable(["trx", "Signer key", "Account"])
    t.align = "l"
    if not use_api:
        from nectarbase.signedtransactions import Signed_Transaction
    for trx in trxs:
        if not use_api:
            signed_tx = Signed_Transaction(trx.copy())
            public_keys = []
            for key in signed_tx.verify(chain=hv.chain_params, recover_parameter=True):
                public_keys.append(format(Base58(key, prefix=hv.prefix), hv.prefix))
        else:
            tx = TransactionBuilder(tx=trx, blockchain_instance=hv)
            public_keys = tx.get_potential_signatures()
        accounts = []
        empty_public_keys = []
        for key in public_keys:
            account = wallet.getAccountFromPublicKey(key)
            if account is None:
                empty_public_keys.append(key)
            else:
                accounts.append(account)
        new_public_keys = []
        for key in public_keys:
            if key not in empty_public_keys or use_api:
                new_public_keys.append(key)
        if len(new_public_keys) == 0:
            for key in public_keys:
                new_public_keys.append(key)
        if isinstance(new_public_keys, list) and len(new_public_keys) == 1:
            new_public_keys = new_public_keys[0]
        else:
            new_public_keys = json.dumps(new_public_keys, indent=4)
        if isinstance(accounts, list) and len(accounts) == 1:
            accounts = accounts[0]
        else:
            accounts = json.dumps(accounts, indent=4)
        t.add_row(["%d" % i, new_public_keys, accounts])
        i += 1
    print(t)


@cli.command()
def chainconfig():
    """Prints chain config in a table"""
    from nectar.amount import Amount

    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    chain_config = hv.get_config()
    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    for key in chain_config:
        if isinstance(chain_config[key], dict) and "amount" in chain_config[key]:
            t.add_row([key, str(Amount(chain_config[key], blockchain_instance=hv))])
        else:
            t.add_row([key, chain_config[key]])
    print(t)


@cli.command()
@click.argument("objects", nargs=-1)
def info(objects):
    """Show basic blockchain info

    General information about the blockchain, a block, an account,
    a post/comment and a public key
    """
    from nectar.account import Account
    from nectar.amount import Amount
    from nectar.witness import Witness

    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not objects:
        t = PrettyTable(["Key", "Value"])
        t.align = "l"
        info = hv.get_dynamic_global_properties()
        median_price = hv.get_current_median_history()
        token_per_mvest = hv.get_token_per_mvest()
        chain_props = hv.get_chain_properties()
        try:
            price = (
                Amount(median_price["base"], blockchain_instance=hv).amount
                / Amount(median_price["quote"], blockchain_instance=hv).amount
            )
        except Exception:
            price = None
        for key in info:
            if isinstance(info[key], dict) and "amount" in info[key]:
                t.add_row([key, str(Amount(info[key], blockchain_instance=hv))])
            else:
                t.add_row([key, info[key]])
        t.add_row(["%s per mvest" % hv.token_symbol, token_per_mvest])
        if price is not None:
            t.add_row(["internal price", price])
        t.add_row(
            [
                "account_creation_fee",
                str(Amount(chain_props["account_creation_fee"], blockchain_instance=hv)),
            ]
        )
        print(t.get_string(sortby="Key"))
    for obj in objects:
        if (
            re.match(r"^[0-9-]*$", obj)
            or re.match(r"^-[0-9]*$", obj)
            or re.match(r"^[0-9-]*:[0-9]", obj)
            or re.match(r"^[0-9-]*:-[0-9]", obj)
        ):
            tran_nr = ""
            if re.match(r"^[0-9-]*:[0-9-]", obj):
                obj, tran_nr = obj.split(":")
            if int(obj) < 1:
                b = Blockchain(blockchain_instance=hv)
                block_number = b.get_current_block_num() + int(obj) - 1
            else:
                block_number = obj
            block = Block(block_number, blockchain_instance=hv)
            if block:
                t = PrettyTable(["Key", "Value"])
                t.align = "l"
                block_json = block.json()
                for key in sorted(block_json):
                    value = block_json[key]
                    if key == "transactions" and not bool(tran_nr):
                        t.add_row(["Nr. of transactions", len(value)])
                    elif key == "transactions" and bool(tran_nr):
                        if int(tran_nr) < 0:
                            tran_nr = len(value) + int(tran_nr)
                        else:
                            tran_nr = int(tran_nr)
                        if len(value) > tran_nr - 1 and tran_nr > -1:
                            t_value = json.dumps(value[tran_nr], indent=4)
                            t.add_row(["transaction %d/%d" % (tran_nr, len(value)), t_value])
                    elif key == "transaction_ids" and not bool(tran_nr):
                        t.add_row(["Nr. of transaction_ids", len(value)])
                    elif key == "transaction_ids" and bool(tran_nr):
                        if int(tran_nr) < 0:
                            tran_nr = len(value) + int(tran_nr)
                        else:
                            tran_nr = int(tran_nr)
                        if len(value) > tran_nr - 1 and tran_nr > -1:
                            t.add_row(
                                [
                                    "transaction_id %d/%d" % (int(tran_nr), len(value)),
                                    value[tran_nr],
                                ]
                            )
                    else:
                        t.add_row([key, value])
                print(t)
            else:
                print("Block number %s unknown" % obj)
        elif re.match(r"^[a-zA-Z0-9\-\._]{2,16}$", obj):
            account = Account(obj, blockchain_instance=hv)
            t = PrettyTable(["Key", "Value"])
            t.align = "l"
            t._max_width = {"Value": 80}
            account_json = account.json()
            for key in sorted(account_json):
                value = account_json[key]
                if key == "json_metadata":
                    value = json.dumps(json.loads(value or "{}"), indent=4)
                elif key in ["posting", "witness_votes", "active", "owner"]:
                    value = json.dumps(value, indent=4)
                elif key == "reputation" and int(value) > 0:
                    value = int(value)
                    rep = account.rep
                    value = "{:.2f} ({:d})".format(rep, value)
                elif isinstance(value, dict) and "asset" in value:
                    value = str(account[key])
                t.add_row([key, value])
            print(t)

            try:
                witness = Witness(obj, blockchain_instance=hv)
                witness_json = witness.json()
                t = PrettyTable(["Key", "Value"])
                t.align = "l"
                for key in sorted(witness_json):
                    value = witness_json[key]
                    if key in ["props", "hbd_exchange_rate"]:
                        value = json.dumps(value, indent=4)
                    t.add_row([key, value])
                print(t)
            except exceptions.WitnessDoesNotExistsException as e:
                print(str(e))
        elif re.match(r"^" + hv.prefix + ".{48,55}$", obj):
            account = hv.wallet.getAccountFromPublicKey(obj)
            if account:
                account = Account(account, blockchain_instance=hv)
                key_type = hv.wallet.getKeyType(account, obj)
                t = PrettyTable(["Account", "Key_type"])
                t.align = "l"
                t._max_width = {"Value": 80}
                t.add_row([account["name"], key_type])
                print(t)
            else:
                print("Public Key %s not known" % obj)
        elif re.match(r".*@.{3,16}/.*$", obj):
            post = Comment(obj, blockchain_instance=hv)
            post_json = post.json()
            if post_json:
                t = PrettyTable(["Key", "Value"])
                t.align = "l"
                t._max_width = {"Value": 80}
                for key in sorted(post_json):
                    if key in ["body", "active_votes"]:
                        value = "not shown"
                    else:
                        value = post_json[key]
                    if key in ["json_metadata"]:
                        value = json.loads(value)
                        value = json.dumps(value, indent=4)
                    elif key in ["tags", "active_votes"]:
                        value = json.dumps(value, indent=4)
                    t.add_row([key, value])
                print(t)
            else:
                print("Post %s not known" % obj)
        elif re.match(r"^[a-zA-Z0-9\_]{40}$", obj):
            b = Blockchain(blockchain_instance=hv)
            from nectarapi.exceptions import UnknownTransaction

            try:
                trx = b.get_transaction(obj)
            except UnknownTransaction:
                print("%s is unknown!" % obj)
                return
            t = PrettyTable(["Key", "Value"])
            t.align = "l"
            t._max_width = {"Value": 80}
            for key in trx:
                value = trx[key]
                if key in ["operations", "signatures"]:
                    value = json.dumps(value, indent=4)
                t.add_row([key, value])
            print(t)
        else:
            print("Couldn't identify object to read")


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


@cli.command()
@click.option(
    "--block",
    "-b",
    help="Select a block number, when skipped the latest block is used.",
    default=None,
)
@click.option(
    "--trx-id", "-t", help="Select a trx-id, When skipped, the latest one is used.", default=None
)
@click.option("--draws", "-d", help="Number of draws (default = 1)", default=1)
@click.option(
    "--participants",
    "-p",
    help="Number of participants or file name including participants (one participant per line), (default = 100)",
    default="100",
)
@click.option(
    "--hashtype", "-h", help="Can be md5, sha256, sha512 (default = sha256)", default="sha256"
)
@click.option(
    "--separator",
    "-s",
    help="Is used for sha256 and sha512 to seperate the draw number from the seed (default = ,)",
    default=",",
)
@click.option("--account", "-a", help="The account which broadcasts the reply")
@click.option(
    "--reply",
    "-r",
    help="Parent post/comment authorperm. When set, the results will be broadcasted as reply to this authorperm.",
    default=None,
)
@click.option(
    "--without-replacement",
    "-w",
    help="When set, numbers are drawed without replacement.",
    is_flag=True,
    default=False,
)
@click.option(
    "--markdown",
    "-m",
    help="When set, results are returned in markdown format",
    is_flag=True,
    default=False,
)
def draw(
    block,
    trx_id,
    draws,
    participants,
    hashtype,
    separator,
    account,
    reply,
    without_replacement,
    markdown,
):
    """Generate pseudo-random numbers based on trx id, block id and previous block id.

    When using --reply, the result is directly broadcasted as comment
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if reply is not None:
        if not unlock_wallet(hv):
            return
        reply_comment = Comment(reply, blockchain_instance=hv)
    if block is not None and block != "":
        block = Block(int(block), blockchain_instance=hv)
    else:
        blockchain = Blockchain(blockchain_instance=hv)
        block = blockchain.get_current_block()
    data = None

    for trx in block.transactions:
        if trx["transaction_id"] == trx_id:
            data = trx
        elif trx_id is None:
            trx_id = trx["transaction_id"]
            data = trx
    if trx_id is None:
        trx_id = "0"

    if os.path.exists(participants):
        with open(participants) as f:
            content = f.read()
        if content.find(",") > 0:
            participants_list = content.split(",")
        else:
            participants_list = content.split("\n")
        if participants_list[-1] == "":
            participants_list = participants_list[:-1]
        participants = len(participants_list)
    else:
        participants = int(participants)
        participants_list = []

    if without_replacement:
        assert draws <= participants
    trx = data["operations"][0]["value"]
    if hashtype == "md5":
        seed = hashlib.md5((trx_id + block["block_id"] + block["previous"]).encode()).hexdigest()
    elif hashtype == "sha256":
        seed = hashlib.sha256((trx_id + block["block_id"] + block["previous"]).encode()).hexdigest()
    elif hashtype == "sha512":
        seed = hashlib.sha512((trx_id + block["block_id"] + block["previous"]).encode()).hexdigest()
    random.seed(a=seed, version=2)
    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    t.add_row(["block number", block["id"]])
    t.add_row(["trx id", trx_id])
    t.add_row(["block id", block["block_id"]])
    t.add_row(["previous", block["previous"]])
    t.add_row(["hash type", hashtype])
    t.add_row(["draws", draws])
    t.add_row(["participants", participants])
    draw_list = [x + 1 for x in range(participants)]
    results = []
    for i in range(int(draws)):
        if hashtype == "md5":
            number = int(random.random() * len(draw_list))
        elif hashtype == "sha256":
            seed = hashlib.sha256(
                (trx_id + block["block_id"] + block["previous"] + separator + str(i + 1)).encode()
            ).digest()
            bigRand = int.from_bytes(seed, "big")
            number = bigRand % (len(draw_list))
        elif hashtype == "sha512":
            seed = hashlib.sha512(
                (trx_id + block["block_id"] + block["previous"] + separator + str(i + 1)).encode()
            ).digest()
            bigRand = int.from_bytes(seed, "big")
            number = bigRand % (len(draw_list))
        results.append(draw_list[number])
        if len(participants_list) > 0:
            t.add_row(
                [
                    "%d. draw" % (i + 1),
                    "%d - %s" % (draw_list[number], participants_list[draw_list[number] - 1]),
                ]
            )
        else:
            t.add_row(["%d. draw" % (i + 1), draw_list[number]])
        if without_replacement:
            draw_list.pop(number)

    body = "The following results can be checked with:\n"
    body += "```\n"
    if without_replacement:
        body += "hive-nectar draw -d %d -p %d -b %d -t %s -h %s -s '%s' -w\n" % (
            draws,
            participants,
            block["id"],
            trx_id,
            hashtype,
            separator,
        )
    else:
        body += "hive-nectar draw -d %d -p %d -b %d -t %s -h %s -s '%s'\n" % (
            draws,
            participants,
            block["id"],
            trx_id,
            hashtype,
            separator,
        )
    body += "```\n\n"
    body += "| key | value |\n"
    body += "| --- | --- |\n"
    body += "| block number | [%d](https://hiveblocks.com/b/%d#%s) |\n" % (
        block["id"],
        block["id"],
        trx_id,
    )
    body += "| trx id | [{}](https://hiveblocks.com/tx/{}) |\n".format(trx_id, trx_id)
    body += "| block id | %s |\n" % block["block_id"]
    body += "| previous id | %s |\n" % block["previous"]
    body += "| hash type | %s |\n" % hashtype
    body += "| draws | %d |\n" % draws
    body += "| participants | %d |\n" % participants
    i = 0
    for result in results:
        i += 1
        if len(participants_list) > 0:
            body += "| %d. draw | %d - %s |\n" % (i, result, participants_list[result - 1])
        else:
            body += "| %d. draw | %d |\n" % (i, result)
    if markdown:
        print(body)
    else:
        print(t)
    if reply:
        reply_comment.reply(body, author=account)


@cli.command()
@click.argument("jsonid", nargs=1)
@click.argument("json_data", nargs=-1)
@click.option("--account", "-a", help="The account which broadcasts the custom_json")
@click.option(
    "--active",
    "-t",
    help="When set, the active key is used for broadcasting",
    is_flag=True,
    default=False,
)
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def customjson(jsonid, json_data, account, active, export):
    """Broadcasts a custom json

    First parameter is the cusom json id, the second field is a json file or a json key value combination
    e.g. hive-nectar customjson -a thecrazygm dw-heist username thecrazygm amount 100
    """
    from nectar.account import Account

    if jsonid is None:
        print("First argument must be the custom_json id")
    if json_data is None:
        print("Second argument must be the json_data, can be a string or a file name.")
    data = import_custom_json(jsonid, json_data)
    if data is None:
        return
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    _acc = Account(account, blockchain_instance=hv)
    if active:
        tx = hv.custom_json(jsonid, data, required_auths=[account])
    else:
        tx = hv.custom_json(jsonid, data, required_posting_auths=[account])
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)
