import unittest

from nectar import Hive
from nectar.instance import set_shared_blockchain_instance, shared_blockchain_instance
from nectar.wallet import Wallet

from .nodes import get_hive_nodes

# Py3 compatibility
core_unit = "STM"
wif = "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hv = shared_blockchain_instance()
        hv.config.refreshBackup()

        cls.hv = Hive(
            node=get_hive_nodes(),
            nobroadcast=True,
            # We want to bundle many operations into a single transaction
            bundle=True,
            num_retries=10,
            # Overwrite wallet to use this list of wifs only
        )

        cls.hv.set_default_account("test")
        set_shared_blockchain_instance(cls.hv)
        # self.hv.newWallet("TestingOneTwoThree")

        cls.wallet = Wallet(blockchain_instance=cls.hv)
        cls.wallet.wipe(True)
        cls.wallet.newWallet("TestingOneTwoThree")
        cls.wallet.unlock(pwd="TestingOneTwoThree")
        cls.wallet.addPrivateKey(wif)

    @classmethod
    def tearDownClass(cls):
        hv = shared_blockchain_instance()
        hv.config.recover_with_latest_backup()

    def test_set_default_account(self):
        hv = self.hv
        hv.set_default_account("thecrazygm")

        self.assertEqual(hv.config["default_account"], "thecrazygm")
