import unittest

from nectar import Hive, exceptions
from nectar.account import Account
from nectar.instance import set_shared_blockchain_instance, shared_blockchain_instance
from nectar.wallet import Wallet

from .nodes import get_hive_nodes

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
        cls.wallet.newWallet(pwd="TestingOneTwoThree")
        cls.wallet.unlock(pwd="TestingOneTwoThree")
        cls.wallet.addPrivateKey(wif)

    @classmethod
    def tearDownClass(cls):
        hv = shared_blockchain_instance()
        hv.config.recover_with_latest_backup()

    def test_wallet_lock(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        self.assertTrue(self.wallet.unlocked())
        self.assertFalse(self.wallet.locked())
        self.wallet.lock()
        self.assertTrue(self.wallet.locked())

    def test_change_masterpassword(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        self.assertTrue(self.wallet.unlocked())
        self.wallet.changePassphrase("newPass")
        self.wallet.lock()
        self.assertTrue(self.wallet.locked())
        self.wallet.unlock(pwd="newPass")
        self.assertTrue(self.wallet.unlocked())
        self.wallet.changePassphrase("TestingOneTwoThree")
        self.wallet.lock()

    def test_Keys(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        keys = self.wallet.getPublicKeys()
        self.assertTrue(len(keys) > 0)
        pub = self.wallet.getPublicKeys()[0]
        private = self.wallet.getPrivateKeyForPublicKey(pub)
        self.assertEqual(private, wif)

    def test_account_by_pub(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        acc = Account("gtg")
        pub = acc["owner"]["key_auths"][0][0]
        acc_by_pub = self.wallet.getAccount(pub)
        self.assertEqual("gtg", acc_by_pub["name"])
        gen = self.wallet.getAccountsFromPublicKey(pub)
        acc_by_pub_list = []
        for a in gen:
            acc_by_pub_list.append(a)
        self.assertEqual("gtg", acc_by_pub_list[0])
        gen = self.wallet.getAllAccounts(pub)
        acc_by_pub_list = []
        for a in gen:
            acc_by_pub_list.append(a)
        self.assertEqual("gtg", acc_by_pub_list[0]["name"])
        self.assertEqual(pub, acc_by_pub_list[0]["pubkey"])

    def test_pub_lookup(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getOwnerKeyForAccount("test")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getMemoKeyForAccount("test")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getActiveKeyForAccount("test")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getPostingKeyForAccount("test")

    def test_pub_lookup_keys(self):
        hv = self.hv
        self.wallet.hive = hv
        self.wallet.unlock(pwd="TestingOneTwoThree")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getOwnerKeysForAccount("test")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getActiveKeysForAccount("test")
        with self.assertRaises(exceptions.MissingKeyError):
            self.wallet.getPostingKeysForAccount("test")
