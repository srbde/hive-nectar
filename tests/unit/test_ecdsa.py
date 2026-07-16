from binascii import unhexlify

import pytest

import nectargraphenebase.ecdsasig as ecda
from nectargraphenebase.account import PrivateKey

wif = "5J4KCbg1G3my9b9hCaQXnHSm6vrwW9xQTJS6ZciW2Kek7cCkCEk"


@pytest.mark.parametrize("module", ["cryptography", "secp256k1", "ecdsa"])
def test_sign_message(module):
    pub_key = PrivateKey(wif).pubkey.compressed()
    signature = ecda.sign_message("Foobar", wif)
    pub_key_sig = ecda.verify_message("Foobar", signature)
    assert pub_key_sig == unhexlify(pub_key)


@pytest.mark.parametrize("module", ["cryptography", "secp256k1"])
def test_sign_message_cross(module):
    pub_key = PrivateKey(wif).pubkey.compressed()
    signature = ecda.sign_message("Foobar", wif)
    pub_key_sig = ecda.verify_message("Foobar", signature)
    assert pub_key_sig == unhexlify(pub_key)


@pytest.mark.parametrize("module", ["cryptography", "secp256k1", "ecdsa"])
def test_wrong_signature(module):
    pub_key = PrivateKey(wif).pubkey.compressed()
    signature = ecda.sign_message("Foobar", wif)
    # Corrupt the signature by changing the last byte
    corrupted_signature = signature[:-1] + bytes([signature[-1] ^ 0xFF])
    pub_key_sig = ecda.verify_message("Foobar", corrupted_signature)
    assert pub_key_sig != unhexlify(pub_key)
