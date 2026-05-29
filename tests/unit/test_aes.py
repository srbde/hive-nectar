import base64
import random
import string

import pytest

from nectargraphenebase.aes import AESCipher


@pytest.fixture
def aes():
    return AESCipher("Foobar")


def test_str():
    assert isinstance(AESCipher.str_to_bytes("foobar"), bytes)
    assert isinstance(AESCipher.str_to_bytes(b"foobar"), bytes)


def test_key(aes):
    assert base64.b64encode(aes.key) == b"6BGBj4DZw8ItV3uoPWGWeI5VO7QIU1u0IQXN/3JqYKs="


def test_pad(aes):
    assert base64.b64encode(aes._pad(b"123456")) == b"MTIzNDU2GhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGho="


def test_unpad(aes):
    assert (
        aes._unpad(base64.b64decode(b"MTIzNDU2GhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGho=")) == b"123456"
    )


def test_padding(aes):
    for n in range(1, 64):
        name = "".join(random.choice(string.ascii_lowercase) for _ in range(n))
        assert aes._unpad(aes._pad(bytes(name, "utf-8"))) == bytes(name, "utf-8")


def test_encdec(aes):
    for n in range(1, 16):
        name = "".join(random.choice(string.ascii_lowercase) for _ in range(64))
        assert aes.decrypt(aes.encrypt(name)) == name
