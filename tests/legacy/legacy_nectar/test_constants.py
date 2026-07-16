import unittest

from nectar import Hive, constants

from .nodes import get_hive_nodes

wif = "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Create a class-level Hive client for tests and assign it to cls.appbase.

        Initializes a Hive instance using get_hive_nodes() and configures it for local testing:
        nobroadcast=True (no real broadcasts), bundle=False, keys overridden to use the test
        private key for the "active" role, and num_retries=10.
        """
        cls.appbase = Hive(
            node=get_hive_nodes(),
            nobroadcast=True,
            bundle=False,
            # Overwrite wallet to use this list of wifs only
            keys={"active": wif},
            num_retries=10,
        )

    def test_constants(self):
        hv = self.appbase
        hive_conf = hv.get_config()
        if "HIVE_100_PERCENT" in hive_conf:
            HIVE_100_PERCENT = hive_conf["HIVE_100_PERCENT"]
            self.assertEqual(constants.HIVE_100_PERCENT, HIVE_100_PERCENT)

        if "HIVE_1_PERCENT" in hive_conf:
            HIVE_1_PERCENT = hive_conf["HIVE_1_PERCENT"]
            self.assertEqual(constants.HIVE_1_PERCENT, HIVE_1_PERCENT)

        if "HIVE_REVERSE_AUCTION_WINDOW_SECONDS" in hive_conf:
            HIVE_REVERSE_AUCTION_WINDOW_SECONDS = hive_conf["HIVE_REVERSE_AUCTION_WINDOW_SECONDS"]
        elif "HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF6" in hive_conf:
            HIVE_REVERSE_AUCTION_WINDOW_SECONDS = hive_conf[
                "HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF6"
            ]
        self.assertEqual(
            constants.HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF6, HIVE_REVERSE_AUCTION_WINDOW_SECONDS
        )

        if "HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF20" in hive_conf:
            self.assertEqual(
                constants.HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF20,
                hive_conf["HIVE_REVERSE_AUCTION_WINDOW_SECONDS_HF20"],
            )

        if "HIVE_VOTE_DUST_THRESHOLD" in hive_conf:
            self.assertEqual(
                constants.HIVE_VOTE_DUST_THRESHOLD, hive_conf["HIVE_VOTE_DUST_THRESHOLD"]
            )

        if "HIVE_VOTE_REGENERATION_SECONDS" in hive_conf:
            HIVE_VOTE_REGENERATION_SECONDS = hive_conf["HIVE_VOTE_REGENERATION_SECONDS"]
            self.assertEqual(
                constants.HIVE_VOTE_REGENERATION_SECONDS, HIVE_VOTE_REGENERATION_SECONDS
            )
        elif "HIVE_VOTING_MANA_REGENERATION_SECONDS" in hive_conf:
            HIVE_VOTING_MANA_REGENERATION_SECONDS = hive_conf[
                "HIVE_VOTING_MANA_REGENERATION_SECONDS"
            ]
            self.assertEqual(
                constants.HIVE_VOTING_MANA_REGENERATION_SECONDS,
                HIVE_VOTING_MANA_REGENERATION_SECONDS,
            )

        if "HIVE_ROOT_POST_PARENT" in hive_conf:
            HIVE_ROOT_POST_PARENT = hive_conf["HIVE_ROOT_POST_PARENT"]
            self.assertEqual(constants.HIVE_ROOT_POST_PARENT, HIVE_ROOT_POST_PARENT)
