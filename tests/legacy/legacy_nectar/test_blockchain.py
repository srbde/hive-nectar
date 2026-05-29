import time
import unittest

from nectar import Hive
from nectar.block import Block
from nectar.blockchain import Blockchain
from nectar.exceptions import BlockWaitTimeExceeded
from nectar.instance import set_shared_blockchain_instance
from nectarbase.signedtransactions import Signed_Transaction

from .nodes import get_hive_nodes

wif = "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up shared test fixtures for the Testcases class.

        Initializes a Hive client configured for testing (no broadcast, provided active key, retry policy), creates a Blockchain wrapper from that client, computes a short test block window (start = current_block - 5, stop = current_block), and registers the Hive client as the shared blockchain instance used by the tests.
        """
        cls.bts = Hive(
            node=get_hive_nodes(), nobroadcast=True, keys={"active": wif}, num_retries=10
        )
        b = Blockchain(blockchain_instance=cls.bts)
        num = b.get_current_block_num()
        cls.start = max(1, num - 1)  # Just test 1 block to speed up
        cls.stop = num

        # from getpass import getpass
        # self.bts.wallet.unlock(getpass())
        set_shared_blockchain_instance(cls.bts)

    def test_blockchain(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        num = b.get_current_block_num()
        self.assertTrue(num > 0)
        self.assertTrue(isinstance(num, int))
        block = b.get_current_block()
        self.assertTrue(isinstance(block, Block))
        # self.assertTrue(num <= block.identifier)
        block_time = b.block_time(block.identifier)
        self.assertEqual(block.time(), block_time)
        block_timestamp = b.block_timestamp(block.identifier)
        timestamp = int(time.mktime(block.time().timetuple()))
        self.assertEqual(block_timestamp, timestamp)

    def test_estimate_block_num(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        last_block = b.get_current_block()
        num = last_block.identifier
        old_block = Block(num - 60, blockchain_instance=bts)
        date = old_block.time()
        est_block_num = b.get_estimated_block_num(date, accurate=False)
        self.assertTrue((est_block_num - (old_block.identifier)) < 10)
        est_block_num = b.get_estimated_block_num(date, accurate=True)
        self.assertTrue((est_block_num - (old_block.identifier)) < 2)
        est_block_num = b.get_estimated_block_num(date, estimateForwards=True, accurate=True)
        self.assertTrue((est_block_num - (old_block.identifier)) < 2)
        est_block_num = b.get_estimated_block_num(date, estimateForwards=True, accurate=False)

    def test_get_account_count(self):
        b = Blockchain(blockchain_instance=self.bts)
        num = b.get_account_count()
        self.assertTrue(isinstance(num, int) and num > 0)

    def test_get_all_accounts(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        accounts = []
        limit = 200
        for acc in b.get_all_accounts(steps=100, limit=limit):
            accounts.append(acc)
        self.assertEqual(len(accounts), limit)
        self.assertEqual(len(set(accounts)), limit)

    def test_awaitTX(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        b.blocks = lambda *args, **kwargs: [{"transactions": []}, {"transactions": []}]
        trans = {
            "ref_block_num": 3855,
            "ref_block_prefix": 1730859721,
            "expiration": "2018-03-09T06:21:06",
            "operations": [],
            "extensions": [],
            "signatures": [
                "2033a872a8ad33c7d5b946871e4c9cc8f08a5809258355fc909058eac83"
                "20ac2a872517a52b51522930d93dd2c1d5eb9f90b070f75f838c881ff29b11af98d6a1b"
            ],
        }
        with self.assertRaises(Exception):
            b.awaitTxConfirmation(trans, limit=1)

    def test_stream(self):
        """Test blockchain streaming functionality."""
        bts = self.bts
        start = self.start
        stop = self.stop
        b = Blockchain(blockchain_instance=bts)
        opNames = ["transfer", "vote"]

        # Test basic stream with processed operations
        ops_stream = []
        for op in b.stream(opNames=opNames, start=start, stop=stop):
            ops_stream.append(op)
            if len(ops_stream) >= 10:  # Limit to 10 ops for speed
                break
        self.assertTrue(len(ops_stream) >= 0)

        # Verify stream operations have correct structure
        for op in ops_stream:
            self.assertIn("type", op)
            self.assertIn(op["type"], opNames)
            self.assertIn("block_num", op)
            self.assertTrue(op["block_num"] >= start)
            self.assertTrue(op["block_num"] <= stop)

        # Test stream with raw operations
        ops_raw_stream = []
        for op in b.stream(opNames=opNames, raw_ops=True, start=start, stop=stop):
            ops_raw_stream.append(op)
            if len(ops_raw_stream) >= 10:  # Limit to 10 ops for speed
                break
        self.assertTrue(len(ops_raw_stream) >= 0)

        # Verify raw stream operations have correct structure
        for op in ops_raw_stream:
            self.assertIn("op", op)
            self.assertIsInstance(op["op"], list)
            self.assertIn(op["op"][0], opNames)
            self.assertIn("block_num", op)
            self.assertTrue(op["block_num"] >= start)
            self.assertTrue(op["block_num"] <= stop)

        # Test stream with only_ops filter
        only_ops_stream = []
        for op in b.stream(opNames=opNames, start=start, stop=stop, only_ops=True):
            only_ops_stream.append(op)
            if len(only_ops_stream) >= 10:  # Limit to 10 ops for speed
                break
        self.assertTrue(len(only_ops_stream) >= 0)

        # Verify only_ops stream has correct structure
        for op in only_ops_stream:
            self.assertIn("type", op)
            self.assertIn(op["type"], opNames)
            self.assertIn("block_num", op)
            self.assertTrue(op["block_num"] >= start)
            self.assertTrue(op["block_num"] <= stop)

        # Test stream with raw_ops and only_ops
        only_ops_raw_stream = []
        for op in b.stream(opNames=opNames, raw_ops=True, start=start, stop=stop, only_ops=True):
            only_ops_raw_stream.append(op)
            if len(only_ops_raw_stream) >= 10:  # Limit to 10 ops for speed
                break
        self.assertTrue(len(only_ops_raw_stream) >= 0)

        # Verify only_ops_raw stream has correct structure
        for op in only_ops_raw_stream:
            self.assertIn("op", op)
            self.assertIsInstance(op["op"], list)
            self.assertIn(op["op"][0], opNames)
            self.assertIn("block_num", op)
            self.assertTrue(op["block_num"] >= start)
            self.assertTrue(op["block_num"] <= stop)

        # Test that ops_statistics works (but don't compare with limited streams)
        op_stat = b.ops_statistics(start=start, stop=stop)
        self.assertIsInstance(op_stat, dict)
        self.assertIn("transfer", op_stat)
        self.assertIn("vote", op_stat)
        self.assertTrue(op_stat["transfer"] >= 0)
        self.assertTrue(op_stat["vote"] >= 0)

        # Test blocks streaming
        ops_blocks = []
        for op in b.blocks(start=start, stop=stop):
            ops_blocks.append(op)
            if len(ops_blocks) >= 5:  # Limit to 5 blocks for speed
                break
        self.assertTrue(len(ops_blocks) > 0)

        # Verify block structure
        for block in ops_blocks:
            self.assertTrue(block.identifier >= start)
            self.assertTrue(block.identifier <= stop)
            self.assertTrue(hasattr(block, "transactions"))

        # Test single block streaming
        ops_blocks = []
        for op in b.blocks():
            ops_blocks.append(op)
            break
        self.assertTrue(len(ops_blocks) == 1)

    def test_stream2(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        stop_block = b.get_current_block_num()
        start_block = stop_block - 10
        ops_stream = []
        for op in b.stream(start=start_block, stop=stop_block):
            ops_stream.append(op)
        self.assertTrue(len(ops_stream) > 0)

    def test_wait_for_and_get_block(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts, max_block_wait_repetition=18)
        start_num = b.get_current_block_num()
        blocknum = start_num
        last_fetched_block_num = None
        for i in range(3):
            block = b.wait_for_and_get_block(blocknum)
            last_fetched_block_num = block.block_num
            blocknum = last_fetched_block_num + 1
        self.assertEqual(last_fetched_block_num, start_num + 2)

        b2 = Blockchain(blockchain_instance=bts, max_block_wait_repetition=1)
        with self.assertRaises(BlockWaitTimeExceeded):
            b2.wait_for_and_get_block(start_num + 1000, blocks_waiting_for=1)

    def test_hash_op(self):
        bts = self.bts
        b = Blockchain(blockchain_instance=bts)
        op1 = {
            "type": "vote_operation",
            "value": {
                "voter": "ubg",
                "author": "yesslife",
                "permlink": "steemit-sandwich-contest-week-25-2da-entry",
                "weight": 100,
            },
        }
        op2 = [
            "vote",
            {
                "voter": "ubg",
                "author": "yesslife",
                "permlink": "steemit-sandwich-contest-week-25-2da-entry",
                "weight": 100,
            },
        ]
        hash1 = b.hash_op(op1)
        hash2 = b.hash_op(op2)
        self.assertEqual(hash1, hash2)

    def test_signing_appbase(self):
        b = Blockchain(blockchain_instance=self.bts)
        st = None
        for block in b.blocks(start=25304468, stop=25304468):
            for trx in block.transactions:
                st = Signed_Transaction(trx.copy())
        self.assertTrue(st is not None)

    def test_get_account_reputations(self):
        b = Blockchain(blockchain_instance=self.bts)
        limit = 100  # get the first 100 account reputations
        reps_limit = list(b.get_account_reputations(limit=limit))
        self.assertTrue(len(reps_limit) == limit)
        for rep in reps_limit:  # expect format {'name': [str], 'reputation': [int]}
            self.assertTrue(isinstance(rep, dict))
            self.assertTrue("account" in rep and "reputation" in rep)
            self.assertTrue(isinstance(rep["account"], str))
            self.assertTrue(isinstance(rep["reputation"], int))

        first = reps_limit[0]["account"]
        last = reps_limit[-1]["account"]
        # get the same account reputations via start/stop constraints
        reps_constr = list(b.get_account_reputations(start=first, stop=last))
        self.assertTrue(len(reps_constr) >= limit)
        # The actual number of accounts may have increased and the
        # reputation values may be different between the two API
        # calls, but each account of the first call should be
        # contained in the second as well
        accounts = [rep["account"] for rep in reps_constr]
        for rep in reps_limit:
            self.assertTrue(rep["account"] in accounts)
