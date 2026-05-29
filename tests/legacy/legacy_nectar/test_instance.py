import unittest

from parameterized import parameterized

from nectar import Hive
from nectar.account import Account
from nectar.amount import Amount
from nectar.block import Block
from nectar.blockchain import Blockchain
from nectar.comment import Comment
from nectar.instance import (
    set_shared_blockchain_instance,
    set_shared_config,
    shared_blockchain_instance,
)
from nectar.market import Market
from nectar.price import Price
from nectar.transactionbuilder import TransactionBuilder
from nectar.vote import Vote
from nectar.wallet import Wallet
from nectar.witness import Witness
from nectarapi.exceptions import RPCConnection

from .nodes import get_hive_nodes

# Py3 compatibility

core_unit = "STM"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Prepare class-wide test fixtures for the test suite.

        Initializes a temporary Hive to refresh backup data and default nodes, collects available node URLs, creates a persistent Hive instance used as the shared blockchain instance for tests, and builds lightweight objects to extract test values. Sets the following class attributes for use by tests:
        - urls: list of Hive node URLs retrieved from get_hive_nodes()
        - bts: Hive instance used as the shared blockchain instance (nobroadcast, num_retries=10)
        - authorperm: authorperm string from a sample Comment
        - authorpermvoter: combination of authorperm and the last vote's voter in the form "authorperm|voter"

        Side effects:
        - Registers bts as the shared blockchain instance via set_shared_blockchain_instance.
        - Mutates class state (adds urls, bts, authorperm, authorpermvoter).
        """
        hv = Hive(node=get_hive_nodes())
        hv.config.refreshBackup()
        hv.set_default_nodes(get_hive_nodes())
        del hv

        cls.urls = get_hive_nodes()
        cls.bts = Hive(node=cls.urls, nobroadcast=True, num_retries=10)
        set_shared_blockchain_instance(cls.bts)
        ranked = cls.bts.rpc.get_ranked_posts({"sort": "trending", "limit": 1}, api="bridge")
        if not ranked:
            raise RuntimeError("Unable to fetch a trending post for tests")
        comment = Comment(ranked[0], api="bridge", blockchain_instance=cls.bts)
        cls.authorperm = comment.authorperm
        votes = comment.get_votes(raw_data=True)
        last_vote = votes[-1] if votes else {"voter": "test"}
        cls.authorpermvoter = comment["authorperm"] + "|" + last_vote.get("voter", "test")

    @classmethod
    def tearDownClass(cls):
        """
        Tear down class-level test fixtures by restoring the shared Hive configuration from the latest backup.

        Creates a temporary Hive instance using the configured test nodes and calls its configuration recovery to restore the most recent backup, ensuring any global configuration changes made during tests are reverted.
        """
        hv = Hive(node=get_hive_nodes())
        hv.config.recover_with_latest_backup()

    @parameterized.expand([("instance"), ("hive")])
    def test_account(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            acc = Account("test")
            self.assertIn(acc.blockchain.rpc.url, self.urls)
            self.assertIn(acc["balance"].blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                acc = Account(
                    "test",
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
                # Force a network call to trigger RPCConnection on bad node
                acc.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            acc = Account("test", blockchain_instance=hv)
            self.assertIn(acc.blockchain.rpc.url, self.urls)
            self.assertIn(acc["balance"].blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                acc = Account("test")
                # Force a network call to trigger RPCConnection on bad shared instance
                acc.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_amount(self, node_param):
        if node_param == "instance":
            hv = Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            set_shared_blockchain_instance(self.bts)
            o = Amount("1 %s" % self.bts.backed_token_symbol)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Amount("1 %s" % self.bts.backed_token_symbol, blockchain_instance=hv)
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Amount("1 %s" % self.bts.backed_token_symbol, blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Amount("1 %s" % self.bts.backed_token_symbol)

    @parameterized.expand([("instance"), ("hive")])
    def test_block(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Block(1)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Block(
                    1,
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Block(1, blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Block(1)
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_blockchain(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Blockchain()
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Blockchain(
                    blockchain_instance=Hive(node="https://abc.d", autoconnect=False, num_retries=1)
                )
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Blockchain(blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Blockchain()

    @parameterized.expand([("instance"), ("hive")])
    def test_comment(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Comment(self.authorperm)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Comment(
                    self.authorperm,
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Comment(self.authorperm, blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Comment(self.authorperm)
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_market(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Market()
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Market(
                    blockchain_instance=Hive(node="https://abc.d", autoconnect=False, num_retries=1)
                )
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Market(blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Market()

    @parameterized.expand([("instance"), ("hive")])
    def test_price(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Price(10.0, "{}/{}".format(self.bts.token_symbol, self.bts.backed_token_symbol))
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Price(
                    10.0,
                    "{}/{}".format(self.bts.token_symbol, self.bts.backed_token_symbol),
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Price(
                10.0,
                "{}/{}".format(self.bts.token_symbol, self.bts.backed_token_symbol),
                blockchain_instance=hv,
            )
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                Price(10.0, "{}/{}".format(self.bts.token_symbol, self.bts.backed_token_symbol))

    @parameterized.expand([("instance"), ("hive")])
    def test_vote(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Vote(self.authorpermvoter)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Vote(
                    self.authorpermvoter,
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Vote(self.authorpermvoter, blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Vote(self.authorpermvoter)
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_wallet(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Wallet()
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Wallet(
                    blockchain_instance=Hive(node="https://abc.d", autoconnect=False, num_retries=1)
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Wallet(blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Wallet()
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_witness(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Witness("gtg")
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Witness(
                    "gtg",
                    blockchain_instance=Hive(
                        node="https://abc.d", autoconnect=False, num_retries=1
                    ),
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = Witness("gtg", blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = Witness("gtg")
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_transactionbuilder(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = TransactionBuilder()
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = TransactionBuilder(
                    blockchain_instance=Hive(node="https://abc.d", autoconnect=False, num_retries=1)
                )
                o.blockchain.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = TransactionBuilder(blockchain_instance=hv)
            self.assertIn(o.blockchain.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                o = TransactionBuilder()
                o.blockchain.get_config()

    @parameterized.expand([("instance"), ("hive")])
    def test_hive(self, node_param):
        if node_param == "instance":
            set_shared_blockchain_instance(self.bts)
            o = Hive(node=self.urls)
            o.get_config()
            self.assertIn(o.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                hv = Hive(node="https://abc.d", autoconnect=False, num_retries=1)
                hv.get_config()
        else:
            set_shared_blockchain_instance(
                Hive(node="https://abc.d", autoconnect=False, num_retries=1)
            )
            hv = self.bts
            o = hv
            o.get_config()
            self.assertIn(o.rpc.url, self.urls)
            with self.assertRaises(RPCConnection):
                hv = shared_blockchain_instance()
                hv.get_config()

    def test_config(self):
        set_shared_config({"node": self.urls})
        set_shared_blockchain_instance(None)
        o = shared_blockchain_instance()
        self.assertIn(o.rpc.url, self.urls)
