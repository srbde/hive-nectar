import unittest

from nectarapi.openapi import get_default_api_for_method


class TestOpenAPIMap(unittest.TestCase):
    def test_method_lookup(self):
        # Sanity check a few known methods from the hived OpenAPI spec
        self.assertEqual(get_default_api_for_method("get_account_history"), "account_history_api")
        self.assertEqual(
            get_default_api_for_method("broadcast_transaction"), "network_broadcast_api"
        )
        self.assertEqual(get_default_api_for_method("get_accounts"), "database_api")
        # Unknown methods return None
        self.assertIsNone(get_default_api_for_method("non_existing_method"))


if __name__ == "__main__":
    unittest.main()
