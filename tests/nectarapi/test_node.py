import unittest

from nectarapi.exceptions import (
    NumRetriesReached,
)
from nectarapi.node import Nodes


class Testcases(unittest.TestCase):
    def test_sleep_and_check_retries(self):
        nodes = Nodes("test", -1, 5)
        nodes.sleep_and_check_retries("error")
        nodes = Nodes("test", 1, 5)
        nodes.increase_error_cnt()
        nodes.increase_error_cnt()
        with self.assertRaises(NumRetriesReached):
            nodes.sleep_and_check_retries()

    def test_next(self):
        nodes = Nodes(["a", "b", "c"], -1, -1)
        self.assertEqual(nodes.working_nodes_count, len(nodes))
        self.assertEqual(nodes.url, nodes[0].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[0].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[1].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[2].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[0].url)

        nodes = Nodes("a,b,c", 5, 5)
        self.assertEqual(nodes.working_nodes_count, len(nodes))
        self.assertEqual(nodes.url, nodes[0].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[0].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[1].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[2].url)
        next(nodes)
        self.assertEqual(nodes.url, nodes[0].url)

        # Test node failure / fallback behavior
        # Mark node 'b' (index 1) as failed (error_cnt > num_retries)
        nodes[1].error_cnt = 6
        self.assertEqual(nodes.working_nodes_count, 2)

        # Advance: currently we are at 'a' (index 0). Next should skip 'b' (index 1) and go to 'c' (index 2)
        next(nodes)
        self.assertEqual(nodes.url, "c")

        # Next should wrap around, skipping 'b', and go to 'a'
        next(nodes)
        self.assertEqual(nodes.url, "a")

        # Mark all nodes as failed
        nodes[0].error_cnt = 6
        nodes[2].error_cnt = 6
        self.assertEqual(nodes.working_nodes_count, 0)
        with self.assertRaises(StopIteration):
            next(nodes)

    def test_init(self):
        nodes = Nodes(["a", "b", "c"], 5, 5)
        nodes2 = Nodes(nodes, 5, 5)
        self.assertEqual(nodes.url, nodes2.url)
        nodes2 = Nodes(["a", "b", "c"], 5, 5)
        nodes2.set_node_urls(["a", "c"])
        self.assertEqual(nodes.url, nodes2.url)
        next(nodes)
        next(nodes)
        next(nodes)
        next(nodes2)
        next(nodes2)
        self.assertEqual(nodes.url, nodes2.url)
