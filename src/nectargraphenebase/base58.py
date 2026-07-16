import hashlib
import logging
import string
from binascii import hexlify, unhexlify
from typing import Any

from .prefix import Prefix

log = logging.getLogger(__name__)


class Base58(Prefix):
    """Base58 base class

    This class serves as an abstraction layer to deal with base58 encoded
    strings and their corresponding hex and binary representation throughout the
    library.

    :param data: Data to initialize object, e.g. pubkey data, address data, ...
    :type data: hex, wif, bip38 encrypted wif, base58 string
    :param str prefix: Prefix to use for Address/PubKey strings (defaults to ``GPH``)
    :return: Base58 object initialized with ``data``
    :rtype: Base58
    :raises ValueError: if data cannot be decoded

    * ``bytes(Base58)``: Returns the raw data
    * ``str(Base58)``:   Returns the readable ``Base58CheckEncoded`` data.
    * ``repr(Base58)``:  Gives the hex representation of the data.
    * ``format(Base58,_format)``: Formats the instance according to ``_format``

        * ``"btc"``: prefixed with ``0x80``. Yields a valid btc address
        * ``"wif"``: prefixed with ``0x00``. Yields a valid wif key
        * ``"bts"``: prefixed with ``BTS``
        * etc.

    """

    def __init__(self, data: Any, prefix: str | None = None) -> None:
        self.set_prefix(prefix)
        if isinstance(data, Base58):
            data = repr(data)
        if all(c in string.hexdigits for c in data):
            self._hex = data
        elif data[0] == "5" or data[0] == "6":
            self._hex = base58CheckDecode(data)
        elif data[0] == "K" or data[0] == "L":
            self._hex = base58CheckDecode(data)[:-2]
        elif data[: len(self.prefix)] == self.prefix:
            self._hex = gphBase58CheckDecode(data[len(self.prefix) :])
        else:
            raise ValueError("Error loading Base58 object")

    def __format__(self, _format: str) -> str:
        """Format output according to argument _format (wif,btc,...)

        :param str _format: Format to use
        :return: formatted data according to _format
        :rtype: str

        """
        if _format.upper() == "WIF":
            return base58CheckEncode(0x80, self._hex)
        elif _format.upper() == "ENCWIF":
            return base58encode(self._hex)
        elif _format.upper() == "BTC":
            return base58CheckEncode(0x00, self._hex)
        else:
            return _format.upper() + str(self)

    def __repr__(self) -> str:
        """Returns hex value of object

        :return: Hex string of instance's data
        :rtype: hex string
        """
        return self._hex

    def __str__(self) -> str:
        """Return graphene-base58CheckEncoded string of data

        :return: Base58 encoded data
        :rtype: str
        """
        return gphBase58CheckEncode(self._hex)

    def __bytes__(self) -> bytes:
        """Return raw bytes

        :return: Raw bytes of instance
        :rtype: bytes

        """
        return unhexlify(self._hex)


# https://github.com/tochev/python3-cryptocoins/raw/master/cryptocoins/base58.py
BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58decode(base58_str: str) -> str:
    base58_text = bytes(base58_str, "ascii")
    n = 0
    leading_zeroes_count = 0
    for b in base58_text:
        # b is always int in Python 3 when iterating bytes
        n = n * 58 + BASE58_ALPHABET.find(bytes([b]))
        if n == 0:
            leading_zeroes_count += 1
    res = bytearray()
    while n >= 256:
        div, mod = divmod(n, 256)
        res.insert(0, mod)
        n = div
    else:
        res.insert(0, n)
    return hexlify(bytearray(1) * leading_zeroes_count + res).decode("ascii")


def base58encode(hexstring: str) -> str:
    # Handle odd-length hex strings by padding with leading zero
    if len(hexstring) % 2 == 1:
        hexstring = "0" + hexstring
    byteseq = bytes(unhexlify(bytes(hexstring, "ascii")))
    n = 0
    leading_zeroes_count = 0
    for c in byteseq:
        n = n * 256 + c
        if n == 0:
            leading_zeroes_count += 1
    res = bytearray()
    while n >= 58:
        div, mod = divmod(n, 58)
        res.insert(0, BASE58_ALPHABET[mod])
        n = div
    else:
        res.insert(0, BASE58_ALPHABET[n])
    return (BASE58_ALPHABET[0:1] * leading_zeroes_count + res).decode("ascii")


def ripemd160(s: str | bytes) -> bytes:
    ripemd160 = hashlib.new("ripemd160")
    ripemd160.update(unhexlify(s))
    return ripemd160.digest()


def doublesha256(s: str | bytes) -> bytes:
    if isinstance(s, str):
        # Handle odd-length hex strings by padding with leading zero
        if len(s) % 2 == 1:
            s = "0" + s
        s = unhexlify(s)
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()


def b58encode(v: str) -> str:
    return base58encode(v)


def b58decode(v: str) -> str:
    return base58decode(v)


def base58CheckEncode(version: int, payload: str) -> str:
    if isinstance(version, str):
        s = version + payload
    else:
        s = ("%.2x" % version) + payload
    checksum = doublesha256(s)[:4]
    result = s + hexlify(checksum).decode("ascii")
    return base58encode(result)


def base58CheckDecode(s: str, skip_first_bytes: bool = True) -> str:
    s_bytes = unhexlify(base58decode(s))
    dec = hexlify(s_bytes[:-4]).decode("ascii")
    checksum = doublesha256(dec)[:4]
    if not (s_bytes[-4:] == checksum):
        raise AssertionError()
    if skip_first_bytes:
        return dec[2:]
    else:
        return dec


def gphBase58CheckEncode(s: str) -> str:
    checksum = ripemd160(s)[:4]
    result = s + hexlify(checksum).decode("ascii")
    return base58encode(result)


def gphBase58CheckDecode(s: str) -> str:
    s_bytes = unhexlify(base58decode(s))
    dec = hexlify(s_bytes[:-4]).decode("ascii")
    checksum = ripemd160(dec)[:4]
    if not (s_bytes[-4:] == checksum):
        raise AssertionError()
    return dec
