import unittest

from parameterized import parameterized

from nectar import Hive
from nectar.asset import Asset
from nectar.exceptions import AssetDoesNotExistsException
from nectar.instance import set_shared_blockchain_instance

from .nodes import get_hive_nodes


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Initialize class-level Hive instances for tests and register the shared blockchain instance.

        Creates two Hive clients on the test class:
        - cls.bts: uses nodes from get_hive_nodes(), with broadcasting disabled and retries set to 10.
        - cls.hiveio: connected to "https://api.hive.blog", with broadcasting disabled and retries set to 10.

        Registers cls.bts as the global shared blockchain instance via set_shared_blockchain_instance, which is a global side effect relied on by tests.
        """
        cls.bts = Hive(node=get_hive_nodes(), nobroadcast=True, num_retries=10)
        cls.hiveio = Hive(node="https://api.hive.blog", nobroadcast=True, num_retries=10)
        set_shared_blockchain_instance(cls.bts)

    @parameterized.expand(
        [
            ("normal"),
            ("hiveio"),
        ]
    )
    def test_assert(self, node_param):
        if node_param == "normal":
            hv = self.bts
        else:
            hv = self.hiveio
        with self.assertRaises(AssetDoesNotExistsException):
            Asset("FOObarNonExisting", full=False, blockchain_instance=hv)

    @parameterized.expand(
        [
            ("normal", "HBD", "HBD", 3, "@@000000013"),
            ("normal", "HIVE", "HIVE", 3, "@@000000021"),
            ("normal", "VESTS", "VESTS", 6, "@@000000037"),
            ("normal", "@@000000013", "HBD", 3, "@@000000013"),
            ("normal", "@@000000021", "HIVE", 3, "@@000000021"),
            ("normal", "@@000000037", "VESTS", 6, "@@000000037"),
        ]
    )
    def test_properties(self, node_param, data, symbol_str, precision, asset_str):
        if node_param == "normal":
            hv = self.bts
        else:
            hv = self.hiveio
        asset = Asset(data, full=False, blockchain_instance=hv)
        self.assertEqual(asset.symbol, symbol_str)
        self.assertEqual(asset.precision, precision)
        self.assertEqual(asset.asset, asset_str)

    def test_assert_equal(self):
        hv = self.bts
        asset1 = Asset("HBD", full=False, blockchain_instance=hv)
        asset2 = Asset("HBD", full=False, blockchain_instance=hv)
        self.assertTrue(asset1 == asset2)
        self.assertTrue(asset1 == "HBD")
        self.assertTrue(asset2 == "HBD")
        asset3 = Asset("HIVE", full=False, blockchain_instance=hv)
        self.assertTrue(asset1 != asset3)
        self.assertTrue(asset3 != "HBD")
        self.assertTrue(asset1 != "HIVE")

        a = {"asset": "@@000000021", "precision": 3, "id": "HIVE", "symbol": "HIVE"}
        b = {"asset": "@@000000021", "precision": 3, "id": "@@000000021", "symbol": "HIVE"}
        self.assertTrue(Asset(a, blockchain_instance=hv) == Asset(b, blockchain_instance=hv))

    """
    # Mocker comes from pytest-mock, providing an easy way to have patched objects
    # for the life of the test.
    def test_calls(mocker):
        asset = Asset("USD", lazy=True, blockchain_instance=Hive(offline=True))
        method = mocker.patch.object(Asset, 'get_call_orders')
        asset.calls
        method.assert_called_with(10)
    """
