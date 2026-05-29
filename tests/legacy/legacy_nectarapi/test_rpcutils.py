import unittest

from nectarapi.rpcutils import get_query


class Testcases(unittest.TestCase):
    def test_get_query(self):
        query = get_query(1, "test_api", "test", "")
        self.assertEqual(query["method"], "test_api.test")
        self.assertEqual(query["jsonrpc"], "2.0")
        self.assertEqual(query["id"], 1)
        self.assertTrue(isinstance(query["params"], dict))

        args = ({"a": "b"},)
        query = get_query(1, "test_api", "test", args)
        self.assertEqual(query["method"], "test_api.test")
        self.assertEqual(query["jsonrpc"], "2.0")
        self.assertEqual(query["id"], 1)
        self.assertTrue(isinstance(query["params"], dict))
        self.assertEqual(query["params"], args[0])

        args = ([{"a": "b"}, {"a": "c"}],)
        query_list = get_query(1, "test_api", "test", args)
        query = query_list[0]
        self.assertEqual(query["method"], "test_api.test")
        self.assertEqual(query["jsonrpc"], "2.0")
        self.assertEqual(query["id"], 1)
        self.assertTrue(isinstance(query["params"], dict))
        self.assertEqual(query["params"], args[0][0])
        query = query_list[1]
        self.assertEqual(query["method"], "test_api.test")
        self.assertEqual(query["jsonrpc"], "2.0")
        self.assertEqual(query["id"], 2)
        self.assertTrue(isinstance(query["params"], dict))
        self.assertEqual(query["params"], args[0][1])

        args = ("b",)
        query = get_query(1, "test_api", "test", args)
        self.assertEqual(query["method"], "test_api.test")
        self.assertEqual(query["jsonrpc"], "2.0")
        self.assertEqual(query["id"], 1)
        self.assertTrue(isinstance(query["params"], list))
        self.assertEqual(query["params"], ["b"])
