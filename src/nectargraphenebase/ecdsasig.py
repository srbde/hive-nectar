import hashlib
import logging
import struct
from binascii import hexlify, unhexlify
from typing import Any, Callable, Optional, Union

import coincurve
from coincurve._libsecp256k1 import ffi  # type: ignore
from cryptography.exceptions import InvalidSignature

from .account import PrivateKey, PublicKey

log = logging.getLogger(__name__)


def _is_canonical(sig: Union[bytes, bytearray]) -> bool:
    """
    Return True if a 64-byte ECDSA signature (R || S) is in canonical form.

    A canonical signature here means:
    - Neither R nor S has its highest bit set (no negative integers when interpreted as signed big-endian).
    - Neither R nor S has unnecessary leading zero bytes (no extra 0x00 padding before a non-negative highest byte).

    Parameters:
        sig (bytes or bytearray): 64-byte concatenation of R (32 bytes) followed by S (32 bytes).

    Returns:
        bool: True if signature is canonical, False otherwise.
    """
    sig = bytearray(sig)
    return (
        not (int(sig[0]) & 0x80)
        and not (sig[0] == 0 and not (int(sig[1]) & 0x80))
        and not (int(sig[32]) & 0x80)
        and not (sig[32] == 0 and not (int(sig[33]) & 0x80))
    )


def compressedPubkey(pk: Any) -> bytes:
    """
    Return the 33-byte compressed secp256k1 public key for the given public-key object.

    Parameters:
        pk: Public-key object (coincurve.PublicKey, account.PublicKey, or bytes).

    Returns:
        bytes: 33-byte compressed public key.
    """
    if isinstance(pk, bytes):
        return coincurve.PublicKey(pk).format(compressed=True)
    if isinstance(pk, PublicKey):
        return bytes(pk)
    if hasattr(pk, "format"):
        return pk.format(compressed=True)
    raise ValueError(f"Unknown public key type: {type(pk)}")


def recover_public_key(
    digest: bytes, signature: bytes, i: int, message: Optional[bytes] = None
) -> Optional[coincurve.PublicKey]:
    """
    Recover the secp256k1 public key from an ECDSA signature and message hash.

    If `message` is provided, the function will recover the public key using the message.
    Otherwise, it recovers the public key using the digest.

    Parameters:
        digest (bytes): The message hash (big-endian) used when signing.
        signature (bytes): 64-byte signature consisting of r||s (raw concatenation).
        i (int): Recovery identifier (0..3) selecting which of the possible curve points to use.
        message (bytes, optional): Original message to verify against.

    Returns:
        coincurve.PublicKey on success, None on failure (if message is None),
        or raises InvalidSignature (if message is not None).

    Raises:
        InvalidSignature: If signature verification fails when message is provided.
    """
    recoverable_sig = signature + bytes([i])
    try:
        return coincurve.PublicKey.from_signature_and_message(recoverable_sig, digest, hasher=None)
    except ValueError as e:
        if message is not None:
            raise InvalidSignature("Signature verification failed") from e
        return None


def recoverPubkeyParameter(
    message: Optional[Union[str, bytes]],
    digest: bytes,
    signature: bytes,
    pubkey: Any,
) -> Optional[int]:
    """
    Determine the ECDSA recovery parameter (0–3) that, when used with the given digest and 64-byte signature (R||S), reproduces the provided public key.

    Attempts each recovery index i in 0..3, recovers a candidate public key, and compares its compressed form to the compressed form of the supplied pubkey. If a match is found returns the matching index; otherwise returns None.

    Returns:
        int: matching recovery parameter in 0..3, or None if no match is found.
    """
    if not isinstance(message, bytes):
        if message is None:
            message = b""
        else:
            message = bytes(message, "utf-8")

    expected_comp = hexlify(compressedPubkey(pubkey))
    for i in range(0, 4):
        p = recover_public_key(digest, signature, i, message)
        if p is None:
            continue
        p_comp = hexlify(compressedPubkey(p))
        if p_comp == expected_comp:
            return i
    return None


def sign_message(message: Union[str, bytes], wif: str, hashfn: Callable = hashlib.sha256) -> bytes:
    """
    Sign a message using a private key in Wallet Import Format (WIF) and return a compact, canonical ECDSA signature.

    Signs the provided message with secp256k1 ECDSA-SHA256 using the private key derived from the given WIF. The function repeats signing as needed until it produces a canonical 64-byte R||S signature (both R and S encoded as 32 bytes). It also computes the recovery parameter for the signature and encodes it into the first byte of the returned blob.

    Parameters:
        message (bytes or str): Message to sign. If a str is provided it is encoded as UTF-8 before hashing.
        wif (str): Private key in Wallet Import Format (WIF).
        hashfn (callable, optional): Hash function to apply to the message prior to recovery-parameter computation; defaults to hashlib.sha256.

    Returns:
        bytes: 65-byte compact signature: 1-byte recovery/version prefix (recovery parameter adjusted for compact/compressed form) followed by the 64-byte R||S sequence.
    """
    if not isinstance(message, bytes):
        message = bytes(message, "utf-8")

    # Detect if message is already a digest
    prehashed = len(message) == hashfn().digest_size

    if prehashed:
        digest = message
    else:
        digest = hashfn(message).digest()

    priv_key = PrivateKey(wif)
    priv_bytes = unhexlify(repr(priv_key))
    private_key = coincurve.PrivateKey(priv_bytes)

    cnt = 0
    while True:
        cnt += 1
        if not cnt % 20:
            log.info("Still searching for a canonical signature. Tried %d times already!" % cnt)

        extra_entropy = cnt.to_bytes(32, "big")
        extra_entropy_c = ffi.new("unsigned char [32]", extra_entropy)

        try:
            recoverable_sig = private_key.sign_recoverable(
                digest, hasher=None, custom_nonce=(ffi.NULL, extra_entropy_c)
            )
        except ValueError:
            continue

        signature = recoverable_sig[:64]
        if _is_canonical(signature):
            i = recoverable_sig[64]
            i += 4  # compressed
            i += 27  # compact
            break

    # pack signature
    sigstr = struct.pack("<B", i)
    sigstr += signature

    return sigstr


def verify_message(
    message: Union[str, bytes],
    signature: Union[str, bytes],
    hashfn: Callable = hashlib.sha256,
    recover_parameter: Optional[int] = None,
) -> Optional[bytes]:
    """
    Verify an ECDSA secp256k1 signature against a message and return the signer's compressed public key.

    Parameters:
        message (bytes or str): The message to verify. If a str, it will be UTF-8 encoded.
        signature (bytes or str): 65-byte compact signature where the first byte encodes the recovery parameter/version and the remaining 64 bytes are R||S. If a str, it will be UTF-8 encoded.
        hashfn (callable): Hash function constructor used to compute the digest of the message (default: hashlib.sha256). Note: The actual verification uses SHA256 regardless of this parameter.
        recover_parameter (int, optional): Explicit recovery parameter (0–3). If omitted, it is extracted from the signature's first byte.

    Returns:
        bytes: The 33-byte compressed public key of the recovered signer on successful verification.

    Notes:
        - Cryptographic verification errors (e.g., invalid signature) will propagate as raised exceptions.
    """
    if not isinstance(message, bytes):
        message = bytes(message, "utf-8")
    if not isinstance(signature, bytes):
        signature = bytes(signature, "utf-8")
    digest = hashfn(message).digest()
    sig = signature[1:]
    if recover_parameter is None:
        recover_parameter = bytearray(signature)[0] - 4 - 27  # recover parameter only
    if recover_parameter < 0:
        log.info("Could not recover parameter")
        return None

    p = recover_public_key(digest, sig, recover_parameter, message)
    if p is None:
        return None
    phex = compressedPubkey(p)
    return phex
