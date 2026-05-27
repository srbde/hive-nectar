import hashlib
import logging
from binascii import hexlify, unhexlify
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .account import PrivateKey
from .base58 import Base58, base58decode

log = logging.getLogger(__name__)


class SaltException(Exception):
    pass


def _aes_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


def _encrypt_xor(a: Any, b: bytes, key: bytes) -> bytes:
    """Returns encrypt(a ^ b)."""
    a_bytes = unhexlify("%0.32x" % (int(a, 16) ^ int(hexlify(b), 16)))
    return _aes_ecb_encrypt(key, a_bytes)


def encrypt(privkey: Any, passphrase: str) -> Base58:
    """BIP0038 non-ec-multiply encryption. Returns BIP0038 encrypted privkey.

    :param privkey: Private key
    :type privkey: Base58
    :param str passphrase: UTF-8 encoded passphrase for encryption
    :return: BIP0038 non-ec-multiply encrypted wif key
    :rtype: Base58

    """
    if isinstance(privkey, str):
        privkey = PrivateKey(privkey)
    else:
        privkey = PrivateKey(repr(privkey))

    privkeyhex = repr(privkey)  # hex
    addr = format(privkey.bitcoin.address, "BTC")
    a = bytes(addr, "ascii")
    salt = hashlib.sha256(hashlib.sha256(a).digest()).digest()[0:4]
    passphrase_bytes = passphrase.encode("utf-8") if isinstance(passphrase, str) else passphrase

    kdf = Scrypt(
        salt=salt,
        length=64,
        n=16384,
        r=8,
        p=8,
    )
    key = kdf.derive(passphrase_bytes)
    (derived_half1, derived_half2) = (key[:32], key[32:])

    encrypted_half1 = _encrypt_xor(privkeyhex[:32], derived_half1[:16], derived_half2)
    encrypted_half2 = _encrypt_xor(privkeyhex[32:], derived_half1[16:], derived_half2)
    # flag byte is forced 0xc0 because Graphene only uses compressed keys
    payload = b"\x01" + b"\x42" + b"\xc0" + salt + encrypted_half1 + encrypted_half2
    # Checksum
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    privatkey = hexlify(payload + checksum).decode("ascii")
    return Base58(privatkey)


def decrypt(encrypted_privkey: Any, passphrase: str) -> Base58:
    """BIP0038 non-ec-multiply decryption. Returns WIF privkey.

    :param Base58 encrypted_privkey: Private key
    :param str passphrase: UTF-8 encoded passphrase for decryption
    :return: BIP0038 non-ec-multiply decrypted key
    :rtype: Base58
    :raises SaltException: if checksum verification failed (e.g. wrong password)

    """

    d = unhexlify(base58decode(encrypted_privkey))
    d = d[2:]  # remove trailing 0x01 and 0x42
    flagbyte = d[0:1]  # get flag byte
    d = d[1:]  # get payload
    if not flagbyte == b"\xc0":
        raise AssertionError("Flagbyte has to be 0xc0")
    salt = d[0:4]
    d = d[4:-4]
    passphrase_bytes = passphrase.encode("utf-8") if isinstance(passphrase, str) else passphrase

    kdf = Scrypt(
        salt=salt,
        length=64,
        n=16384,
        r=8,
        p=8,
    )
    key = kdf.derive(passphrase_bytes)
    derivedhalf1 = key[0:32]
    derivedhalf2 = key[32:64]
    encryptedhalf1 = d[0:16]
    encryptedhalf2 = d[16:32]

    decryptedhalf2 = _aes_ecb_decrypt(derivedhalf2, encryptedhalf2)
    decryptedhalf1 = _aes_ecb_decrypt(derivedhalf2, encryptedhalf1)
    privraw = decryptedhalf1 + decryptedhalf2
    privraw = "%064x" % (int(hexlify(privraw), 16) ^ int(hexlify(derivedhalf1), 16))
    wif = Base58(privraw)
    # Verify Salt
    privkey = PrivateKey(format(wif, "wif"))
    addr = format(privkey.bitcoin.address, "BTC")
    a = bytes(addr, "ascii")
    saltverify = hashlib.sha256(hashlib.sha256(a).digest()).digest()[0:4]
    if saltverify != salt:
        raise SaltException("checksum verification failed! Password may be incorrect.")
    return wif
