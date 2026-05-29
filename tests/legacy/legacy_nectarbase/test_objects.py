import json
import unittest

from nectarbase.objects import Amount, Operation


class Testcases(unittest.TestCase):
    def test_Amount(self):
        a = "1.000 HIVE"
        t = Amount(a)
        self.assertEqual(a, t.__str__())
        self.assertEqual(a, str(t))

        t = Amount(a, json_str=True, prefix="STM")
        self.assertEqual(
            {"amount": "1000", "precision": 3, "nai": "@@000000021"}, json.loads(str(t))
        )

        a = {"amount": "3000", "precision": 3, "nai": "@@000000037"}
        t = Amount(a, prefix="STM")
        # self.assertEqual(str(a), t.__str__())
        self.assertEqual(a, json.loads(str(t)))

    def test_Amount_overflow(self):
        a = "0.9999 HIVE"
        t = Amount(a)
        self.assertEqual("0.999 HIVE", t.__str__())
        self.assertEqual("0.999 HIVE", str(t))
        a = "0.9991 HIVE"
        t = Amount(a)
        self.assertEqual("0.999 HIVE", t.__str__())
        self.assertEqual("0.999 HIVE", str(t))

        a = "8.9999 HIVE"
        t = Amount(a)
        self.assertEqual("8.999 HIVE", t.__str__())
        self.assertEqual("8.999 HIVE", str(t))
        a = "8.9991 HIVE"
        t = Amount(a)
        self.assertEqual("8.999 HIVE", t.__str__())
        self.assertEqual("8.999 HIVE", str(t))

        a = "8.19 HIVE"
        t = Amount(a)
        self.assertEqual("8.190 HIVE", t.__str__())
        self.assertEqual("8.190 HIVE", str(t))

        a = "0.0009 HIVE"
        t = Amount(a)
        self.assertEqual("0.000 HIVE", t.__str__())
        self.assertEqual("0.000 HIVE", str(t))

        a = "100.0009 HIVE"
        t = Amount(a)
        self.assertEqual("100.000 HIVE", t.__str__())
        self.assertEqual("100.000 HIVE", str(t))

    def test_Operation(self):
        a = {"amount": "1000", "precision": 3, "nai": "@@000000013"}
        j = ["transfer", {"from": "a", "to": "b", "amount": a, "memo": "c"}]
        o = Operation(j)
        self.assertEqual(o.json()[1], j[1])
