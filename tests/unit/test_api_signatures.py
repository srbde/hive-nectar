import inspect

from nectar import Hive
from nectar.account import Account
from nectar.amount import Amount
from nectar.asset import Asset
from nectar.block import Block
from nectar.blockchain import Blockchain


def check_params_exist(func, expected_params):
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    for param in expected_params:
        assert param in params, (
            f"Expected parameter '{param}' not found in {func.__name__} signature: {params}"
        )


def test_hive_signatures():
    check_params_exist(Hive.__init__, ["self", "node", "rpcuser", "rpcpassword"])


def test_account_signatures():
    check_params_exist(Account.__init__, ["self", "account", "blockchain_instance"])

    # Check history signature parameters
    check_params_exist(
        Account.history,
        ["self", "start", "stop", "only_ops", "exclude_ops", "batch_size", "raw_output"],
    )


def test_amount_signatures():
    check_params_exist(Amount.__init__, ["self", "amount", "asset", "blockchain_instance"])


def test_asset_signatures():
    check_params_exist(Asset.__init__, ["self", "asset", "lazy", "blockchain_instance"])


def test_block_signatures():
    check_params_exist(Block.__init__, ["self", "block", "lazy", "blockchain_instance"])


def test_blockchain_signatures():
    check_params_exist(Blockchain.__init__, ["self", "blockchain_instance", "mode"])
    check_params_exist(Blockchain.stream, ["self", "opNames"])
