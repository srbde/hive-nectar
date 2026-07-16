import unittest

from nectar import Hive
from nectar.amount import Amount
from nectar.asset import Asset
from nectar.instance import set_shared_blockchain_instance
from nectar.market import Market
from nectar.price import Price

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

    def test_market(self):
        bts = self.bts
        m1 = Market("HIVE", "HBD", blockchain_instance=bts)
        self.assertEqual(m1.get_string(), "HBD:HIVE")
        m2 = Market(blockchain_instance=bts)
        self.assertEqual(m2.get_string(), "HBD:HIVE")
        m3 = Market("HIVE:HBD", blockchain_instance=bts)
        self.assertEqual(m3.get_string(), "HIVE:HBD")
        self.assertTrue(m1 == m2)

        base = Asset("HBD", blockchain_instance=bts)
        quote = Asset("HIVE", blockchain_instance=bts)
        m = Market(base, quote, blockchain_instance=bts)
        self.assertEqual(m.get_string(), "HIVE:HBD")

    def test_ticker(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        ticker = m.ticker()
        self.assertEqual(len(ticker), 6)
        if "hive_volume" in ticker:
            self.assertEqual(ticker["hive_volume"]["symbol"], "HIVE")
            self.assertEqual(ticker["hbd_volume"]["symbol"], "HBD")

    def test_volume(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        volume = m.volume24h()
        self.assertEqual(volume["HIVE"]["symbol"], "HIVE")
        self.assertEqual(volume["HBD"]["symbol"], "HBD")

    def test_orderbook(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        orderbook = m.orderbook(limit=10)
        self.assertEqual(len(orderbook["asks_date"]), 10)
        self.assertEqual(len(orderbook["asks"]), 10)
        self.assertEqual(len(orderbook["bids_date"]), 10)
        self.assertEqual(len(orderbook["bids"]), 10)

    def test_recenttrades(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        recenttrades = m.recent_trades(limit=10)
        recenttrades_raw = m.recent_trades(limit=10, raw_data=True)
        self.assertEqual(len(recenttrades), 10)
        self.assertEqual(len(recenttrades_raw), 10)

    def test_trades(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        trades = m.trades(limit=10)
        trades_raw = m.trades(limit=10, raw_data=True)
        trades_history = m.trade_history(limit=10)
        self.assertEqual(len(trades), 10)
        self.assertTrue(len(trades_history) > 0)
        self.assertEqual(len(trades_raw), 10)

    def test_market_history(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        buckets = m.market_history_buckets()
        history = m.market_history(buckets[2])
        self.assertTrue(len(history) > 0)

    def test_accountopenorders(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        openOrder = m.accountopenorders("test")
        self.assertTrue(isinstance(openOrder, list))

    def test_buy(self):
        bts = self.bts
        m = Market("HIVE:HBD", blockchain_instance=bts)
        bts.txbuffer.clear()
        tx = m.buy(5, 0.1, account="test")
        op_name, op = self._extract_op(tx)
        self.assertEqual(op_name, "limit_order_create")
        self.assertIn("test", op["owner"])
        self.assertEqual(
            Amount(op["min_to_receive"], blockchain_instance=bts),
            Amount("0.100 HIVE", blockchain_instance=bts),
        )
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )

        p = Price(5, "HBD:HIVE", blockchain_instance=bts)
        tx = m.buy(p, 0.1, account="test")
        _, op = self._extract_op(tx)
        self.assertEqual(
            Amount(op["min_to_receive"], blockchain_instance=bts),
            Amount("0.100 HIVE", blockchain_instance=bts),
        )
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )

        p = Price(5, "HBD:HIVE", blockchain_instance=bts)
        a = Amount(0.1, "HIVE", blockchain_instance=bts)
        tx = m.buy(p, a, account="test")
        _, op = self._extract_op(tx)
        self.assertEqual(Amount(op["min_to_receive"], blockchain_instance=bts), Amount(a))
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )

    def test_sell(self):
        bts = self.bts
        bts.txbuffer.clear()
        m = Market("HIVE:HBD", blockchain_instance=bts)
        tx = m.sell(5, 0.1, account="test")
        op_name, op = self._extract_op(tx)
        self.assertEqual(op_name, "limit_order_create")
        self.assertIn("test", op["owner"])
        self.assertEqual(
            Amount(op["min_to_receive"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.100 HIVE", blockchain_instance=bts),
        )

        p = Price(5, "HBD:HIVE")
        tx = m.sell(p, 0.1, account="test")
        _, op = self._extract_op(tx)
        self.assertEqual(
            Amount(op["min_to_receive"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.100 HIVE", blockchain_instance=bts),
        )

        p = Price(5, "HBD:HIVE", blockchain_instance=bts)
        a = Amount(0.1, "HIVE", blockchain_instance=bts)
        tx = m.sell(p, a, account="test")
        _, op = self._extract_op(tx)
        self.assertEqual(
            Amount(op["min_to_receive"], blockchain_instance=bts),
            Amount("0.500 HBD", blockchain_instance=bts),
        )
        self.assertEqual(
            Amount(op["amount_to_sell"], blockchain_instance=bts),
            Amount("0.100 HIVE", blockchain_instance=bts),
        )

    def test_cancel(self):
        bts = self.bts
        bts.txbuffer.clear()
        m = Market("HIVE:HBD", blockchain_instance=bts)
        tx = m.cancel(5, account="test")
        op_name, op = self._extract_op(tx)
        self.assertEqual(op_name, "limit_order_cancel")
        self.assertIn("test", op["owner"])
