import unittest

from parameterized import parameterized

from nectar import Hive
from nectar.instance import set_shared_blockchain_instance
from nectar.witness import Witness, Witnesses, WitnessesRankedByVote, WitnessesVotedByAccount

from .nodes import get_hive_nodes

wif = "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bts = Hive(
            node=get_hive_nodes(),
            nobroadcast=True,
            unsigned=True,
            keys={"active": wif},
            num_retries=10,
        )
        cls.hiveio = Hive(
            node=get_hive_nodes(),
            nobroadcast=True,
            unsigned=True,
            keys={"active": wif},
            num_retries=10,
        )
        # from getpass import getpass
        # self.bts.wallet.unlock(getpass())
        set_shared_blockchain_instance(cls.bts)
        cls.bts.set_default_account("test")

    @staticmethod
    def _extract_op(tx):
        op = tx["operations"][0]
        if isinstance(op, dict):
            name = op.get("type") or op.get("operation")
            if name and name.endswith("_operation"):
                name = name[: -len("_operation")]
            return name, op.get("value", {})
        elif isinstance(op, (list, tuple)) and len(op) >= 2:
            return op[0], op[1]
        return None, op

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_feed_publish(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        bts.txbuffer.clear()
        w = Witness("gtg", blockchain_instance=bts)
        tx = w.feed_publish("4 %s" % bts.backed_token_symbol, "1 %s" % bts.token_symbol)
        op_name, op = self._extract_op(tx)
        self.assertEqual(op_name, "feed_publish")
        self.assertIn("gtg", op["publisher"])

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_update(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        bts.txbuffer.clear()
        w = Witness("gtg", blockchain_instance=bts)
        props = {
            "account_creation_fee": "0.1 %s" % bts.token_symbol,
            "maximum_block_size": 32000,
            "sbd_interest_rate": 0,
        }
        tx = w.update(wif, "", props)
        op_name, op = self._extract_op(tx)
        self.assertEqual(op_name, "witness_update")
        self.assertIn("gtg", op["owner"])

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_witnesses(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        w = Witnesses(blockchain_instance=bts)
        w.printAsTable()
        self.assertTrue(len(w) > 0)
        self.assertTrue(isinstance(w[0], Witness))

    @parameterized.expand(
        [
            ("normal"),
        ]
    )
    def test_WitnessesVotedByAccount(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        w = WitnessesVotedByAccount("gtg", blockchain_instance=bts)
        w.printAsTable()
        self.assertTrue(len(w) > 0)
        self.assertTrue(isinstance(w[0], Witness))

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_WitnessesRankedByVote(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        w = WitnessesRankedByVote(blockchain_instance=bts)
        w.printAsTable()
        self.assertTrue(len(w) > 0)
        self.assertTrue(isinstance(w[0], Witness))

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_export(self, node_param):
        if node_param == "normal":
            bts = self.bts
        else:
            bts = self.hiveio
        owner = "gtg"
        witness = bts.rpc.find_witnesses({"owners": [owner]}, api="database_api")["witnesses"]
        if len(witness) > 0:
            witness = witness[0]

        w = Witness(owner, blockchain_instance=bts)
        keys = list(witness.keys())
        json_witness = w.json()
        exclude_list = [
            "votes",
            "virtual_last_update",
            "virtual_scheduled_time",
            "last_aslot",
            "last_confirmed_block_num",
            "available_witness_account_subsidies",
        ]
        for k in keys:
            if k not in exclude_list:
                if isinstance(witness[k], dict) and isinstance(json_witness[k], list):
                    self.assertEqual(list(witness[k].values()), json_witness[k])
                else:
                    self.assertEqual(witness[k], json_witness[k])
