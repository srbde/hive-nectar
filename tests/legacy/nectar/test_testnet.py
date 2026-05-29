import random
import string

# Py3 compatibility
import sys
import unittest

from nectar import Hive
from nectar.account import Account
from nectar.amount import Amount
from nectar.exceptions import InvalidWifError, MissingKeyError
from nectar.instance import shared_blockchain_instance
from nectar.memo import Memo
from nectar.nodelist import NodeList
from nectar.transactionbuilder import TransactionBuilder
from nectarapi import exceptions
from nectarbase.operations import Transfer
from nectargraphenebase.account import PrivateKey, PublicKey

core_unit = "STX"


class Testcases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nodelist = NodeList()
        # hv = shared_blockchain_instance()
        # hv.config.refreshBackup()
        # nodes = nodelist.get_testnet()
        cls.nodes = nodelist.get_nodes()
        cls.bts = Hive(
            node=cls.nodes,
            nobroadcast=True,
            num_retries=10,
            expiration=120,
        )
        # from getpass import getpass
        # self.bts.wallet.unlock(getpass())
        cls.bts.set_default_account("nectar")

        # Test account "nectar"
        cls.active_key = "5Jt2wTfhUt5GkZHV1HYVfkEaJ6XnY8D2iA4qjtK9nnGXAhThM3w"
        cls.posting_key = "5Jh1Gtu2j4Yi16TfhoDmg8Qj3ULcgRi7A49JXdfUUTVPkaFaRKz"
        cls.memo_key = "5KPbCuocX26aMxN9CDPdUex4wCbfw9NoT5P7UhcqgDwxXa47bit"

        # Test account "nectar1"
        cls.active_key1 = "5Jo9SinzpdAiCDLDJVwuN7K5JcusKmzFnHpEAtPoBHaC1B5RDUd"
        cls.posting_key1 = "5JGNhDXuDLusTR3nbmpWAw4dcmE8WfSM8odzqcQ6mDhJHP8YkQo"
        cls.memo_key1 = "5KA2ddfAffjfRFoe1UhQjJtKnGsBn9xcsdPQTfMt1fQuErDAkWr"

        cls.active_private_key_of_nectar4 = "5JkZZEUWrDsu3pYF7aknSo7BLJx7VfxB3SaRtQaHhsPouDYjxzi"
        cls.active_private_key_of_nectar5 = "5Hvbm9VjRbd1B3ft8Lm81csaqQudwFwPGdiRKrCmTKcomFS3Z9J"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        raise unittest.SkipTest()
        hv = self.bts
        hv.nobroadcast = True
        hv.wallet.wipe(True)
        hv.wallet.create("123")
        hv.wallet.unlock("123")

        hv.wallet.addPrivateKey(self.active_key1)
        hv.wallet.addPrivateKey(self.memo_key1)
        hv.wallet.addPrivateKey(self.posting_key1)

        hv.wallet.addPrivateKey(self.active_key)
        hv.wallet.addPrivateKey(self.memo_key)
        hv.wallet.addPrivateKey(self.posting_key)
        hv.wallet.addPrivateKey(self.active_private_key_of_nectar4)
        hv.wallet.addPrivateKey(self.active_private_key_of_nectar5)

    @classmethod
    def tearDownClass(cls):
        hv = shared_blockchain_instance()
        hv.config.recover_with_latest_backup()

    def test_wallet_keys(self):
        hv = self.bts
        hv.wallet.unlock("123")
        priv_key = hv.wallet.getPrivateKeyForPublicKey(
            str(PrivateKey(self.posting_key, prefix=hv.prefix).pubkey)
        )
        self.assertEqual(str(priv_key), self.posting_key)
        priv_key = hv.wallet.getKeyForAccount("nectar", "active")
        self.assertEqual(str(priv_key), self.active_key)
        priv_key = hv.wallet.getKeyForAccount("nectar1", "posting")
        self.assertEqual(str(priv_key), self.posting_key1)

        priv_key = hv.wallet.getPrivateKeyForPublicKey(
            str(PrivateKey(self.active_private_key_of_nectar4, prefix=hv.prefix).pubkey)
        )
        self.assertEqual(str(priv_key), self.active_private_key_of_nectar4)
        priv_key = hv.wallet.getKeyForAccount("nectar4", "active")
        self.assertEqual(str(priv_key), self.active_private_key_of_nectar4)

        priv_key = hv.wallet.getPrivateKeyForPublicKey(
            str(PrivateKey(self.active_private_key_of_nectar5, prefix=hv.prefix).pubkey)
        )
        self.assertEqual(str(priv_key), self.active_private_key_of_nectar5)
        priv_key = hv.wallet.getKeyForAccount("nectar5", "active")
        self.assertEqual(str(priv_key), self.active_private_key_of_nectar5)

    def test_transfer(self):
        bts = self.bts
        bts.nobroadcast = False
        bts.wallet.unlock("123")
        # bts.wallet.addPrivateKey(self.active_key)
        # bts.prefix ="STX"
        acc = Account("nectar", blockchain_instance=bts)
        tx = acc.transfer("nectar1", 1.33, "HBD", memo="Foobar")
        self.assertEqual(tx["operations"][0][0], "transfer")
        self.assertEqual(len(tx["signatures"]), 1)
        op = tx["operations"][0][1]
        self.assertIn("memo", op)
        self.assertEqual(op["from"], "nectar")
        self.assertEqual(op["to"], "nectar1")
        amount = Amount(op["amount"], blockchain_instance=bts)
        self.assertEqual(float(amount), 1.33)
        bts.nobroadcast = True

    def test_transfer_memo(self):
        bts = self.bts
        bts.nobroadcast = False
        bts.wallet.unlock("123")
        acc = Account("nectar", blockchain_instance=bts)
        tx = acc.transfer("nectar1", 1.33, "HBD", memo="#Foobar")
        self.assertEqual(tx["operations"][0][0], "transfer")
        op = tx["operations"][0][1]
        self.assertIn("memo", op)
        self.assertIn("#", op["memo"])
        m = Memo(from_account=op["from"], to_account=op["to"], blockchain_instance=bts)
        memo = m.decrypt(op["memo"])
        self.assertEqual(memo, "Foobar")

        self.assertEqual(op["from"], "nectar")
        self.assertEqual(op["to"], "nectar1")
        amount = Amount(op["amount"], blockchain_instance=bts)
        self.assertEqual(float(amount), 1.33)
        bts.nobroadcast = True

    def test_transfer_1of1(self):
        hive = self.bts
        hive.nobroadcast = False
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("0.01 STEEM", blockchain_instance=hive),
                    "memo": "1 of 1 transaction",
                }
            )
        )
        self.assertEqual(tx["operations"][0]["type"], "transfer_operation")
        tx.appendWif(self.active_key)
        tx.sign()
        tx.sign()
        self.assertEqual(len(tx["signatures"]), 1)
        tx.broadcast()
        hive.nobroadcast = True

    def test_transfer_2of2_simple(self):
        # Send a 2 of 2 transaction from elf which needs nectar4's cosign to send funds
        hive = self.bts
        hive.nobroadcast = False
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar5",
                    "to": "nectar1",
                    "amount": Amount("0.01 HIVE", blockchain_instance=hive),
                    "memo": "2 of 2 simple transaction",
                }
            )
        )

        tx.appendWif(self.active_private_key_of_nectar5)
        tx.sign()
        tx.clearWifs()
        tx.appendWif(self.active_private_key_of_nectar4)
        tx.sign(reconstruct_tx=False)
        self.assertEqual(len(tx["signatures"]), 2)
        tx.broadcast()
        hive.nobroadcast = True

    def test_transfer_2of2_wallet(self):
        # Send a 2 of 2 transaction from nectar5 which needs nectar4's cosign to send
        # priv key of nectar5 and nectar4 are stored in the wallet
        # appendSigner fetches both keys and signs automatically with both keys.
        hive = self.bts
        hive.nobroadcast = False
        hive.wallet.unlock("123")

        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar5",
                    "to": "nectar1",
                    "amount": Amount("0.01 HIVE", blockchain_instance=hive),
                    "memo": "2 of 2 serialized/deserialized transaction",
                }
            )
        )

        tx.appendSigner("nectar5", "active")
        tx.sign()
        self.assertEqual(len(tx["signatures"]), 2)
        tx.broadcast()
        hive.nobroadcast = True

    def test_transfer_2of2_serialized_deserialized(self):
        # Send a 2 of 2 transaction from nectar5 which needs nectar4's cosign to send
        # funds but sign the transaction with nectar5's key and then serialize the transaction
        # and deserialize the transaction.  After that, sign with nectar4's key.
        hive = self.bts
        hive.nobroadcast = False
        hive.wallet.unlock("123")
        # hive.wallet.removeAccount("nectar4")
        hive.wallet.removePrivateKeyFromPublicKey(
            str(PublicKey(self.active_private_key_of_nectar4, prefix=core_unit))
        )

        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar5",
                    "to": "nectar1",
                    "amount": Amount("0.01 STEEM", blockchain_instance=hive),
                    "memo": "2 of 2 serialized/deserialized transaction",
                }
            )
        )

        tx.appendSigner("nectar5", "active")
        tx.addSigningInformation("nectar5", "active")
        tx.sign()
        tx.clearWifs()
        self.assertEqual(len(tx["signatures"]), 1)
        # hive.wallet.removeAccount("nectar5")
        hive.wallet.removePrivateKeyFromPublicKey(
            str(PublicKey(self.active_private_key_of_nectar5, prefix=core_unit))
        )
        tx_json = tx.json()
        del tx
        new_tx = TransactionBuilder(tx=tx_json, blockchain_instance=hive)
        self.assertEqual(len(new_tx["signatures"]), 1)
        hive.wallet.addPrivateKey(self.active_private_key_of_nectar4)
        new_tx.appendMissingSignatures()
        new_tx.sign(reconstruct_tx=False)
        self.assertEqual(len(new_tx["signatures"]), 2)
        new_tx.broadcast()
        hive.nobroadcast = True

    def test_transfer_2of2_offline(self):
        # Send a 2 of 2 transaction from nectar5 which needs nectar4's cosign to send
        # funds but sign the transaction with nectar5's key and then serialize the transaction
        # and deserialize the transaction.  After that, sign with nectar4's key.
        hive = self.bts
        hive.nobroadcast = False
        hive.wallet.unlock("123")
        # hive.wallet.removeAccount("nectar4")
        hive.wallet.removePrivateKeyFromPublicKey(
            str(PublicKey(self.active_private_key_of_nectar4, prefix=core_unit))
        )

        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar5",
                    "to": "nectar",
                    "amount": Amount("0.01 STEEM", blockchain_instance=hive),
                    "memo": "2 of 2 serialized/deserialized transaction",
                }
            )
        )

        tx.appendSigner("nectar5", "active")
        tx.addSigningInformation("nectar5", "active")
        tx.sign()
        tx.clearWifs()
        self.assertEqual(len(tx["signatures"]), 1)
        # hive.wallet.removeAccount("nectar5")
        hive.wallet.removePrivateKeyFromPublicKey(
            str(PublicKey(self.active_private_key_of_nectar5, prefix=core_unit))
        )
        hive.wallet.addPrivateKey(self.active_private_key_of_nectar4)
        tx.appendMissingSignatures()
        tx.sign(reconstruct_tx=False)
        self.assertEqual(len(tx["signatures"]), 2)
        tx.broadcast()
        hive.nobroadcast = True
        hive.wallet.addPrivateKey(self.active_private_key_of_nectar5)

    def test_transfer_2of2_wif(self):
        _ = NodeList()
        # Send a 2 of 2 transaction from elf which needs nectar4's cosign to send
        # funds but sign the transaction with elf's key and then serialize the transaction
        # and deserialize the transaction.  After that, sign with nectar4's key.
        hive = Hive(
            node=self.nodes,
            num_retries=10,
            keys=[self.active_private_key_of_nectar5],
            expiration=360,
        )

        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hive)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar5",
                    "to": "nectar",
                    "amount": Amount("0.01 HIVE", blockchain_instance=hive),
                    "memo": "2 of 2 serialized/deserialized transaction",
                }
            )
        )

        tx.appendSigner("nectar5", "active")
        tx.addSigningInformation("nectar5", "active")
        tx.sign()
        tx.clearWifs()
        self.assertEqual(len(tx["signatures"]), 1)
        tx_json = tx.json()
        del hive
        del tx

        hive = Hive(
            node=self.nodes,
            num_retries=10,
            keys=[self.active_private_key_of_nectar4],
            expiration=360,
        )
        new_tx = TransactionBuilder(tx=tx_json, blockchain_instance=hive)
        new_tx.appendMissingSignatures()
        new_tx.sign(reconstruct_tx=False)
        self.assertEqual(len(new_tx["signatures"]), 2)
        new_tx.broadcast()

    def test_verifyAuthority(self):
        hv = self.bts
        hv.wallet.unlock("123")
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hv)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("1.300 HBD", blockchain_instance=hv),
                    "memo": "Foobar",
                }
            )
        )
        account = Account("nectar", blockchain_instance=hv)
        tx.appendSigner(account, "active")
        self.assertTrue(len(tx.wifs) > 0)
        tx.sign()
        tx.verify_authority()
        self.assertTrue(len(tx["signatures"]) > 0)

    def test_create_account(self):
        bts = self.bts
        name = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        key1 = PrivateKey()
        key2 = PrivateKey()
        key3 = PrivateKey()
        key4 = PrivateKey()
        key5 = PrivateKey()
        tx = bts.create_account(
            name,
            creator="nectar",
            owner_key=format(key1.pubkey, core_unit),
            active_key=format(key2.pubkey, core_unit),
            posting_key=format(key3.pubkey, core_unit),
            memo_key=format(key4.pubkey, core_unit),
            additional_owner_keys=[format(key5.pubkey, core_unit)],
            additional_active_keys=[format(key5.pubkey, core_unit)],
            additional_owner_accounts=["nectar1"],  # 1.2.0
            additional_active_accounts=["nectar1"],
            storekeys=False,
        )
        self.assertEqual(tx["operations"][0][0], "account_create")
        op = tx["operations"][0][1]
        role = "active"
        self.assertIn(format(key5.pubkey, core_unit), [x[0] for x in op[role]["key_auths"]])
        self.assertIn(format(key5.pubkey, core_unit), [x[0] for x in op[role]["key_auths"]])
        self.assertIn("nectar1", [x[0] for x in op[role]["account_auths"]])
        role = "owner"
        self.assertIn(format(key5.pubkey, core_unit), [x[0] for x in op[role]["key_auths"]])
        self.assertIn(format(key5.pubkey, core_unit), [x[0] for x in op[role]["key_auths"]])
        self.assertIn("nectar1", [x[0] for x in op[role]["account_auths"]])
        self.assertEqual(op["creator"], "nectar")

    def test_connect(self):
        _ = NodeList()
        self.bts.connect(node=self.nodes)
        bts = self.bts
        self.assertEqual(bts.prefix, "STX")

    def test_set_default_account(self):
        self.bts.set_default_account("nectar")

    def test_info(self):
        info = self.bts.info()
        for key in [
            "current_witness",
            "head_block_id",
            "head_block_number",
            "id",
            "last_irreversible_block_num",
            "current_witness",
            "total_pow",
            "time",
        ]:
            self.assertTrue(key in info)

    def test_finalizeOps(self):
        bts = self.bts
        tx1 = bts.new_tx()
        tx2 = bts.new_tx()

        acc = Account("nectar", blockchain_instance=bts)
        acc.transfer("nectar1", 1, "STEEM", append_to=tx1)
        acc.transfer("nectar1", 2, "STEEM", append_to=tx2)
        acc.transfer("nectar1", 3, "STEEM", append_to=tx1)
        tx1 = tx1.json()
        tx2 = tx2.json()
        ops1 = tx1["operations"]
        ops2 = tx2["operations"]
        self.assertEqual(len(ops1), 2)
        self.assertEqual(len(ops2), 1)

    def test_weight_threshold(self):
        bts = self.bts
        auth = {
            "account_auths": [["test", 1]],
            "extensions": [],
            "key_auths": [
                ["STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n", 1],
                ["STX7GM9YXcsoAJAgKbqW2oVj7bnNXFNL4pk9NugqKWPmuhoEDbkDv", 1],
            ],
            "weight_threshold": 3,
        }  # threshold fine
        bts._test_weights_treshold(auth)
        auth = {
            "account_auths": [["test", 1]],
            "extensions": [],
            "key_auths": [
                ["STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n", 1],
                ["STX7GM9YXcsoAJAgKbqW2oVj7bnNXFNL4pk9NugqKWPmuhoEDbkDv", 1],
            ],
            "weight_threshold": 4,
        }  # too high

        with self.assertRaises(ValueError):
            bts._test_weights_treshold(auth)

    def test_allow(self):
        bts = self.bts
        self.assertIn(bts.prefix, "STX")
        acc = Account("nectar", blockchain_instance=bts)
        self.assertIn(acc.hive.prefix, "STX")
        tx = acc.allow(
            "STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n",
            account="nectar",
            weight=1,
            threshold=1,
            permission="active",
        )
        self.assertEqual((tx["operations"][0][0]), "account_update")
        op = tx["operations"][0][1]
        self.assertIn("active", op)
        self.assertIn(
            ["STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n", "1"],
            op["active"]["key_auths"],
        )
        self.assertEqual(op["active"]["weight_threshold"], 1)

    def test_disallow(self):
        bts = self.bts
        acc = Account("nectar", blockchain_instance=bts)
        if sys.version > "3":
            _assertRaisesRegex = self.assertRaisesRegex
        else:
            _assertRaisesRegex = self.assertRaisesRegexp
        with _assertRaisesRegex(ValueError, ".*Changes nothing.*"):
            acc.disallow(
                "STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n",
                weight=1,
                threshold=1,
                permission="active",
            )
        with _assertRaisesRegex(ValueError, ".*Changes nothing!.*"):
            acc.disallow(
                "STX6MRyAjQq8ud7hVNYcfnVPJqcVpscN5So8BhtHuGYqET5GDW5CV",
                weight=1,
                threshold=1,
                permission="active",
            )

    def test_update_memo_key(self):
        bts = self.bts
        bts.wallet.unlock("123")
        self.assertEqual(bts.prefix, "STX")
        acc = Account("nectar", blockchain_instance=bts)
        tx = acc.update_memo_key("STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n")
        self.assertEqual((tx["operations"][0][0]), "account_update")
        op = tx["operations"][0][1]
        self.assertEqual(op["memo_key"], "STX55VCzsb47NZwWe5F3qyQKedX9iHBHMVVFSc96PDvV7wuj7W86n")

    def test_approvewitness(self):
        bts = self.bts
        w = Account("nectar", blockchain_instance=bts)
        tx = w.approvewitness("nectar1")
        self.assertEqual((tx["operations"][0][0]), "account_witness_vote")
        op = tx["operations"][0][1]
        self.assertIn("nectar1", op["witness"])

    def test_appendWif(self):
        _ = NodeList()
        hv = Hive(node=self.nodes, nobroadcast=True, expiration=120, num_retries=10)
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hv)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("1 STEEM", blockchain_instance=hv),
                    "memo": "",
                }
            )
        )
        with self.assertRaises(MissingKeyError):
            tx.sign()
        with self.assertRaises(InvalidWifError):
            tx.appendWif("abcdefg")
        tx.appendWif(self.active_key)
        tx.sign()
        self.assertTrue(len(tx["signatures"]) > 0)

    def test_appendSigner(self):
        _ = NodeList()
        hv = Hive(
            node=self.nodes,
            keys=[self.active_key],
            nobroadcast=True,
            expiration=120,
            num_retries=10,
        )
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hv)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("1 STEEM", blockchain_instance=hv),
                    "memo": "",
                }
            )
        )
        account = Account("nectar", blockchain_instance=hv)
        with self.assertRaises(AssertionError):
            tx.appendSigner(account, "abcdefg")
        tx.appendSigner(account, "active")
        self.assertTrue(len(tx.wifs) > 0)
        tx.sign()
        self.assertTrue(len(tx["signatures"]) > 0)

    def test_verifyAuthorityException(self):
        _ = NodeList()
        hv = Hive(
            node=self.nodes,
            keys=[self.posting_key],
            nobroadcast=True,
            expiration=120,
            num_retries=10,
        )
        tx = TransactionBuilder(use_condenser_api=True, blockchain_instance=hv)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("1 STEEM", blockchain_instance=hv),
                    "memo": "",
                }
            )
        )
        account = Account("nectar2", blockchain_instance=hv)
        tx.appendSigner(account, "active")
        tx.appendWif(self.posting_key)
        self.assertTrue(len(tx.wifs) > 0)
        tx.sign()
        with self.assertRaises(exceptions.MissingRequiredActiveAuthority):
            tx.verify_authority()
        self.assertTrue(len(tx["signatures"]) > 0)

    def test_Transfer_broadcast(self):
        _ = NodeList()
        hv = Hive(
            node=self.nodes,
            keys=[self.active_key],
            nobroadcast=True,
            expiration=120,
            num_retries=10,
        )

        tx = TransactionBuilder(use_condenser_api=True, expiration=10, blockchain_instance=hv)
        tx.appendOps(
            Transfer(
                **{
                    "from": "nectar",
                    "to": "nectar1",
                    "amount": Amount("1 STEEM", blockchain_instance=hv),
                    "memo": "",
                }
            )
        )
        tx.appendSigner("nectar", "active")
        tx.sign()
        tx.broadcast()

    def test_TransactionConstructor(self):
        hv = self.bts
        opTransfer = Transfer(
            **{
                "from": "nectar",
                "to": "nectar1",
                "amount": Amount("1 STEEM", blockchain_instance=hv),
                "memo": "",
            }
        )
        tx1 = TransactionBuilder(use_condenser_api=True, blockchain_instance=hv)
        tx1.appendOps(opTransfer)
        tx = TransactionBuilder(tx1, blockchain_instance=hv)
        self.assertFalse(tx.is_empty())
        self.assertTrue(len(tx.list_operations()) == 1)
        self.assertTrue(repr(tx) is not None)
        self.assertTrue(str(tx) is not None)
        account = Account("nectar", blockchain_instance=hv)
        tx.appendSigner(account, "active")
        self.assertTrue(len(tx.wifs) > 0)
        tx.sign()
        self.assertTrue(len(tx["signatures"]) > 0)

    def test_follow_active_key(self):
        _ = NodeList()
        hv = Hive(
            node=self.nodes,
            keys=[self.active_key],
            nobroadcast=True,
            expiration=120,
            num_retries=10,
        )
        account = Account("nectar", blockchain_instance=hv)
        account.follow("nectar1")

    def test_follow_posting_key(self):
        _ = NodeList()
        hv = Hive(
            node=self.nodes,
            keys=[self.posting_key],
            nobroadcast=True,
            expiration=120,
            num_retries=10,
        )
        account = Account("nectar", blockchain_instance=hv)
        account.follow("nectar1")
