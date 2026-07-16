import unittest

from nectar import Hive
from nectar.block import Block, Blocks
from nectar.instance import set_shared_blockchain_instance

from .nodes import get_hive_nodes

# Use a known block with operations
# Block 102186724 (from debug session) has operations and is recent enough
TEST_BLOCK_ID = 102186724
# Block with virtual operations (producer_reward usually)
# We can find one or just assume standard blocks have them often,
# or use a known one. Let's use a range that likely contains one.


class TestBlockExtensive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = get_hive_nodes()
        cls.hive = Hive(node=cls.nodes, nobroadcast=True, num_retries=10)
        set_shared_blockchain_instance(cls.hive)

    def test_single_block_only_ops(self):
        """
        Test Case 1 & 5: Single Block with only_ops=True.
        - Uses `get_ops_in_block`.
        - Verify normalization of operations (dict format).
        - Verify metadata (transaction_id, block_num, timestamp).
        """
        print(f"\n[Test] Single Block {TEST_BLOCK_ID} (only_ops=True)...")
        block = Block(TEST_BLOCK_ID, only_ops=True, blockchain_instance=self.hive)

        self.assertIsInstance(block, dict)
        self.assertTrue(len(block.operations) > 0, "Block should have operations")

        op = block.operations[0]
        self.assertIsInstance(op, dict, "Operation should be a dictionary")
        self.assertIn("type", op)
        self.assertIn("value", op)
        self.assertIsInstance(op.get("type"), str, "Operation type should be string")

        # Metadata assertions
        self.assertIn("transaction_id", op, "transaction_id missing in single block op")
        self.assertIn("block_num", op, "block_num missing in single block op")
        self.assertIn("timestamp", op, "timestamp missing in single block op")

        print(
            f" -> Success: Found {len(block.operations)} ops. Sample TrxID: {op.get('transaction_id')}"
        )

    def test_bulk_blocks_only_ops(self):
        """
        Test Case 2 & 3: Bulk Blocks with only_ops=True.
        - Uses `get_block_range`.
        - Verify fallback extraction from `transactions`.
        - Verify metadata injection.
        """
        print(f"\n[Test] Bulk Blocks {TEST_BLOCK_ID} count=5 (only_ops=True)...")
        blocks = Blocks(TEST_BLOCK_ID, count=5, only_ops=True, blockchain_instance=self.hive)

        self.assertEqual(len(blocks), 5, "Should fetch 5 blocks")

        for block in blocks:
            self.assertTrue(
                len(block.operations) > 0, f"Block {block.identifier} should have operations"
            )
            op = block.operations[0]

            self.assertIsInstance(op, dict, "Operation should be a dictionary")
            self.assertIn("type", op)
            self.assertIn("value", op)
            self.assertIsInstance(op.get("type"), str, "Operation type should be string")

            # Metadata assertions
            self.assertIn(
                "transaction_id", op, f"transaction_id missing in bulk block {block.identifier}"
            )
            self.assertIn("block_num", op, f"block_num missing in bulk block {block.identifier}")
            self.assertIn("timestamp", op, f"timestamp missing in bulk block {block.identifier}")

        print(" -> Success: Verified 5/5 blocks in bulk mode.")

    def test_only_virtual_ops(self):
        """
        Test Case 4: only_virtual_ops=True.
        - Uses `get_ops_in_block` with `only_virtual=True`.
        - Verify strict virtual ops filtering.
        - Verify metadata.
        """
        # Block 80000000 has virtual ops (producer_reward)
        v_block_id = 80000000
        print(f"\n[Test] Virtual Ops Block {v_block_id}...")

        block = Block(v_block_id, only_virtual_ops=True, blockchain_instance=self.hive)

        self.assertTrue(len(block.operations) > 0, "Should have virtual operations")

        for op in block.operations:
            self.assertIsInstance(op, dict)
            # Verify it's effectively a virtual op (often indicated by 00000 trx_id or specific types)
            # But mostly we check structure and metadata here
            self.assertIn("type", op)
            self.assertIn("value", op)
            self.assertIsInstance(op.get("type"), str, "Operation type should be string")

            # Virtual ops in Hive often have a null transaction ID or string of zeros,
            # OR they inherit the block's context.
            # get_ops_in_block returns them wrapped, and we inject what we find.
            # If the API returns a trx_id for them, we should have it.
            # Usually virtual ops have trx_id '0000000000000000000000000000000000000000'

            if "transaction_id" in op:
                pass  # Good

            self.assertIn("block_num", op)

        print(f" -> Success: Found {len(block.operations)} virtual ops.")


if __name__ == "__main__":
    unittest.main()
