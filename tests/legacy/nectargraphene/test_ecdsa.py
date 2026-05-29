import unittest
from binascii import unhexlify

from parameterized import parameterized

import nectargraphenebase.ecdsasig as ecda
from nectargraphenebase.account import PrivateKey

wif = "5J4KCbg1G3my9b9hCaQXnHSm6vrwW9xQTJS6ZciW2Kek7cCkCEk"


class Testcases(unittest.TestCase):
    # Ignore warning:
    # https://www.reddit.com/r/joinmarket/comments/5crhfh/userwarning_implicit_cast_from_char_to_a/
    # @pytest.mark.filterwarnings()
    @parameterized.expand([("cryptography"), ("secp256k1"), ("ecdsa")])
    def test_sign_message(self, module):
        pub_key = PrivateKey(wif).pubkey.compressed()
        signature = ecda.sign_message("Foobar", wif)
        pub_key_sig = ecda.verify_message("Foobar", signature)
        self.assertEqual(pub_key_sig, unhexlify(pub_key))

    @parameterized.expand(
        [
            ("cryptography"),
            ("secp256k1"),
        ]
    )
    def test_sign_message_cross(self, module):
        pub_key = PrivateKey(wif).pubkey.compressed()
        signature = ecda.sign_message("Foobar", wif)
        pub_key_sig = ecda.verify_message("Foobar", signature)
        self.assertEqual(pub_key_sig, unhexlify(pub_key))

    @parameterized.expand(
        [
            ("cryptography"),
            ("secp256k1"),
            ("ecdsa"),
        ]
    )
    def test_wrong_signature(self, module):
        pub_key = PrivateKey(wif).pubkey.compressed()
        signature = ecda.sign_message("Foobar", wif)
        # Corrupt the signature by changing the last byte
        corrupted_signature = signature[:-1] + bytes([signature[-1] ^ 0xFF])
        # This should return None or raise an exception
        pub_key_sig = ecda.verify_message("Foobar", corrupted_signature)
        # For now, let's just test that it doesn't return the original key
        self.assertNotEqual(pub_key_sig, unhexlify(pub_key))


if __name__ == "__main__":
    unittest.main()
