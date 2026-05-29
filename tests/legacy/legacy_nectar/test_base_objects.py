import unittest

from nectar import Hive
from nectar.account import Account
from nectar.instance import set_shared_blockchain_instance
from nectar.witness import Witness

from .nodes import get_hive_nodes


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up a shared Hive blockchain instance for the test class.

        Creates a Hive client configured with the test node(s), nobroadcast=True, and num_retries=10,
        assigns it to the class attribute `bts`, and registers it as the global shared blockchain instance
        used by tests.
        """
        cls.bts = Hive(node=get_hive_nodes(), nobroadcast=True, num_retries=10)
        set_shared_blockchain_instance(cls.bts)

    def test_Account(self):
        # with self.assertRaises(exceptions.AccountDoesNotExistsException):
        #     Account("gtg")

        c = Account("gtg")
        self.assertEqual(c["name"], "gtg")
        self.assertIsInstance(c, Account)

    def test_Witness(self):
        # with self.assertRaises(exceptions.WitnessDoesNotExistsException):
        #     Witness("gtg")

        c = Witness("gtg")
        self.assertEqual(c["owner"], "gtg")
        self.assertIsInstance(c.account, Account)
