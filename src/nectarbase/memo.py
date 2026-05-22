import hashlib
import struct
from binascii import hexlify, unhexlify
from typing import Any, Tuple

import coincurve
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from nectargraphenebase.account import PublicKey
from nectargraphenebase.base58 import base58decode, base58encode
from nectargraphenebase.types import varintdecode

from .objects import Memo

default_prefix = "STM"


class CryptographyAESWrapper:
    def __init__(self, key: bytes, iv: bytes) -> None:
        self.key = key
        self.iv = iv

    def encrypt(self, data: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv))
        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()

    def decrypt(self, data: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv))
        decryptor = cipher.decryptor()
        return decryptor.update(data) + decryptor.finalize()


def get_shared_secret(priv: Any, pub: PublicKey) -> str:
    """Derive the share secret between ``priv`` and ``pub``
    :param `Base58` priv: Private Key
    :param `Base58` pub: Public Key
    :return: Shared secret
    :rtype: hex
    The shared secret is generated such that::
        Pub(Alice) * Priv(Bob) = Pub(Bob) * Priv(Alice)
    """
    priv_bytes = unhexlify(repr(priv))
    pub_bytes = bytes(pub)
    cc_pub = coincurve.PublicKey(pub_bytes)
    cc_shared_pub = cc_pub.multiply(priv_bytes)
    cc_uncompressed = cc_shared_pub.format(compressed=False)
    res_hex = cc_uncompressed[1:33].hex()
    return res_hex


def init_aes(shared_secret: str, nonce: int) -> Any:
    """Initialize AES instance
    :param hex shared_secret: Shared Secret to use as encryption key
    :param int nonce: Random nonce
    :return: AES instance
    :rtype: AES
    """
    " Shared Secret "
    ss = hashlib.sha512(unhexlify(shared_secret)).digest()
    " Seed "
    seed = bytes(str(nonce), "ascii") + hexlify(ss)
    seed_digest = hexlify(hashlib.sha512(seed).digest()).decode("ascii")
    " AES "
    key = unhexlify(seed_digest[0:64])
    iv = unhexlify(seed_digest[64:96])
    return CryptographyAESWrapper(key, iv)


def init_aes_bts(shared_secret: str, nonce: int) -> Any:
    """Initialize AES instance
    :param hex shared_secret: Shared Secret to use as encryption key
    :param int nonce: Random nonce
    :return: AES instance
    :rtype: AES
    """
    " Shared Secret "
    ss = hashlib.sha512(unhexlify(shared_secret)).digest()
    " Seed "
    seed = bytes(str(nonce), "ascii") + hexlify(ss)
    seed_digest = hexlify(hashlib.sha512(seed).digest()).decode("ascii")
    " AES "
    key = unhexlify(seed_digest[0:64])
    iv = unhexlify(seed_digest[64:96])
    return CryptographyAESWrapper(key, iv)


def init_aes2(shared_secret: str, nonce: int) -> Tuple[Any, int]:
    """Initialize AES instance
    :param hex shared_secret: Shared Secret to use as encryption key
    :param int nonce: Random nonce
    """
    shared_secret = hashlib.sha512(unhexlify(shared_secret)).hexdigest()
    # Seed
    ss = unhexlify(shared_secret)
    n = struct.pack("<Q", int(nonce))
    encryption_key = hashlib.sha512(n + ss).hexdigest()
    # Check'sum'
    check = hashlib.sha256(unhexlify(encryption_key)).digest()
    check = struct.unpack_from("<I", check[:4])[0]
    # AES
    key = unhexlify(encryption_key[0:64])
    iv = unhexlify(encryption_key[64:96])
    return CryptographyAESWrapper(key, iv), check


def _pad(s: bytes, BS: int) -> bytes:
    numBytes = BS - len(s) % BS
    return s + numBytes * struct.pack("B", numBytes)


def _unpad(s: bytes, BS: int) -> bytes:
    count = s[-1]
    if s[-count::] == count * struct.pack("B", count):
        return s[:-count]
    return s


def encode_memo_bts(priv: Any, pub: PublicKey, nonce: int, message: str) -> str:
    """Encode a message with a shared secret between Alice and Bob

    :param PrivateKey priv: Private Key (of Alice)
    :param PublicKey pub: Public Key (of Bob)
    :param int nonce: Random nonce
    :param str message: Memo message
    :return: Encrypted message
    :rtype: hex

    """
    shared_secret = get_shared_secret(priv, pub)
    aes = init_aes_bts(shared_secret, nonce)
    " Checksum "
    raw = bytes(message, "utf8")
    checksum = hashlib.sha256(raw).digest()
    raw = checksum[0:4] + raw
    " Padding "
    raw = _pad(raw, 16)
    " Encryption "
    return hexlify(aes.encrypt(raw)).decode("ascii")


def decode_memo_bts(priv: Any, pub: PublicKey, nonce: int, message: str) -> str:
    """Decode a message with a shared secret between Alice and Bob

    :param PrivateKey priv: Private Key (of Bob)
    :param PublicKey pub: Public Key (of Alice)
    :param int nonce: Nonce used for Encryption
    :param bytes message: Encrypted Memo message
    :return: Decrypted message
    :rtype: str
    :raise ValueError: if message cannot be decoded as valid UTF-8
           string

    """
    shared_secret = get_shared_secret(priv, pub)
    aes = init_aes_bts(shared_secret, nonce)
    " Encryption "
    raw = bytes(message, "ascii")
    cleartext = aes.decrypt(unhexlify(raw))
    " Checksum "
    checksum = cleartext[0:4]
    message_bytes = cleartext[4:]
    message_bytes = _unpad(message_bytes, 16)
    " Verify checksum "
    check = hashlib.sha256(
        message_bytes if isinstance(message_bytes, bytes) else message_bytes.encode("utf-8")
    ).digest()[0:4]
    if check != checksum:  # pragma: no cover
        raise ValueError("checksum verification failure")
    return message_bytes.decode("utf8") if isinstance(message_bytes, bytes) else message_bytes


def encode_memo(priv: Any, pub: PublicKey, nonce: int, message: str, **kwargs: Any) -> str:
    """Encode a message with a shared secret between Alice and Bob

    :param PrivateKey priv: Private Key (of Alice)
    :param PublicKey pub: Public Key (of Bob)
    :param int nonce: Random nonce
    :param str message: Memo message
    :return: Encrypted message
    :rtype: hex
    """
    shared_secret = get_shared_secret(priv, pub)
    aes, check = init_aes2(shared_secret, nonce)
    " Padding "
    raw = bytes(message, "utf8")
    raw = _pad(raw, 16)
    " Encryption "
    cipher = hexlify(aes.encrypt(raw)).decode("ascii")
    prefix = kwargs.pop("prefix", default_prefix)
    s = {
        "from": format(priv.pubkey, prefix),
        "to": format(pub, prefix),
        "nonce": nonce,
        "check": check,
        "encrypted": cipher,
        "prefix": prefix,
    }
    tx = Memo(**s)
    return "#" + base58encode(hexlify(bytes(tx)).decode("ascii"))


def extract_memo_data(message: str) -> Tuple[PublicKey, PublicKey, str, int, bytes]:
    """Returns the stored pubkey keys, nonce, checksum and encrypted message of a memo"""
    raw = base58decode(message[1:])
    from_key = PublicKey(raw[:66])
    raw = raw[66:]
    to_key = PublicKey(raw[:66])
    raw = raw[66:]
    nonce = str(struct.unpack_from("<Q", unhexlify(raw[:16]))[0])
    raw = raw[16:]
    check = struct.unpack_from("<I", unhexlify(raw[:8]))[0]
    raw = raw[8:]
    cipher = unhexlify(raw)
    return from_key, to_key, nonce, check, cipher


def decode_memo(priv: Any, message: str) -> str:
    """Decode a message with a shared secret between Alice and Bob

    :param PrivateKey priv: Private Key (of Bob)
    :param base58encoded message: Encrypted Memo message
    :return: Decrypted message
    :rtype: str
    :raise ValueError: if message cannot be decoded as valid UTF-8
           string
    """
    # decode structure
    from_key, to_key, nonce, check, cipher = extract_memo_data(message)

    if repr(to_key) == repr(priv.pubkey):
        shared_secret = get_shared_secret(priv, from_key)
    elif repr(from_key) == repr(priv.pubkey):
        shared_secret = get_shared_secret(priv, to_key)
    else:
        raise ValueError("Incorrect PrivateKey")

    # Init encryption
    aes, checksum = init_aes2(shared_secret, int(nonce))
    # Check
    if not check == checksum:
        raise AssertionError("Checksum failure")
    # Encryption
    # remove the varint prefix (FIXME, long messages!)
    numBytes = 16 - len(cipher) % 16
    n = 16 - numBytes
    message_bytes = cipher[n:]
    message_bytes = aes.decrypt(message_bytes)
    message_bytes = _unpad(message_bytes, 16)
    n = varintdecode(message_bytes)
    if (len(message_bytes) - n) > 0 and (len(message_bytes) - n) < 8:
        message_part = message_bytes[len(message_bytes) - n :]
        if isinstance(message_part, bytes):
            message_part = message_part.decode("utf8")
        return "#" + message_part
    else:
        return "#" + (
            message_bytes.decode("utf8") if isinstance(message_bytes, bytes) else message_bytes
        )
