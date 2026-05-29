import ast
import logging
import os

import click

from nectar.hive import Hive
from nectar.instance import set_shared_blockchain_instance
from nectar.version import version as __version__

click.disable_unicode_literals_warning = True
log = logging.getLogger(__name__)


@click.group(chain=True)
@click.option(
    "--node", "-n", default="", help="URL for public Hive API (e.g. https://api.hive.blog)"
)
@click.option("--offline", "-o", is_flag=True, default=False, help="Prevent connecting to network")
@click.option("--no-broadcast", "-d", is_flag=True, default=False, help="Do not broadcast")
@click.option(
    "--testnet",
    "-t",
    is_flag=True,
    default=False,
    help="Legacy compatibility flag (no-op, Hive only).",
)
@click.option("--no-wallet", "-p", is_flag=True, default=False, help="Do not load the wallet")
@click.option(
    "--unsigned",
    "-x",
    is_flag=True,
    default=False,
    help="Nothing will be signed, changes the default value of expires to 3600",
)
@click.option(
    "--keys",
    "-k",
    help="JSON file that contains account keys, when set, the wallet cannot be used.",
)
@click.option(
    "--use-ledger",
    "-u",
    is_flag=True,
    default=False,
    help="Uses the ledger device Nano S for signing.",
)
@click.option(
    "--path", help="BIP32 path from which the keys are derived, when not set, default_path is used."
)
@click.option(
    "--expires",
    "-e",
    default=30,
    help="Delay in seconds until transactions are supposed to expire(defaults to 30)",
)
@click.option("--verbose", "-v", default=3, help="Verbosity")
@click.version_option(version=__version__)
def cli(
    node,
    offline,
    no_broadcast,
    testnet,  # noqa: ARG001
    no_wallet,
    unsigned,
    keys,
    use_ledger,
    path,
    expires,
    verbose,
):
    # Logging
    log = logging.getLogger(__name__)
    verbosity = ["critical", "error", "warn", "info", "debug"][int(min(verbose, 4))]
    log.setLevel(getattr(logging, verbosity.upper()))
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, verbosity.upper()))
    ch.setFormatter(formatter)
    log.addHandler(ch)

    if unsigned and expires == 30:
        # Change expires to max duration when setting unsigned
        expires = 3600

    keys_list = []
    autoconnect = False
    if keys and keys != "":
        if not os.path.isfile(keys):
            raise Exception("File %s does not exist!" % keys)
        with open(keys) as fp:
            keyfile = fp.read()
        if keyfile.find("\0") > 0:
            with open(keys, encoding="utf-16") as fp:
                keyfile = fp.read()
        keyfile = ast.literal_eval(keyfile)
        for account in keyfile:
            for role in ["owner", "active", "posting", "memo"]:
                if role in keyfile[account]:
                    keys_list.append(keyfile[account][role])
    if len(keys_list) > 0:
        autoconnect = True
    debug = verbose > 0
    # Hive-only instance
    hv = Hive(
        node=node,
        nobroadcast=no_broadcast,
        keys=keys_list,
        offline=offline,
        nowallet=no_wallet,
        unsigned=unsigned,
        expiration=expires,
        use_ledger=use_ledger,
        path=path,
        debug=debug,
        num_retries=10,
        num_retries_call=5,
        timeout=30,
        autoconnect=autoconnect,
    )

    set_shared_blockchain_instance(hv)

    pass


# Import other modules to register commands on the cli group
from nectar.cli import account, market, post, utils, wallet  # noqa: F401
