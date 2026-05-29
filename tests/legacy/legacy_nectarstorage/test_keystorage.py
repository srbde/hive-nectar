import unittest

from nectargraphenebase.account import PrivateKey
from nectargraphenebase.bip38 import SaltException
from nectarstorage import (
    InRamConfigurationStore,
    InRamEncryptedKeyStore,
    InRamPlainKeyStore,
    SqliteEncryptedKeyStore,
    SqlitePlainKeyStore,
)
from nectarstorage.exceptions import KeyAlreadyInStoreException, WalletLocked


def pubprivpair(wif):
    return (str(wif), str(PrivateKey(wif).pubkey))


class Testcases(unittest.TestCase):
    def test_inramkeystore(self):
        self.do_keystore(InRamPlainKeyStore())

    def test_inramencryptedkeystore(self):
        self.do_keystore(InRamEncryptedKeyStore(config=InRamConfigurationStore()))

    def test_sqlitekeystore(self):
        s = SqlitePlainKeyStore(profile="testing")
        s.wipe()
        self.do_keystore(s)
        self.assertFalse(s.is_encrypted())

    def test_sqliteencryptedkeystore(self):
        self.do_keystore(
            SqliteEncryptedKeyStore(profile="testing", config=InRamConfigurationStore())
        )

    def do_keystore(self, keys):
        keys.wipe()
        password = "foobar"

        if isinstance(keys, (SqliteEncryptedKeyStore, InRamEncryptedKeyStore)):
            keys.config.wipe()
            with self.assertRaises(WalletLocked):
                keys.decrypt("6PRViepa2zaXXGEQTYUsoLM1KudLmNBB1t812jtdKx1TEhQtvxvmtEm6Yh")
            with self.assertRaises(WalletLocked):
                keys.encrypt("6PRViepa2zaXXGEQTYUsoLM1KudLmNBB1t812jtdKx1TEhQtvxvmtEm6Yh")
            with self.assertRaises(WalletLocked):
                keys._get_encrypted_masterpassword()

            # set the first MasterPassword here!
            keys._new_masterpassword(password)
            keys.lock()
            keys.unlock(password)
            assert keys.unlocked()
            assert keys.is_encrypted()

            with self.assertRaises(SaltException):
                keys.decrypt("6PRViepa2zaXXGEQTYUsoLM1KudLmNBB1t812jtdKx1TEhQtvxvmtEm6Yh")

        keys.add(*pubprivpair("5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"))
        # Duplicate key
        with self.assertRaises(KeyAlreadyInStoreException):
            keys.add(*pubprivpair("5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3"))
        self.assertIn(
            "STM6MRyAjQq8ud7hVNYcfnVPJqcVpscN5So8BhtHuGYqET5GDW5CV",
            keys.getPublicKeys(),
        )

        self.assertEqual(
            keys.getPrivateKeyForPublicKey("STM6MRyAjQq8ud7hVNYcfnVPJqcVpscN5So8BhtHuGYqET5GDW5CV"),
            "5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3",
        )
        self.assertEqual(keys.getPrivateKeyForPublicKey("GPH6MRy"), None)
        self.assertEqual(len(keys.getPublicKeys()), 1)
        keys.add(*pubprivpair("5Hqr1Rx6v3MLAvaYCxLYqaSEsm4eHaDFkLksPF2e1sDS7omneaZ"))
        self.assertEqual(len(keys.getPublicKeys()), 2)
        self.assertEqual(
            keys.getPrivateKeyForPublicKey("STM5u9tEsKaqtCpKibrXJAMhaRUVBspB5pr9X34PPdrSbvBb6ajZY"),
            "5Hqr1Rx6v3MLAvaYCxLYqaSEsm4eHaDFkLksPF2e1sDS7omneaZ",
        )
        keys.delete("STM5u9tEsKaqtCpKibrXJAMhaRUVBspB5pr9X34PPdrSbvBb6ajZY")
        self.assertEqual(len(keys.getPublicKeys()), 1)

        if isinstance(keys, (SqliteEncryptedKeyStore, InRamEncryptedKeyStore)):
            keys.lock()
            keys.wipe()
            keys.config.wipe()
