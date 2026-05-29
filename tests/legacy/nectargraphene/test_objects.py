import json
import unittest

from nectargraphenebase import objects, types


class Testcases(unittest.TestCase):
    def test_GrapheneObject(self):
        j = {"a": 2, "b": "abcde", "c": ["a", "b"]}
        j2 = objects.GrapheneObject(j)
        self.assertEqual(j, j2.data)
        self.assertEqual(json.loads(j2.__str__()), j2.json())

        a = types.Array(["1000", 3, "@@000000013"])
        j = {"a": a}
        j2 = objects.GrapheneObject(j)
        self.assertEqual(j, j2.data)
        self.assertEqual(json.loads(j2.__str__()), j2.json())

        a = types.Array(["1000", 3, "@@000000013"])
        j = {"a": a}
        j2 = objects.GrapheneObject(j)
        self.assertEqual(j, j2.data)
        self.assertEqual(json.loads(j2.__str__()), j2.json())
