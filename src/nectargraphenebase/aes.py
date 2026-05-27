import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class AESCipher:
    """
    A classical AES Cipher. Can use any size of data and any size of password thanks to padding.
    Also ensure the coherence and the type of the data with a unicode to byte converter.
    """

    def __init__(self, key: Any) -> None:
        self.bs: int = 32
        self.key = hashlib.sha256(AESCipher.str_to_bytes(key)).digest()

    @staticmethod
    def str_to_bytes(data: Any) -> bytes:
        u_type = type(b"".decode("utf8"))
        if isinstance(data, u_type):
            return data.encode("utf8")
        return data

    def _pad(self, s: bytes) -> bytes:
        return s + (self.bs - len(s) % self.bs) * AESCipher.str_to_bytes(
            chr(self.bs - len(s) % self.bs)
        )

    @staticmethod
    def _unpad(s: bytes) -> bytes:
        count = s[-1]
        # Validate padding to prevent padding oracle attacks
        if s[-count:] == bytes([count]) * count:
            return s[:-count]
        raise ValueError("Invalid padding")

    def encrypt(self, raw: Any) -> str:
        raw = self._pad(AESCipher.str_to_bytes(raw))
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(raw) + encryptor.finalize()
        return base64.b64encode(iv + encrypted).decode("utf-8")

    def decrypt(self, enc: str) -> str:
        enc_bytes = base64.b64decode(enc)
        iv = enc_bytes[:16]
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(enc_bytes[16:]) + decryptor.finalize()
        return self._unpad(decrypted).decode("utf-8")
