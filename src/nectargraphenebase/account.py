import binascii
import bisect
import hashlib
import itertools
import os
import re
import unicodedata
from binascii import hexlify, unhexlify
from typing import Any, Union

import coincurve

from .base58 import Base58, doublesha256, ripemd160
from .bip32 import BIP32Key, parse_path
from .dictionary import words as BrainKeyDictionary
from .dictionary import words_bip39 as MnemonicDictionary
from .prefix import Prefix

PBKDF2_ROUNDS = 2048


# secp256k1 curve parameters for pure Python implementation
SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP256K1_A = 0
SECP256K1_B = 7
SECP256K1_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP256K1_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _mod_inverse(a: int, m: int) -> int:
    """
    Return the modular inverse of a modulo m using the extended Euclidean algorithm.

    Given integers a and m, compute x such that (a * x) % m == 1. The result is normalized
    to the range [0, m-1]. If m == 1 the function returns 0.

    Parameters:
        a (int): The value to invert modulo m.
        m (int): The modulus.

    Returns:
        int: The modular inverse of a modulo m, or 0 when m == 1.
    """
    m0, y, x = m, 0, 1
    if m == 1:
        return 0
    while a > 1:
        q = a // m
        m, a = a % m, m
        y, x = x - q * y, y
    if x < 0:
        x += m0
    return x


def _is_on_curve(
    x: int, y: int, p: int = SECP256K1_P, a: int = SECP256K1_A, b: int = SECP256K1_B
) -> bool:
    """Check if point (x, y) is on the secp256k1 curve: y² = x³ + a*x + b"""
    left_side = (y * y) % p
    right_side = (x * x * x + a * x + b) % p
    return left_side == right_side


def _point_add(
    p1: tuple[int, int] | None, p2: tuple[int, int] | None, p: int = SECP256K1_P
) -> tuple[int, int] | None:
    """
    Add two points on an elliptic curve over a prime field.

    Both p1 and p2 are either None (the point at infinity) or 2-tuples (x, y) of integers
    interpreted modulo p. Returns a 2-tuple (x, y) representing the sum (mod p), or None
    for the point at infinity. Uses the short Weierstrass group law (handles point
    doubling and addition, including the inverse/vertical-tangent cases).

    Parameters:
        p1 (tuple|None): First point as (x, y) or None for infinity.
        p2 (tuple|None): Second point as (x, y) or None for infinity.
        p (int): Prime modulus of the field (defaults to SECP256K1_P).

    Returns:
        tuple|None: Resulting point (x, y) modulo p, or None if the result is the
        point at infinity.
    """
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    # P + (-P) = O
    if x1 == x2 and (y1 + y2) % p == 0:
        return None  # Point at infinity

    if x1 == x2:
        # Point doubling - for secp256k1: s = (3*x1^2) / (2*y1)
        if y1 % p == 0:
            return None  # vertical tangent => infinity
        numerator = (3 * x1 * x1) % p
        denominator = (2 * y1) % p
        s = (numerator * _mod_inverse(denominator, p)) % p
    else:
        # Point addition
        denom = (x2 - x1) % p
        s = ((y2 - y1) % p) * _mod_inverse(denom, p) % p

    x3 = (s * s - x1 - x2) % p
    y3 = (s * (x1 - x3) - y1) % p

    return (x3, y3)


def _scalar_mult(
    k: int, point: tuple[int, int] | None, p: int = SECP256K1_P
) -> tuple[int, int] | None:
    """
    Compute k * point on the secp256k1 curve using the binary (double-and-add) method.

    Parameters:
        k (int): Non-negative integer scalar.
        point (tuple|None): Elliptic-curve point as (x, y) or None to represent the point at infinity.
        p (int, optional): Prime modulus of the field (defaults to SECP256K1_P).

    Returns:
        tuple|None: The resulting point (x, y) after scalar multiplication, or None for the point at infinity.
    """
    if k == 0:
        return None  # Point at infinity
    if k == 1:
        return point

    result = None
    current = point

    while k > 0:
        if k & 1:
            result = _point_add(result, current, p)
        current = _point_add(current, current, p)
        k >>= 1

    return result


def _point_to_compressed(point: tuple[int, int]) -> bytes:
    """
    Return the 33-byte SEC compressed encoding of an EC point on secp256k1.

    The input `point` must be a tuple (x, y) of integers representing coordinates on the curve.
    The result is a 33-byte bytes object: a 1-byte prefix 0x02 (even y) or 0x03 (odd y)
    followed by the 32-byte big-endian x coordinate.

    Raises:
        ValueError: If `point` is None (the point at infinity cannot be compressed).
    """
    if point is None:
        raise ValueError("Cannot compress point at infinity")

    x, y = point
    prefix = 0x02 if y % 2 == 0 else 0x03
    return prefix.to_bytes(1, "big") + x.to_bytes(32, "big")


def _compressed_to_point(compressed: bytes) -> tuple[int, int]:
    """
    Convert a 33-byte SEC compressed public key to an (x, y) point on the secp256k1 curve.

    Parameters:
        compressed (bytes): 33-byte compressed point (prefix 0x02 or 0x03 followed by 32-byte big-endian x).

    Returns:
        tuple[int, int]: The affine coordinates (x, y) of the corresponding point.

    Raises:
        ValueError: If the input length is not 33 bytes, the prefix is not 0x02/0x03, or the recovered point is not on the secp256k1 curve.
    """
    if len(compressed) != 33:
        raise ValueError("Invalid compressed point length")

    prefix = compressed[0]
    x = int.from_bytes(compressed[1:], "big")

    if prefix not in (0x02, 0x03):
        raise ValueError("Invalid compressed point prefix")

    # Calculate y from x using curve equation: y^2 = x^3 + a*x + b
    y_squared = (x * x * x + SECP256K1_A * x + SECP256K1_B) % SECP256K1_P

    # Find square root mod p
    y = pow(y_squared, (SECP256K1_P + 1) // 4, SECP256K1_P)

    # Choose the correct y based on parity
    if (prefix == 0x02 and y % 2 != 0) or (prefix == 0x03 and y % 2 == 0):
        y = SECP256K1_P - y

    if not _is_on_curve(x, y):
        raise ValueError("Point not on curve")

    return (x, y)


# From <https://stackoverflow.com/questions/212358/binary-search-bisection-in-python/2233940#2233940>
def binary_search(a: list[Any], x: Any, lo: int = 0, hi: int | None = None) -> int:
    """
    Locate the index of x in sorted sequence a using binary search.

    Performs a binary search on the sorted sequence `a` and returns the lowest index i in [lo, hi)
    such that a[i] == x. If x is not present in that slice, returns -1.

    Parameters:
        a (Sequence): Sorted sequence (ascending) to search.
        x: Value to locate.
        lo (int, optional): Lower bound (inclusive) index to search from. Defaults to 0.
        hi (int, optional): Upper bound (exclusive) index to search to. Defaults to len(a).

    Returns:
        int: Index of the first matching element in [lo, hi), or -1 if not found.
    """
    hi = hi if hi is not None else len(a)  # hi defaults to len(a)
    pos = bisect.bisect_left(a, x, lo, hi)  # find insertion position
    return pos if pos != hi and a[pos] == x else -1  # don't walk off the end


class PasswordKey(Prefix):
    """This class derives a private key given the account name, the
    role and a password. It leverages the technology of Brainkeys
    and allows people to have a secure private key by providing a
    passphrase only.
    """

    def __init__(
        self,
        account: str | None,
        password: str,
        role: str = "active",
        prefix: str | None = None,
    ) -> None:
        self.set_prefix(prefix)
        self.account = account
        self.role = role
        self.password = password

    def normalize(self, seed: str) -> str:
        """Correct formatting with single whitespace syntax and no trailing space"""
        return " ".join(re.compile("[\t\n\v\f\r ]+").split(seed))

    def get_private(self) -> "PrivateKey":
        """Derive private key from the account, the role and the password"""
        if self.account is None and self.role is None:
            seed = self.password
        elif self.account == "" and self.role == "":
            seed = self.password
        else:
            seed = self.normalize(f"{self.account or ''}{self.role or ''}{self.password}")
        return PrivateKey(
            hexlify(hashlib.sha256(seed.encode()).digest()).decode("ascii"), prefix=self.prefix
        )

    def get_public(self) -> "PublicKey":
        return self.get_private().pubkey

    def get_private_key(self) -> "PrivateKey":
        return self.get_private()

    def get_public_key(self) -> "PublicKey":
        return self.get_public()


class BrainKey(Prefix):
    """Brainkey implementation similar to the graphene-ui web-wallet.

    :param str brainkey: Brain Key
    :param int sequence: Sequence number for consecutive keys

    Keys in Graphene are derived from a seed brain key which is a string of
    16 words out of a predefined dictionary with 49744 words. It is a
    simple single-chain key derivation scheme that is not compatible with
    BIP44 but easy to use.

    Given the brain key, a private key is derived as::

        privkey = SHA256(SHA512(brainkey + " " + sequence))

    Incrementing the sequence number yields a new key that can be
    regenerated given the brain key.

    """

    def __init__(
        self, brainkey: str | None = None, sequence: int = 0, prefix: str | None = None
    ) -> None:
        self.set_prefix(prefix)
        if not brainkey:
            self.brainkey = self.suggest()
        else:
            self.brainkey = self.normalize(brainkey).strip()
        self.sequence = sequence

    def __next__(self) -> "BrainKey":
        """Get the next private key (sequence number increment) for
        iterators
        """
        return self.next_sequence()

    def next_sequence(self) -> "BrainKey":
        """Increment the sequence number by 1"""
        self.sequence += 1
        return self

    def normalize(self, brainkey: str) -> str:
        """Correct formatting with single whitespace syntax and no trailing space"""
        return " ".join(re.compile("[\t\n\v\f\r ]+").split(brainkey))

    def get_brainkey(self) -> str:
        """Return brain key of this instance"""
        return self.normalize(self.brainkey)

    def get_private(self) -> "PrivateKey":
        """Derive private key from the brain key and the current sequence
        number
        """
        encoded = "%s %d" % (self.brainkey, self.sequence)
        a = bytes(encoded, "ascii")
        s = hashlib.sha256(hashlib.sha512(a).digest()).digest()
        return PrivateKey(hexlify(s).decode("ascii"), prefix=self.prefix)

    def get_blind_private(self) -> "PrivateKey":
        """Derive private key from the brain key (and no sequence number)"""
        a = bytes(self.brainkey, "ascii")
        return PrivateKey(hashlib.sha256(a).hexdigest(), prefix=self.prefix)

    def get_public(self) -> "PublicKey":
        return self.get_private().pubkey

    def get_private_key(self) -> "PrivateKey":
        return self.get_private()

    def get_public_key(self) -> "PublicKey":
        return self.get_public()

    def suggest(self, word_count: int = 16) -> str:
        """Suggest a new random brain key. Randomness is provided by the
        operating system using ``os.urandom()``.
        """
        brainkey: list[str] = [""] * word_count
        dict_lines = BrainKeyDictionary.split(",")
        if not len(dict_lines) == 49744:
            raise AssertionError()
        for j in range(0, word_count):
            urand = os.urandom(2)
            num = int.from_bytes(urand, byteorder="little")
            rndMult = num / 2**16  # returns float between 0..1 (inclusive)
            wIdx = int(round(len(dict_lines) * rndMult))
            brainkey[j] = dict_lines[wIdx]
        return " ".join(brainkey).upper()


# From https://github.com/trezor/python-mnemonic/blob/master/mnemonic/mnemonic.py
#
# Copyright (c) 2013 Pavol Rusnak
# Copyright (c) 2017 mruddy
class Mnemonic:
    """BIP39 mnemoric implementation"""

    def __init__(self) -> None:
        self.wordlist = MnemonicDictionary.split(",")
        self.radix = 2048

    def generate(self, strength: int = 128) -> str:
        """Generates a word list based on the given strength

        :param int strength: initial entropy strength, must be one of [128, 160, 192, 224, 256]

        """
        if strength not in [128, 160, 192, 224, 256]:
            raise ValueError(
                "Strength should be one of the following: [128, 160, 192, 224, 256], but it is not (%d)."
                % strength
            )
        return self.to_mnemonic(os.urandom(strength // 8))

    # Adapted from <http://tinyurl.com/oxmn476>
    def to_entropy(self, words: str | list[str]) -> bytes:
        if not isinstance(words, list):
            words = words.split(" ")
        if len(words) not in [12, 15, 18, 21, 24]:
            raise ValueError(
                "Number of words must be one of the following: [12, 15, 18, 21, 24], but it is not (%d)."
                % len(words)
            )
        # Look up all the words in the list and construct the
        # concatenation of the original entropy and the checksum.
        concatLenBits = len(words) * 11
        concatBits = [False] * concatLenBits
        wordindex = 0
        use_binary_search = True
        for word in words:
            # Find the words index in the wordlist
            ndx = (
                binary_search(self.wordlist, word)
                if use_binary_search
                else self.wordlist.index(word)
            )
            if ndx < 0:
                raise LookupError('Unable to find "%s" in word list.' % word)
            # Set the next 11 bits to the value of the index.
            for ii in range(11):
                concatBits[(wordindex * 11) + ii] = (ndx & (1 << (10 - ii))) != 0
            wordindex += 1
        checksumLengthBits = concatLenBits // 33
        entropyLengthBits = concatLenBits - checksumLengthBits
        # Extract original entropy as bytes.
        entropy = bytearray(entropyLengthBits // 8)
        for ii in range(len(entropy)):
            for jj in range(8):
                if concatBits[(ii * 8) + jj]:
                    entropy[ii] |= 1 << (7 - jj)
        # Take the digest of the entropy.
        hashBytes = hashlib.sha256(entropy).digest()
        hashBits = list(
            itertools.chain.from_iterable(
                [c & (1 << (7 - i)) != 0 for i in range(8)] for c in hashBytes
            )
        )
        # Check all the checksum bits.
        for i in range(checksumLengthBits):
            if concatBits[entropyLengthBits + i] != hashBits[i]:
                raise ValueError("Failed checksum.")
        return bytes(entropy)

    def to_mnemonic(self, data: bytes) -> str:
        if len(data) not in [16, 20, 24, 28, 32]:
            raise ValueError(
                "Data length should be one of the following: [16, 20, 24, 28, 32], but it is not (%d)."
                % len(data)
            )
        h = hashlib.sha256(data).hexdigest()
        b = (
            bin(int(binascii.hexlify(data), 16))[2:].zfill(len(data) * 8)
            + bin(int(h, 16))[2:].zfill(256)[: len(data) * 8 // 32]
        )
        result = []
        for i in range(len(b) // 11):
            idx = int(b[i * 11 : (i + 1) * 11], 2)
            result.append(self.wordlist[idx])

        result_phrase = " ".join(result)
        return result_phrase

    def check(self, mnemonic: str | list[str]) -> bool:
        """Checks the mnemonic word list is valid
        :param list mnemonic: mnemonic word list with length of 12, 15, 18, 21, 24
        :returns: True, when valid
        """
        mnemonic_str = " ".join(mnemonic) if isinstance(mnemonic, list) else mnemonic
        mnemonic = self.normalize_string(mnemonic_str).split(" ")
        # list of valid mnemonic lengths
        if len(mnemonic) not in [12, 15, 18, 21, 24]:
            return False
        try:
            idx = map(lambda x: bin(self.wordlist.index(x))[2:].zfill(11), mnemonic)
            b = "".join(idx)
        except ValueError:
            return False
        l = len(b)  # noqa: E741
        d = b[: l // 33 * 32]
        h = b[-l // 33 :]
        nd = binascii.unhexlify(hex(int(d, 2))[2:].rstrip("L").zfill(l // 33 * 8))
        nh = bin(int(hashlib.sha256(nd).hexdigest(), 16))[2:].zfill(256)[: l // 33]
        return h == nh

    def check_word(self, word: str) -> bool:
        return word in self.wordlist

    def expand_word(self, prefix: str) -> str:
        """Expands a word when sufficient chars are given

        :param str prefix: first chars of a valid dict word

        """
        if prefix in self.wordlist:
            return prefix
        else:
            matches = [word for word in self.wordlist if word.startswith(prefix)]
            if len(matches) == 1:  # matched exactly one word in the wordlist
                return matches[0]
            else:
                # exact match not found.
                # this is not a validation routine, just return the input
                return prefix

    def expand(self, mnemonic: str) -> str:
        """Expands all words given in a list"""
        return " ".join(map(self.expand_word, mnemonic.split(" ")))

    @classmethod
    def normalize_string(cls, txt: str) -> str:
        """Normalizes strings"""
        return unicodedata.normalize("NFKD", txt)

    @classmethod
    def to_seed(cls, mnemonic: str | list[str], passphrase: str = "") -> bytes:
        """Returns a seed based on bip39

        :param str mnemonic: string containing a valid mnemonic word list
        :param str passphrase: optional, passphrase can be set to modify the returned seed.

        """
        if isinstance(mnemonic, list):
            mnemonic = " ".join(mnemonic)
        norm_mnemonic = cls.normalize_string(mnemonic)
        norm_passphrase = cls.normalize_string(passphrase)
        salt = "mnemonic" + norm_passphrase
        stretched = hashlib.pbkdf2_hmac(
            "sha512",
            norm_mnemonic.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ROUNDS,
        )
        return stretched[:64]


class MnemonicKey(Prefix):
    """This class derives a private key from a BIP39 mnemoric implementation"""

    def __init__(
        self,
        word_list: str | list[str] | None = None,
        passphrase: str = "",
        account_sequence: int = 0,
        key_sequence: int = 0,
        prefix: str | None = None,
    ) -> None:
        self.set_prefix(prefix)
        if word_list is not None:
            self.set_mnemonic(word_list, passphrase=passphrase)
        else:
            self.seed = None
        self.account_sequence = account_sequence
        self.key_sequence = key_sequence
        self.prefix = prefix or ""
        self.path = "m/48'/13'/0'/%d'/%d'" % (self.account_sequence, self.key_sequence)

    def set_mnemonic(self, word_list: str | list[str], passphrase: str = "") -> None:
        mnemonic = Mnemonic()
        if not mnemonic.check(word_list):
            raise ValueError("Word list is not valid!")
        self.seed = mnemonic.to_seed(word_list, passphrase=passphrase)

    def generate_mnemonic(self, passphrase: str = "", strength: int = 256) -> str:
        mnemonic = Mnemonic()
        word_list = mnemonic.generate(strength=strength)
        self.seed = mnemonic.to_seed(word_list, passphrase=passphrase)
        return word_list

    def set_path_BIP32(self, path: str) -> None:
        self.path = path

    def set_path_BIP44(
        self,
        account_sequence: int = 0,
        chain_sequence: int = 0,
        key_sequence: int = 0,
        hardened_address: bool = True,
    ) -> None:
        if account_sequence < 0:
            raise ValueError("account_sequence must be >= 0")
        if key_sequence < 0:
            raise ValueError("key_sequence must be >= 0")
        if chain_sequence < 0:
            raise ValueError("chain_sequence must be >= 0")
        self.account_sequence = account_sequence
        self.key_sequence = key_sequence
        if hardened_address:
            self.path = "m/44'/0'/%d'/%d/%d'" % (
                self.account_sequence,
                chain_sequence,
                self.key_sequence,
            )
        else:
            self.path = "m/44'/0'/%d'/%d/%d" % (
                self.account_sequence,
                chain_sequence,
                self.key_sequence,
            )

    def set_path_BIP48(
        self,
        network_index: int = 13,
        role: str | int = "owner",
        account_sequence: int = 0,
        key_sequence: int = 0,
    ) -> None:
        if account_sequence < 0:
            raise ValueError("account_sequence must be >= 0")
        if key_sequence < 0:
            raise ValueError("key_sequence must be >= 0")
        if network_index < 0:
            raise ValueError("network_index must be >= 0")
        if isinstance(role, str) and role not in ["owner", "active", "posting", "memo"]:
            raise ValueError("Wrong role!")
        elif isinstance(role, int) and role < 0:
            raise ValueError("role must be >= 0")
        if role == "owner":
            role = 0
        elif role == "active":
            role = 1
        elif role == "posting":
            role = 4
        elif role == "memo":
            role = 3

        self.account_sequence = account_sequence
        self.key_sequence = key_sequence
        self.path = "m/48'/%d'/%d'/%d'/%d'" % (
            network_index,
            role,
            self.account_sequence,
            self.key_sequence,
        )

    def next_account_sequence(self) -> "MnemonicKey":
        """Increment the account sequence number by 1"""
        self.account_sequence += 1
        return self

    def next_sequence(self) -> "MnemonicKey":
        """Increment the key sequence number by 1"""
        self.key_sequence += 1
        return self

    def set_path(self, path: str) -> None:
        self.path = path

    def get_path(self) -> str:
        return self.path

    def get_private(self) -> "PrivateKey":
        """Derive private key from the account_sequence, the role and the key_sequence"""
        if self.seed is None:
            raise ValueError("seed is None, set or generate a mnemonic first")
        key = BIP32Key.fromEntropy(self.seed)
        path_result = parse_path(self.get_path(), as_bytes=False)
        for n in path_result:
            key = key.ChildKey(n)
            if key is None:
                raise ValueError(f"Failed to derive child key for path index: {n}")

        return PrivateKey(key.WalletImportFormat(), prefix=self.prefix)

    def get_public(self) -> "PublicKey":
        return self.get_private().pubkey

    def get_private_key(self) -> "PrivateKey":
        return self.get_private()

    def get_public_key(self) -> "PublicKey":
        return self.get_public()


class Address(Prefix):
    """Address class

    This class serves as an address representation for Public Keys.

    :param str address: Base58 encoded address (defaults to ``None``)
    :param str prefix: Network prefix (defaults to ``STM``)

    Example::

       Address("STMFN9r6VYzBK8EKtMewfNbfiGCr56pHDBFi")

    """

    def __init__(self, address: str, prefix: str | None = None) -> None:
        self.set_prefix(prefix)
        self._address = Base58(address, prefix=self.prefix)

    @classmethod
    def from_pubkey(
        cls,
        pubkey: Union[str, "PublicKey"],
        compressed: bool = True,
        version: int = 56,
        prefix: str | None = None,
    ) -> "Address":
        """Load an address provided by the public key.
        Version: 56 => PTS
        """
        # Ensure this is a public key
        pubkey = PublicKey(pubkey, prefix=prefix or Prefix.prefix)
        if compressed:
            pubkey_plain = pubkey.compressed()
        else:
            pubkey_plain = pubkey.uncompressed()
        sha = hashlib.sha256(unhexlify(pubkey_plain)).hexdigest()
        rep = hexlify(ripemd160(sha)).decode("ascii")
        s = ("%.2x" % version) + rep
        result = s + hexlify(doublesha256(s)[:4]).decode("ascii")
        result = hexlify(ripemd160(result)).decode("ascii")
        return cls(result, prefix=pubkey.prefix)

    @classmethod
    def derivesha256address(
        cls, pubkey: Union[str, "PublicKey"], compressed: bool = True, prefix: str | None = None
    ) -> "Address":
        """Derive address using ``RIPEMD160(SHA256(x))``"""
        pubkey = PublicKey(pubkey, prefix=prefix or Prefix.prefix)
        if compressed:
            pubkey_plain = pubkey.compressed()
        else:
            pubkey_plain = pubkey.uncompressed()
        pkbin = unhexlify(repr(pubkey_plain))
        result = hexlify(hashlib.sha256(pkbin).digest())
        result = hexlify(ripemd160(result)).decode("ascii")
        return cls(result, prefix=pubkey.prefix)

    @classmethod
    def derivesha512address(
        cls, pubkey: Union[str, "PublicKey"], compressed: bool = True, prefix: str | None = None
    ) -> "Address":
        """Derive address using ``RIPEMD160(SHA512(x))``"""
        pubkey = PublicKey(pubkey, prefix=prefix or Prefix.prefix)
        if compressed:
            pubkey_plain = pubkey.compressed()
        else:
            pubkey_plain = pubkey.uncompressed()
        pkbin = unhexlify(repr(pubkey_plain))
        result = hexlify(hashlib.sha512(pkbin).digest())
        result = hexlify(ripemd160(result)).decode("ascii")
        return cls(result, prefix=pubkey.prefix)

    def __repr__(self) -> str:
        """Gives the hex representation of the ``GrapheneBase58CheckEncoded``
        Graphene address.
        """
        return repr(self._address)

    def __str__(self) -> str:
        """Returns the readable Graphene address. This call is equivalent to
        ``format(Address, "STM")``
        """
        return format(self._address, self.prefix)

    def __format__(self, _format: str) -> str:
        """May be issued to get valid "MUSE", "PLAY" or any other Graphene compatible
        address with corresponding prefix.
        """
        return format(self._address, _format)

    def __bytes__(self) -> bytes:
        """Returns the raw content of the ``Base58CheckEncoded`` address"""
        return bytes(self._address)


class GrapheneAddress(Address):
    """Graphene Addresses are different. Hence we have a different class"""

    @classmethod
    def from_pubkey(
        cls,
        pubkey: Union[str, "PublicKey"],
        compressed: bool = True,
        version: int = 56,
        prefix: str | None = None,
    ) -> "GrapheneAddress":
        # Ensure this is a public key
        pubkey = PublicKey(pubkey, prefix=prefix or Prefix.prefix)
        if compressed:
            pubkey_plain = pubkey.compressed()
        else:
            pubkey_plain = pubkey.uncompressed()

        """ Derive address using ``RIPEMD160(SHA512(x))`` """
        addressbin = ripemd160(hashlib.sha512(unhexlify(pubkey_plain)).hexdigest())
        result = Base58(hexlify(addressbin).decode("ascii"))
        return cls(repr(result), prefix=pubkey.prefix)


class PublicKey(Prefix):
    """This class deals with Public Keys and inherits ``Address``.

    :param str pk: Base58 encoded public key
    :param str prefix: Network prefix (defaults to ``STM``)

    Example::

       PublicKey("STM6UtYWWs3rkZGV8JA86qrgkG6tyFksgECefKE1MiH4HkLD8PFGL")

    .. note:: By default, graphene-based networks deal with **compressed**
              public keys. If an **uncompressed** key is required, the
              method :func:`unCompressed` can be used::

                  PublicKey("xxxxx").unCompressed()

    """

    def __init__(self, pk: Union[str, "PublicKey"], prefix: str | None = None) -> None:
        """Init PublicKey
        :param str pk: Base58 encoded public key
        :param str prefix: Network prefix (defaults to ``STM``)
        """
        self.set_prefix(prefix)
        if isinstance(pk, PublicKey):
            pk = format(pk, self.prefix)

        if str(pk).startswith("04"):
            # We only ever deal with compressed keys, so let's make it
            # compressed
            import coincurve

            pk_bytes = coincurve.PublicKey(unhexlify(pk)).format(compressed=True)
            pk = hexlify(pk_bytes).decode("ascii")

        self._pk = Base58(pk, prefix=self.prefix)

    @property
    def pubkey(self) -> str:
        return repr(self._pk)

    def get_public_key(self) -> str:
        """Returns the pubkey"""
        return self.pubkey

    @property
    def compressed_key(self) -> "PublicKey":
        return PublicKey(self.compressed())

    def __str__(self) -> str:
        """Return the string representation of the public key"""
        return self.prefix + str(self._pk)

    def __repr__(self) -> str:
        """Return the string representation of the public key"""
        return str(self)

    def __format__(self, _format: str) -> str:
        """Format the public key with the given prefix"""
        return _format + str(self._pk)

    def __bytes__(self) -> bytes:
        """Return the bytes representation of the public key"""
        return bytes(self._pk)

    def _derive_y_from_x(self, x: int, is_even: bool) -> int:
        """Derive y point from x point"""
        # The curve equation over F_p is:
        #   y^2 = x^3 + ax + b
        # For secp256k1, a=0, b=7
        alpha = (pow(x, 3, SECP256K1_P) + SECP256K1_B) % SECP256K1_P
        beta = pow(alpha, (SECP256K1_P + 1) // 4, SECP256K1_P)
        if (beta % 2) == is_even:
            beta = SECP256K1_P - beta
        return beta

    def compressed(self) -> str:
        """Derive compressed public key"""
        return repr(self._pk)

    def uncompressed(self) -> str:
        """Derive uncompressed key"""
        public_key = repr(self._pk)
        prefix = public_key[0:2]
        if prefix == "04":
            return public_key
        if not (prefix == "02" or prefix == "03"):
            raise AssertionError()
        x = int(public_key[2:], 16)
        y = self._derive_y_from_x(x, (prefix == "02"))
        key = "04" + "%064x" % x + "%064x" % y
        return key

    def child(self, offset256: bytes) -> "PublicKey":
        """Derive new public key from this key and a sha256 "offset" """
        a = bytes(self) + offset256
        s = hashlib.sha256(a).digest()
        return self.add(s)

    def add(self, digest256: bytes) -> "PublicKey":
        """
        Return a new PublicKey obtained by adding a 32-byte tweak (interpreted as a big-endian scalar) times the curve generator to this public key.

        Parameters:
            digest256 (bytes): A 32-byte SHA-256 digest used as the tweak scalar (big-endian). Must be length 32, non-zero, and less than the curve order.

        Returns:
            PublicKey: A new PublicKey instance representing (tweak * G) + current_public_key, preserving this key's prefix.

        Raises:
            ValueError: If `digest256` is not bytes, not 32 bytes long, is zero, is >= curve order, or if intermediate point multiplication/addition results in the point at infinity.
        """
        # Validate tweak
        if not isinstance(digest256, (bytes, bytearray)):
            raise ValueError("Tweak must be bytes")
        if len(digest256) != 32:
            raise ValueError("Tweak must be exactly 32 bytes")

        tweak = int.from_bytes(digest256, "big")
        if tweak == 0:
            raise ValueError("Tweak cannot be zero")
        if tweak >= SECP256K1_N:
            raise ValueError("Tweak must be less than curve order")

        # Convert current public key to point
        current_compressed = bytes(self)
        current_point = _compressed_to_point(current_compressed)

        # Compute G*tweak (scalar multiplication of generator)
        generator_point = (SECP256K1_GX, SECP256K1_GY)
        tweak_point = _scalar_mult(tweak, generator_point)

        if tweak_point is None:
            raise ValueError("Tweak multiplication resulted in point at infinity")

        # Add points: result = tweak_point + current_point
        result_point = _point_add(tweak_point, current_point)

        if result_point is None:
            raise ValueError("Point addition resulted in point at infinity")

        # Convert back to compressed format
        result_compressed = _point_to_compressed(result_point)

        # Create new PublicKey with same prefix
        return PublicKey(hexlify(result_compressed).decode("ascii"), prefix=self.prefix)

    @classmethod
    def from_privkey(
        cls, privkey: Union[str, "PrivateKey"], prefix: str | None = None
    ) -> "PublicKey":
        """
        Derive a compressed public key from a private key and return a PublicKey instance.

        Parameters:
            privkey: The private key material to derive from — accepts a WIF/hex string or a PrivateKey instance.
            prefix (optional): Network/key prefix to use for the resulting PublicKey; if omitted the module default prefix is used.

        Returns:
            PublicKey: A PublicKey (compressed form) constructed from the derived public key bytes.
        """
        privkey = PrivateKey(privkey, prefix=prefix or Prefix.prefix)
        secret = unhexlify(repr(privkey))

        cc_priv = coincurve.PrivateKey(secret)
        compressed = hexlify(cc_priv.public_key.format(compressed=True)).decode("ascii")
        return cls(compressed, prefix=prefix or Prefix.prefix)

    def unCompressed(self) -> str:
        """Alias for self.uncompressed() - LEGACY"""
        return self.uncompressed()

    @property
    def address(self) -> GrapheneAddress:
        """Obtain a GrapheneAddress from a public key"""
        return GrapheneAddress.from_pubkey(str(self), prefix=self.prefix)


class PrivateKey(Prefix):
    """Derives the compressed and uncompressed public keys and
    constructs two instances of :class:`PublicKey`:

    :param str wif: Base58check-encoded wif key
    :param str prefix: Network prefix (defaults to ``STM``)

    Example::

        PrivateKey("5HqUkGuo62BfcJU5vNhTXKJRXuUi9QSE6jp8C3uBJ2BVHtB8WSd")

    Compressed vs. Uncompressed:

    * ``PrivateKey("w-i-f").pubkey``:
        Instance of :class:`PublicKey` using compressed key.
    * ``PrivateKey("w-i-f").pubkey.address``:
        Instance of :class:`Address` using compressed key.
    * ``PrivateKey("w-i-f").uncompressed``:
        Instance of :class:`PublicKey` using uncompressed key.
    * ``PrivateKey("w-i-f").uncompressed.address``:
        Instance of :class:`Address` using uncompressed key.

    """

    def __init__(
        self, wif: Union[str, "PrivateKey", Base58] | None = None, prefix: str | None = None
    ) -> None:
        self.set_prefix(prefix)
        if wif is None:
            import os

            self._wif = Base58(hexlify(os.urandom(32)).decode("ascii"))
        elif isinstance(wif, PrivateKey):
            self._wif = wif._wif
        elif isinstance(wif, Base58):
            self._wif = wif
        else:
            self._wif = Base58(wif)

        assert len(repr(self._wif)) == 64

    @property
    def bitcoin(self) -> PublicKey:
        return BitcoinPublicKey.from_privkey(self)

    @property
    def address(self) -> Address:
        return Address.from_pubkey(self.pubkey, prefix=self.prefix)

    @property
    def pubkey(self) -> PublicKey:
        return self.compressed

    def get_public_key(self) -> PublicKey:
        """Legacy: Returns the pubkey"""
        return self.pubkey

    @property
    def compressed(self) -> PublicKey:
        return PublicKey.from_privkey(self, prefix=self.prefix)

    @property
    def uncompressed(self) -> PublicKey:
        return PublicKey(self.pubkey.uncompressed(), prefix=self.prefix)

    def get_secret(self) -> bytes:
        """Get sha256 digest of the wif key."""
        return hashlib.sha256(bytes(self)).digest()

    def derive_private_key(self, sequence: int) -> "PrivateKey":
        """Derive new private key from this private key and an arbitrary
        sequence number
        """
        encoded = "%s %d" % (str(self), sequence)
        a = bytes(encoded, "ascii")
        s = hashlib.sha256(hashlib.sha512(a).digest()).digest()
        return PrivateKey(hexlify(s).decode("ascii"), prefix=self.pubkey.prefix)

    def child(self, offset256: bytes) -> "PrivateKey":
        """Derive new private key from this key and a sha256 "offset" """
        a = bytes(self.pubkey) + offset256
        s = hashlib.sha256(a).digest()
        return self.derive_from_seed(s)

    def derive_from_seed(self, offset: bytes) -> "PrivateKey":
        """
        Derive a new PrivateKey by adding a 32-byte integer offset to this key's seed modulo the secp256k1 order.

        Parameters:
            offset (bytes): A 32-byte SHA-256 digest interpreted as a big-endian integer offset to add to this key's secret.

        Returns:
            PrivateKey: A new PrivateKey created from (seed + offset) mod SECP256K1_N, preserving this key's prefix.
        """
        seed = int(hexlify(bytes(self)).decode("ascii"), 16)
        z = int(hexlify(offset).decode("ascii"), 16)
        order = SECP256K1_N
        secexp = (seed + z) % order
        secret = "%0x" % secexp
        if len(secret) < 64:  # left-pad with zeroes
            secret = ("0" * (64 - len(secret))) + secret
        return PrivateKey(secret, prefix=self.pubkey.prefix)

    def __format__(self, _format: str) -> str:
        """Formats the instance of:doc:`Base58 <base58>` according to
        ``_format``
        """
        return format(self._wif, _format)

    def __repr__(self) -> str:
        """Gives the hex representation of the Graphene private key."""
        return repr(self._wif)

    def __str__(self) -> str:
        """Returns the readable (uncompressed wif format) Graphene private key. This
        call is equivalent to ``format(PrivateKey, "WIF")``
        """
        return format(self._wif, "WIF")

    def __bytes__(self) -> bytes:
        """Returns the raw private key"""
        return bytes(self._wif)


class BitcoinAddress(Address):
    @classmethod
    def from_pubkey(
        cls,
        pubkey: str | PublicKey,
        compressed: bool = False,
        version: int = 56,
        prefix: str | None = None,
    ) -> "BitcoinAddress":
        # Ensure this is a public key
        pubkey_obj = PublicKey(pubkey)
        if compressed:
            pubkey_plain = pubkey_obj.compressed()
        else:
            pubkey_plain = pubkey_obj.uncompressed()

        """ Derive address using ``RIPEMD160(SHA256(x))`` """
        addressbin = ripemd160(hexlify(hashlib.sha256(unhexlify(pubkey_plain)).digest()))
        return cls(hexlify(addressbin).decode("ascii"))

    def __str__(self) -> str:
        """Returns the readable Graphene address. This call is equivalent to
        ``format(Address, "GPH")``
        """
        return format(self._address, "BTC")


class BitcoinPublicKey(PublicKey):
    @property
    def address(self) -> BitcoinAddress:
        return BitcoinAddress.from_pubkey(repr(self))
