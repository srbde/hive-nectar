#!/usr/bin/env python
#
# Copyright 2014 Corgan Labs
# See LICENSE.txt for distribution terms
# https://github.com/namuyan/bip32nem/blob/master/bip32nem/BIP32Key.py

import codecs
import hashlib
import hmac
import os
import struct
from binascii import hexlify, unhexlify
from hashlib import sha256
from typing import Optional

import coincurve

from nectargraphenebase.base58 import base58CheckDecode, base58CheckEncode

CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

MIN_ENTROPY_LEN = 128  # bits
BIP32_HARDEN = 0x80000000  # choose from hardened set of child keys
EX_MAIN_PRIVATE = [
    codecs.decode("0488ade4", "hex")
]  # Version strings for mainnet extended private keys
EX_MAIN_PUBLIC = [
    codecs.decode("0488b21e", "hex"),
    codecs.decode("049d7cb2", "hex"),
]  # Version strings for mainnet extended public keys
EX_TEST_PRIVATE = [
    codecs.decode("04358394", "hex")
]  # Version strings for testnet extended private keys
EX_TEST_PUBLIC = [
    codecs.decode("043587CF", "hex")
]  # Version strings for testnet extended public keys


def int_to_hex(x: int) -> bytes:
    return bytes(hex(x)[2:], encoding="utf-8")


def parse_path(nstr: str, as_bytes: bool = False) -> list[int] | bytes:
    """Parse a derivation path like \"m/0'/1/2\" into a list of indexes or bytes."""
    r = list()
    for s in nstr.split("/"):
        if s == "m":
            continue
        elif s.endswith("'") or s.endswith("h"):
            r.append(int(s[:-1]) + BIP32_HARDEN)
        else:
            r.append(int(s))
    if not as_bytes:
        return r
    path = b""
    for p in r:
        path += int_to_hex(p)
    return path


class BIP32Key:
    # Static initializers to create from entropy or external formats
    #
    @classmethod
    def fromEntropy(
        cls, entropy: bytes | None = None, public: bool = False, testnet: bool = False
    ) -> "BIP32Key":
        """Create a BIP32Key using supplied entropy >= MIN_ENTROPY_LEN"""
        if entropy is None:
            entropy = os.urandom(MIN_ENTROPY_LEN // 8)  # Python doesn't have os.random()
        if not len(entropy) >= MIN_ENTROPY_LEN // 8:
            raise ValueError(
                "Initial entropy %i must be at least %i bits" % (len(entropy), MIN_ENTROPY_LEN)
            )
        i64 = hmac.new(b"Bitcoin seed", entropy, hashlib.sha512).digest()
        il, ir = i64[:32], i64[32:]
        # FIXME test Il for 0 or less than SECP256k1 prime field order
        key = BIP32Key(
            secret=il, chain=ir, depth=0, index=0, fpr=b"\0\0\0\0", public=False, testnet=testnet
        )
        if public:
            key.SetPublic()
        return key

    @staticmethod
    def fromExtendedKey(xkey: str, public: bool = False) -> "BIP32Key":
        """
        Create a BIP32Key by importing from extended private or public key string

        If public is True, return a public-only key regardless of input type.
        """
        # Sanity checks
        # raw = check_decode(xkey)
        raw = unhexlify(base58CheckDecode(xkey, skip_first_bytes=False))

        if len(raw) != 78:
            raise ValueError("extended key format wrong length")

        # Verify address version/type
        version = raw[:4]
        if version in EX_MAIN_PRIVATE:
            is_testnet = False
            is_pubkey = False
        elif version in EX_TEST_PRIVATE:
            is_testnet = True
            is_pubkey = False
        elif version in EX_MAIN_PUBLIC:
            is_testnet = False
            is_pubkey = True
        elif version in EX_TEST_PUBLIC:
            is_testnet = True
            is_pubkey = True
        else:
            raise ValueError("unknown extended key version")

        # Extract remaining fields
        depth = raw[4]
        fpr = raw[5:9]
        child = struct.unpack(">L", raw[9:13])[0]
        chain = raw[13:45]
        secret = raw[45:78]

        # Extract private key or public key point
        if not is_pubkey:
            secret = secret[1:]
        else:
            secret = coincurve.PublicKey(secret)

        key = BIP32Key(
            secret=secret,
            chain=chain,
            depth=depth,
            index=child,
            fpr=fpr,
            public=is_pubkey,
            testnet=is_testnet,
        )
        if not is_pubkey and public:
            key.SetPublic()
        return key

    # Normal class initializer
    def __init__(
        self,
        secret: bytes | coincurve.PublicKey,
        chain: bytes,
        depth: int,
        index: int,
        fpr: bytes,
        public: bool = False,
        testnet: bool = False,
    ) -> None:
        """
        Create a public or private BIP32Key using key material and chain code.

        secret   This is the source material to generate the keypair, either a
                 32-byte str representation of a private key, or the coincurve
                 PublicKey object representing a public key.

        chain    This is a 32-byte str representation of the chain code

        depth    Child depth; parent increments its own by one when assigning this

        index    Child index

        fpr      Parent fingerprint

        public   If true, this keypair will only contain a public key and can only create
                 a public key chain.
        """

        self.public = public
        self.C = chain
        self.depth = depth
        self.index = index
        self.parent_fpr = fpr
        self.testnet = testnet
        if public is False:
            if not isinstance(secret, bytes):
                raise TypeError("Secret must be bytes for private keys")
            self.k = coincurve.PrivateKey(secret)
            self.K = self.k.public_key
        else:
            self.k = None
            if isinstance(secret, bytes):
                self.K = coincurve.PublicKey(secret)
            else:
                self.K = secret

    # Internal methods not intended to be called externally
    #
    def hmac(self, data: bytes) -> tuple[bytes, bytes]:
        """
        Calculate the HMAC-SHA512 of input data using the chain code as key.

        Returns a tuple of the left and right halves of the HMAC
        """
        i64 = hmac.new(self.C, data, hashlib.sha512).digest()
        return i64[:32], i64[32:]

    def CKDpriv(self, i: int) -> Optional["BIP32Key"]:
        """
        Create a child key of index 'i'.

        If the most significant bit of 'i' is set, then select from the
        hardened key set, otherwise, select a regular child key.

        Returns a BIP32Key constructed with the child key parameters,
        or None if i index would result in an invalid key.
        """
        # Index as bytes, BE
        i_str = struct.pack(">L", i)

        # Data to HMAC
        if i & BIP32_HARDEN:
            if self.k is None:
                raise Exception("No private key available for hardened derivation")
            data = b"\0" + self.k.secret + i_str
        else:
            data = self.PublicKey() + i_str
        # Get HMAC of data
        (Il, Ir) = self.hmac(data)

        # Construct new key material from Il and current private key
        Il_int = int.from_bytes(Il, "big")
        if Il_int >= CURVE_ORDER:
            return None
        if self.k is None:
            return None
        pvt_int = int.from_bytes(self.k.secret, "big")
        k_int = (Il_int + pvt_int) % CURVE_ORDER
        if k_int == 0:
            return None
        secret = k_int.to_bytes(32, "big")

        # Construct and return a new BIP32Key
        return BIP32Key(
            secret=secret,
            chain=Ir,
            depth=self.depth + 1,
            index=i,
            fpr=self.Fingerprint(),
            public=False,
            testnet=self.testnet,
        )

    def CKDpub(self, i: int) -> Optional["BIP32Key"]:
        """
        Create a publicly derived child key of index 'i'.

        If the most significant bit of 'i' is set, this is
        an error.

        Returns a BIP32Key constructed with the child key parameters,
        or None if index would result in invalid key.
        """

        if i & BIP32_HARDEN:
            raise Exception("Cannot create a hardened child key using public child derivation")

        # Data to HMAC.  Same as CKDpriv() for public child key.
        data = self.PublicKey() + struct.pack(">L", i)

        # Get HMAC of data
        (Il, Ir) = self.hmac(data)

        Il_int = int.from_bytes(Il, "big")
        if Il_int >= CURVE_ORDER:
            return None
        if self.K is None:
            return None

        try:
            K_i = self.K.add(Il)
        except ValueError:
            return None

        # Construct and return a new BIP32Key
        return BIP32Key(
            secret=K_i,
            chain=Ir,
            depth=self.depth + 1,
            index=i,
            fpr=self.Fingerprint(),
            public=True,
            testnet=self.testnet,
        )

    # Public methods
    #
    def ChildKey(self, i: int) -> Optional["BIP32Key"]:
        """
        Create and return a child key of this one at index 'i'.

        The index 'i' should be summed with BIP32_HARDEN to indicate
        to use the private derivation algorithm.
        """
        if self.public is False:
            return self.CKDpriv(i)
        else:
            return self.CKDpub(i)

    def SetPublic(self) -> None:
        """Convert a private BIP32Key into a public one"""
        self.k = None
        self.public = True

    def PrivateKey(self) -> bytes:
        """Return private key as string"""
        if self.public:
            raise Exception("Publicly derived deterministic keys have no private half")
        if self.k is None:
            raise Exception("No private key available")
        return self.k.secret

    def PublicKey(self) -> bytes:
        """Return compressed public key encoding"""
        if self.K is None:
            raise Exception("No public key available")
        return self.K.format(compressed=True)

    def ChainCode(self) -> bytes:
        """Return chain code as string"""
        return self.C

    def Identifier(self) -> bytes:
        """Return key identifier as string"""
        cK = self.PublicKey()
        return hashlib.new("ripemd160", sha256(cK).digest()).digest()

    def Fingerprint(self) -> bytes:
        """Return key fingerprint as string"""
        return self.Identifier()[:4]

    def Address(self) -> str:
        """Return compressed public key address"""
        addressversion = b"\x00" if not self.testnet else b"\x6f"
        # vh160 = addressversion + self.Identifier()
        # return check_encode(vh160)
        payload = hexlify(self.Identifier()).decode("ascii")
        return base58CheckEncode(int.from_bytes(addressversion, "big"), payload)

    def P2WPKHoP2SHAddress(self) -> str:
        """Return P2WPKH over P2SH segwit address"""
        pk_bytes = self.PublicKey()
        assert len(pk_bytes) == 33 and (
            pk_bytes.startswith(b"\x02") or pk_bytes.startswith(b"\x03")
        ), (
            "Only compressed public keys are compatible with p2sh-p2wpkh addresses. "
            "See https://github.com/bitcoin/bips/blob/master/bip-0049.mediawiki."
        )
        pk_hash = hashlib.new("ripemd160", sha256(pk_bytes).digest()).digest()
        push_20 = bytes.fromhex("0014")
        script_sig = push_20 + pk_hash
        address_bytes = hashlib.new("ripemd160", sha256(script_sig).digest()).digest()
        prefix = b"\xc4" if self.testnet else b"\x05"
        # return check_encode(prefix + address_bytes)
        payload = hexlify(address_bytes).decode("ascii")
        return base58CheckEncode(int.from_bytes(prefix, "big"), payload)

    def WalletImportFormat(self) -> str:
        """Returns private key encoded for wallet import"""
        if self.public:
            raise Exception("Publicly derived deterministic keys have no private half")
        if self.k is None:
            raise Exception("No private key available")
        addressversion = b"\x80" if not self.testnet else b"\xef"
        raw = self.k.secret + b"\x01"  # Always compressed
        # return check_encode(addressversion + raw)
        payload = hexlify(raw).decode("ascii")
        return base58CheckEncode(int.from_bytes(addressversion, "big"), payload)

    def ExtendedKey(self, private: bool = True, encoded: bool = True) -> str | bytes:
        """Return extended private or public key as string, optionally base58 encoded"""
        if self.public is True and private is True:
            raise Exception(
                "Cannot export an extended private key from a public-only deterministic key"
            )
        if not self.testnet:
            version = EX_MAIN_PRIVATE[0] if private else EX_MAIN_PUBLIC[0]
        else:
            version = EX_TEST_PRIVATE[0] if private else EX_TEST_PUBLIC[0]
        depth = bytes(bytearray([self.depth]))
        fpr = self.parent_fpr
        child = struct.pack(">L", self.index)
        chain = self.C
        if self.public is True or private is False:
            data = self.PublicKey()
        else:
            data = b"\x00" + self.PrivateKey()
        raw = version + depth + fpr + child + chain + data
        if not encoded:
            return raw
        else:
            # return check_encode(raw)
            payload = hexlify(chain + data).decode("ascii")
            version_int = int.from_bytes(version + depth + fpr + child, "big")
            return base58CheckEncode(version_int, payload)

    # Debugging methods
    #
    def dump(self):
        """Dump key fields mimicking the BIP0032 test vector format"""
        print("   * Identifier")
        print("     * (hex):      ", self.Identifier().hex())
        print("     * (fpr):      ", self.Fingerprint().hex())
        print("     * (main addr):", self.Address())
        if self.public is False:
            print("   * Secret key")
            print("     * (hex):      ", self.PrivateKey().hex())
            print("     * (wif):      ", self.WalletImportFormat())
        print("   * Public key")
        print("     * (hex):      ", self.PublicKey().hex())
        print("   * Chain code")
        print("     * (hex):      ", self.C.hex())
        print("   * Serialized")
        pub_hex = self.ExtendedKey(private=False, encoded=False)
        prv_hex = self.ExtendedKey(private=True, encoded=False) if not self.public else None
        print("     * (pub hex):  ", pub_hex.hex() if isinstance(pub_hex, bytes) else str(pub_hex))
        print("     * (pub b58):  ", self.ExtendedKey(private=False, encoded=True))
        if self.public is False:
            print(
                "     * (prv hex):  ", prv_hex.hex() if isinstance(prv_hex, bytes) else str(prv_hex)
            )
            print("     * (prv b58):  ", self.ExtendedKey(private=True, encoded=True))


def test():
    from binascii import a2b_hex

    # BIP0032 Test vector 1
    entropy = a2b_hex("000102030405060708090A0B0C0D0E0F")
    m = BIP32Key.fromEntropy(entropy)
    print("Test vector 1:")
    print("Master (hex):", entropy.hex())
    print("* [Chain m]")
    m.dump()

    print("* [Chain m/0h]")
    m_child = m.ChildKey(0 + BIP32_HARDEN)
    if m_child:
        m_child.dump()
    else:
        print("Failed to create child key")

    print("* [Chain m/0h/1]")
    m_child2 = m_child.ChildKey(1) if m_child else None
    if m_child2:
        m_child2.dump()
    else:
        print("Failed to create grandchild key")

    print("* [Chain m/0h/1/2h]")
    m_child3 = m_child2.ChildKey(2 + BIP32_HARDEN) if m_child2 else None
    if m_child3:
        m_child3.dump()
    else:
        print("Failed to create great-grandchild key")

    print("* [Chain m/0h/1/2h/2]")
    m_child4 = m_child3.ChildKey(2) if m_child3 else None
    if m_child4:
        m_child4.dump()
    else:
        print("Failed to create 4th level key")

    print("* [Chain m/0h/1/2h/2/1000000000]")
    m_child5 = m_child4.ChildKey(1000000000) if m_child4 else None
    if m_child5:
        m_child5.dump()
    else:
        print("Failed to create 5th level key")

    # BIP0032 Test vector 2
    entropy = a2b_hex(
        "fffcf9f6f3f0edeae7e4e1dedbd8d5d2cfccc9c6c3c0bdbab7b4b1aeaba8a5a29f9c999693908d8a878481"
        "7e7b7875726f6c696663605d5a5754514e4b484542"
    )
    m = BIP32Key.fromEntropy(entropy)
    print("Test vector 2:")
    print("Master (hex):", entropy.hex())
    print("* [Chain m]")
    m.dump()

    print("* [Chain m/0]")
    m2_child = m.ChildKey(0)
    if m2_child:
        m2_child.dump()
    else:
        print("Failed to create child key")

    print("* [Chain m/0/2147483647h]")
    m2_child2 = m2_child.ChildKey(2147483647 + BIP32_HARDEN) if m2_child else None
    if m2_child2:
        m2_child2.dump()
    else:
        print("Failed to create grandchild key")

    print("* [Chain m/0/2147483647h/1]")
    m2_child3 = m2_child2.ChildKey(1) if m2_child2 else None
    if m2_child3:
        m2_child3.dump()
    else:
        print("Failed to create great-grandchild key")

    print("* [Chain m/0/2147483647h/1/2147483646h]")
    m2_child4 = m2_child3.ChildKey(2147483646 + BIP32_HARDEN) if m2_child3 else None
    if m2_child4:
        m2_child4.dump()
    else:
        print("Failed to create 4th level key")

    print("* [Chain m/0/2147483647h/1/2147483646h/2]")
    m2_child5 = m2_child4.ChildKey(2) if m2_child4 else None
    if m2_child5:
        m2_child5.dump()
    else:
        print("Failed to create 5th level key")


if __name__ == "__main__":
    test()
