import unittest
from datetime import datetime

from nectar import Hive, exceptions
from nectar.block import Block, BlockHeader
from nectar.instance import set_shared_blockchain_instance

from .nodes import get_hive_nodes

wif = "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up class-level Hive blockchain test fixture.

        Creates a Hive instance (nobroadcast=True, provided active key, retries=10), stores it on the class as `bts`, sets `test_block_id` to 19273700, registers the instance as the shared blockchain instance, and sets the default account to "test".
        """
        cls.bts = Hive(
            node=get_hive_nodes(),
            nobroadcast=True,
            keys={"active": wif},
            num_retries=10,
        )
        cls.test_block_id = 19273700
        # from getpass import getpass
        # self.bts.wallet.unlock(getpass())
        set_shared_blockchain_instance(cls.bts)
        cls.bts.set_default_account("test")

    def test_block(self):
        bts = self.bts
        test_block_id = self.test_block_id
        block = Block(test_block_id, blockchain_instance=bts)
        self.assertEqual(block.identifier, test_block_id)
        self.assertTrue(isinstance(block.time(), datetime))
        self.assertTrue(isinstance(block, dict))

        self.assertTrue(len(block.operations))
        self.assertTrue(isinstance(block.ops_statistics(), dict))

        block2 = Block(test_block_id + 1, blockchain_instance=bts)
        self.assertTrue(block2.time() > block.time())
        with self.assertRaises(exceptions.BlockDoesNotExistsException):
            Block(0, blockchain_instance=bts)

    def test_block_only_ops(self):
        bts = self.bts
        test_block_id = self.test_block_id
        block = Block(test_block_id, only_ops=True, blockchain_instance=bts)
        self.assertEqual(block.identifier, test_block_id)
        self.assertTrue(isinstance(block.time(), datetime))
        self.assertTrue(isinstance(block, dict))

        self.assertTrue(len(block.operations))
        self.assertTrue(isinstance(block.ops_statistics(), dict))

        block2 = Block(test_block_id + 1, blockchain_instance=bts)
        self.assertTrue(block2.time() > block.time())
        with self.assertRaises(exceptions.BlockDoesNotExistsException):
            Block(0, blockchain_instance=bts)

    def test_block_header(self):
        bts = self.bts
        test_block_id = self.test_block_id
        block = BlockHeader(test_block_id, blockchain_instance=bts)
        self.assertEqual(block.identifier, test_block_id)
        self.assertTrue(isinstance(block.time(), datetime))
        self.assertTrue(isinstance(block, dict))

        block2 = BlockHeader(test_block_id + 1, blockchain_instance=bts)
        self.assertTrue(block2.time() > block.time())
        with self.assertRaises(exceptions.BlockDoesNotExistsException):
            BlockHeader(0, blockchain_instance=bts)

    def test_export(self):
        bts = self.bts
        block_num = 2000000

        block = bts.rpc.get_block({"block_num": block_num}, api="block_api")
        if block and "block" in block:
            block = block["block"]

        b = Block(block_num, blockchain_instance=bts)
        keys = list(block.keys())
        json_content = b.json()

        for k in keys:
            if k not in "json_metadata":
                if isinstance(block[k], dict) and isinstance(json_content[k], list):
                    self.assertEqual(list(block[k].values()), json_content[k])
                else:
                    self.assertEqual(block[k], json_content[k])

        block = bts.rpc.get_block_header({"block_num": block_num}, api="block_api")
        if "header" in block:
            block = block["header"]

        b = BlockHeader(block_num, blockchain_instance=bts)
        keys = list(block.keys())
        json_content = b.json()

        for k in keys:
            if k not in "json_metadata":
                if isinstance(block[k], dict) and isinstance(json_content[k], list):
                    self.assertEqual(list(block[k].values()), json_content[k])
                else:
                    self.assertEqual(block[k], json_content[k])

    def test_block_only_ops_dict_normalization(self):
        """Verify that only_ops=True returns operations as dicts, not lists."""
        bts = self.bts
        test_block_id = self.test_block_id
        # Initialize block with only_ops=True
        block = Block(test_block_id, only_ops=True, blockchain_instance=bts)

        self.assertTrue(len(block.operations) > 0, "Should have operations")

        # Check the first operation
        op = block.operations[0]
        self.assertTrue(isinstance(op, dict), f"Operation should be dict, got {type(op)}")
        self.assertIn("type", op)
        self.assertIn("value", op)

        # We expect transaction keys to be injected now
        self.assertIn("transaction_id", op, "transaction_id missing in normalized op")
        self.assertIn("block_num", op, "block_num missing in normalized op")
        self.assertTrue(
            isinstance(op.get("type"), str),
            f"Operation type should be string, got {type(op.get('type'))}",
        )
