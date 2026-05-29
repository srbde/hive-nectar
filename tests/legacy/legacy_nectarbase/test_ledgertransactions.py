import pytest

pytest.skip(
    "Skipping legacy Hive ledger serialization tests (migrated to Hive)", allow_module_level=True
)

import unittest
from binascii import hexlify

from nectar.amount import Amount
from nectar.hive import Hive
from nectarbase import operations
from nectarbase.ledgertransactions import Ledger_Transaction
from nectarbase.objects import Operation

TEST_AGAINST_CLI_WALLET = False

prefix = "STEEM"
default_prefix = "STM"
ref_block_num = 34843
ref_block_prefix = 1663841413
expiration = "2020-05-10T20:30:57"
path = "48'/13'/0'/0'/0'"


class Testcases(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.hv = Hive(offline=True)

    def doit(self, printWire=False, ops=None):
        if ops is None:
            ops = [Operation(self.op)]
        tx = Ledger_Transaction(
            ref_block_num=ref_block_num,
            ref_block_prefix=ref_block_prefix,
            expiration=expiration,
            operations=ops,
        )
        txWire = hexlify(bytes(tx)).decode("ascii")
        txApdu = tx.build_apdu(path, chain=prefix)
        if printWire:
            print()
            print(txWire)
            print()
        if len(self.cm) > 0:
            self.assertEqual(self.cm, txWire)
        if len(self.apdu) > 0:
            self.assertEqual(len(self.apdu), len(txApdu))
            for i in range(len(txApdu)):
                self.assertEqual(self.apdu[i], hexlify(txApdu[i]))

    def test_Transfer(self):
        self.op = operations.Transfer(
            **{
                "from": "nettybot",
                "to": "netuoso",
                "amount": Amount("0.001 STEEM", blockchain_instance=self.hv),
                "memo": "",
                "prefix": default_prefix,
            }
        )
        self.apdu = [
            b"d40400007205800000308000000d80000000800000008000000004"
            b"200000000000000000000000000000000000000000000000000000"
            b"00000000000004021b88040485342c6304048164b85e0401010423"
            b"02086e65747479626f74076e6574756f736f010000000000000003"
            b"535445454d000000040100"
        ]
        self.cm = "04021b88040485342c6304048164b85e040101042302086e65747479626f74076e6574756f736f010000000000000003535445454d000000040100"
        self.doit()

    def test_createclaimedaccount(self):
        self.op = operations.Create_claimed_account(
            **{
                "creator": "netuoso",
                "new_account_name": "netuoso2",
                "owner": {
                    "weight_threshold": 1,
                    "account_auths": [],
                    "key_auths": [["STM7QtTRvd1owAh4uGaC6trxjR9M1cpqfi2WfLQed1GbUGPomt9DP", 1]],
                },
                "active": {
                    "weight_threshold": 1,
                    "account_auths": [],
                    "key_auths": [["STM7QtTRvd1owAh4uGaC6trxjR9M1cpqfi2WfLQed1GbUGPomt9DP", 1]],
                },
                "posting": {
                    "weight_threshold": 1,
                    "account_auths": [],
                    "key_auths": [["STM7QtTRvd1owAh4uGaC6trxjR9M1cpqfi2WfLQed1GbUGPomt9DP", 1]],
                },
                "memo_key": "STM7QtTRvd1owAh4uGaC6trxjR9M1cpqfi2WfLQed1GbUGPomt9DP",
                "json_metadata": "{}",
            }
        )
        self.apdu = [
            b"d4040000dd05800000308000000d800000008000000080000000042000000000000000000000000000000000000000000000000000000000000000000402bd8c04045fe26f450404f179a8570401010481b217076e6574756f736f086e6574756f736f32010000000001034c6a518a9b9e9cb8099176854a322c87db6c7e82c47bd5fe68c273ba63a647160100010000000001034c6a518a9b9e9cb8099176854a322c87db6c7e82c47bd5fe68c273ba63a647160100010000000001034c6a518a9b9e9cb8099176854a322c87db6c7e82c47bd5fe68c273ba63a647160100034c6a",
            b"d404800025518a9b9e9cb8099176854a322c87db6c7e82c47bd5fe68c273ba63a6471600000000040100",
        ]

    def test_vote(self):
        self.op = operations.Vote(
            **{
                "voter": "nettybot",
                "author": "jrcornel",
                "permlink": "hive-sitting-back-at-previous-support-levels-is-this-a-buy",
                "weight": 10000,
            }
        )
        self.cm = b"0402528804049ce2ccea04047660b85e040101045000086e65747479626f74086a72636f726e656c3a686976652d73697474696e672d6261636b2d61742d70726576696f75732d737570706f72742d6c6576656c732d69732d746869732d612d6275791027040100"
        self.apdu = [
            b"d40400009f05800000308000000d800000008000000080000000042000000000000000000000000000000000000000000000000000000000000000000402528804049ce2ccea04047660b85e040101045000086e65747479626f74086a72636f726e656c3a686976652d73697474696e672d6261636b2d61742d70726576696f75732d737570706f72742d6c6576656c732d69732d746869732d612d6275791027040100"
        ]

    def test_pubkey(self):
        tx = Ledger_Transaction(
            ref_block_num=ref_block_num,
            ref_block_prefix=ref_block_prefix,
            expiration=expiration,
            operations=[],
        )
        apdu = tx.build_apdu_pubkey()
        self.assertEqual(
            bytes(apdu),
            b"\xd4\x02\x00\x01\x15\x05\x80\x00\x00\x80\x00\x00\r\x80\x00\x00\x00\x80\x00\x00\x00\x80\x00\x00\x00",
        )
