import json
import unittest

from nectar import Hive
from nectar.instance import set_shared_blockchain_instance
from nectar.nodelist import (
    CACHE_FILE,
    NodeList,
    clear_beacon_cache,
    extract_nodes_from_raw,
    fetch_beacon_nodes,
)


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nodelist = NodeList()
        cls.bts = Hive(node=nodelist.get_hive_nodes(), nobroadcast=True, num_retries=10)
        set_shared_blockchain_instance(cls.bts)

    def test_get_nodes(self):
        nodelist = NodeList()
        all_nodes = nodelist.get_nodes()
        self.assertEqual(len(nodelist), len(all_nodes))
        https_nodes = nodelist.get_nodes(wss=False)
        self.assertEqual(https_nodes[0][:5], "https")

    def test_hive_nodes(self):
        nodelist = NodeList()
        nodelist.update_nodes()
        hive_nodes = nodelist.get_nodes()
        for node in hive_nodes:
            blockchainobject = Hive(node=node)
            assert blockchainobject.is_hive

    def test_nodes_update(self):
        nodelist = NodeList()
        all_nodes = nodelist.get_nodes()
        nodelist.update_nodes(blockchain_instance=self.bts)
        nodes = nodelist.get_nodes()
        self.assertIn(nodes[0], all_nodes)

    def test_extract_nodes_from_raw(self):
        """Test the extract_nodes_from_raw function with valid and invalid data."""
        # Valid data
        valid_data = [{"endpoint": "https://api.example.com", "score": 90}]
        result = extract_nodes_from_raw(valid_data, "test")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["endpoint"], "https://api.example.com")

        # Invalid data type
        invalid_data = "not a list"
        result = extract_nodes_from_raw(invalid_data, "test")
        self.assertIsNone(result)

        # Mixed valid/invalid items
        mixed_data = [
            {"endpoint": "https://api.example.com"},
            "invalid",
            {"endpoint": "https://api2.example.com"},
        ]
        result = extract_nodes_from_raw(mixed_data, "test")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["endpoint"], "https://api.example.com")
        self.assertEqual(result[1]["endpoint"], "https://api2.example.com")

    def test_clear_beacon_cache(self):
        """Test that clear_beacon_cache clears both memory and disk cache."""
        # First fetch some data to populate cache
        nodes = fetch_beacon_nodes()
        self.assertIsNotNone(nodes)

        # Clear cache
        clear_beacon_cache()

        # Check that cache file is removed
        self.assertFalse(CACHE_FILE.exists())

    def test_disk_cache_persistence(self):
        """Test that fetched nodes are written to disk cache."""
        # Clear any existing cache
        clear_beacon_cache()

        # Fetch fresh nodes
        nodes = fetch_beacon_nodes()
        self.assertIsNotNone(nodes)
        self.assertGreater(len(nodes), 0)

        # Check that cache file exists
        self.assertTrue(CACHE_FILE.exists())

        # Verify cache file contains valid JSON data
        with CACHE_FILE.open("r") as f:
            cached_data = json.load(f)
        self.assertIsInstance(cached_data, list)
        self.assertEqual(len(cached_data), len(nodes))

    def test_cache_reuse(self):
        """Test that subsequent calls use cached data."""
        # Clear cache first
        clear_beacon_cache()

        # First call should fetch from API
        nodes1 = fetch_beacon_nodes()
        self.assertIsNotNone(nodes1)

        # Second call should use cache (memory or disk)
        nodes2 = fetch_beacon_nodes()
        self.assertIsNotNone(nodes2)
        self.assertEqual(nodes1, nodes2)
