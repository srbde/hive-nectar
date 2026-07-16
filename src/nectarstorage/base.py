# Inspired by https://raw.githubusercontent.com/xeroc/python-graphenelib/master/graphenestorage/base.py
import logging

from .exceptions import KeyAlreadyInStoreException
from .interfaces import (
    ConfigInterface,
    EncryptedKeyInterface,
    EncryptedTokenInterface,
    KeyInterface,
    TokenInterface,
)
from .masterpassword import MasterPassword
from .ram import InRamStore
from .sqlite import SQLiteStore

log = logging.getLogger(__name__)


# Configuration
class InRamConfigurationStore(InRamStore, ConfigInterface):
    """A simple example that stores configuration in RAM.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.ConfigInterface`.
    """

    pass


class SqliteConfigurationStore(SQLiteStore, ConfigInterface):
    """This is the configuration storage that stores key/value
    pairs in the `config` table of the SQLite3 database.

    Internally, this works by simply inheriting
    :class:`nectarstorage.sqlite.SQLiteStore`. The interface is defined
    in :class:`nectarstorage.interfaces.ConfigInterface`.
    """

    #: The table name for the configuration
    __tablename__ = "config"
    #: The name of the 'key' column
    __key__ = "key"
    #: The name of the 'value' column
    __value__ = "value"


# Keys
class InRamPlainKeyStore(InRamStore, KeyInterface):
    """A simple in-RAM Store that stores keys unencrypted in RAM

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.KeyInterface`.
    """

    def getPublicKeys(self):
        return [k for k, v in self.items()]

    def getPrivateKeyForPublicKey(self, pub):
        return self.get(str(pub), None)

    def add(self, wif, pub=None):
        if pub is None:
            raise ValueError("pub key required")
        if str(pub) in self:
            raise KeyAlreadyInStoreException
        self[str(pub)] = str(wif)

    def delete(self, key):
        InRamStore.delete(self, str(key))


class SqlitePlainKeyStore(SQLiteStore, KeyInterface):
    """This is the key storage that stores the public key and the
    **unencrypted** private key in the `keys` table in the SQLite3
    database.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.KeyInterface`.
    """

    #: The table name for the configuration
    __tablename__ = "keys"
    #: The name of the 'key' column
    __key__ = "pub"
    #: The name of the 'value' column
    __value__ = "wif"

    def getPublicKeys(self):
        return [k for k, v in self.items()]

    def getPrivateKeyForPublicKey(self, pub):
        return self.get(str(pub), None)

    def add(self, wif, pub=None):
        if pub is None:
            raise ValueError("pub key required")
        if str(pub) in self:
            raise KeyAlreadyInStoreException
        self[str(pub)] = str(wif)

    def delete(self, key):
        SQLiteStore.delete(self, str(key))

    def is_encrypted(self):
        """Returns False, as we are not encrypted here"""
        return False


class KeyEncryption(MasterPassword, EncryptedKeyInterface):
    """This is an interface class that provides the methods required for
    EncryptedKeyInterface and links them to the MasterPassword-provided
    functionatlity, accordingly.
    """

    def __init__(self, *args, **kwargs):
        EncryptedKeyInterface.__init__(self, *args, **kwargs)
        MasterPassword.__init__(self, *args, **kwargs)

    # Interface to deal with encrypted keys
    def getPublicKeys(self):
        return [k for k, v in self.items()]

    def getPrivateKeyForPublicKey(self, pub):
        wif = self.get(str(pub), None)
        if wif:
            return self.decrypt(wif)  # From Masterpassword

    def add(self, wif, pub=None):
        if pub is None:
            raise ValueError("pub key required")
        if str(pub) in self:
            raise KeyAlreadyInStoreException
        self[str(pub)] = self.encrypt(str(wif))  # From Masterpassword

    def is_encrypted(self):
        return True


class InRamEncryptedKeyStore(InRamStore, KeyEncryption):
    """An in-RAM Store that stores keys **encrypted** in RAM.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.KeyInterface`.

    .. note:: This module also inherits
        :class:`nectarstorage.masterpassword.MasterPassword` which offers
        additional methods and deals with encrypting the keys.
    """

    def __init__(self, *args, **kwargs):
        InRamStore.__init__(self, *args, **kwargs)
        KeyEncryption.__init__(self, *args, **kwargs)


class SqliteEncryptedKeyStore(SQLiteStore, KeyEncryption):
    """This is the key storage that stores the public key and the
    **encrypted** private key in the `keys` table in the SQLite3 database.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.KeyInterface`.

    .. note:: This module also inherits
        :class:`nectarstorage.masterpassword.MasterPassword` which offers
        additional methods and deals with encrypting the keys.
    """

    __tablename__ = "keys"
    __key__ = "pub"
    __value__ = "wif"

    def __init__(self, *args, **kwargs):
        SQLiteStore.__init__(self, *args, **kwargs)
        KeyEncryption.__init__(self, *args, **kwargs)


# Token
class InRamPlainTokenStore(InRamStore, TokenInterface):
    """A simple in-RAM Store that stores token unencrypted in RAM

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.TokenInterface`.
    """

    def getPublicNames(self):
        return [k for k, v in self.items()]

    def getTokenForName(self, name):
        return self.get(str(name), None)

    def add(self, token, name=None):
        if name is None:
            raise ValueError("name required")
        if str(name) in self:
            raise KeyAlreadyInStoreException
        self[str(name)] = str(token)

    def delete(self, key):
        InRamStore.delete(self, str(key))


class SqlitePlainTokenStore(SQLiteStore, TokenInterface):
    """This is the token storage that stores the public key and the
    **unencrypted** private key in the `tokens` table in the SQLite3
    database.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.TokenInterface`.
    """

    #: The table name for the configuration
    __tablename__ = "token"
    #: The name of the 'key' column
    __key__ = "name"
    #: The name of the 'value' column
    __value__ = "token"

    def getPublicNames(self):
        return [k for k, v in self.items()]

    def getTokenForName(self, name):
        return self.get(str(name), None)

    def add(self, token, name=None):
        if name is None:
            raise ValueError("name required")
        if str(name) in self:
            raise KeyAlreadyInStoreException
        self[str(name)] = str(token)

    def updateToken(self, name, token):
        self[str(name)] = str(token)

    def delete(self, key):
        SQLiteStore.delete(self, str(key))

    def is_encrypted(self):
        """Returns False, as we are not encrypted here"""
        return False


class TokenEncryption(MasterPassword, EncryptedTokenInterface):
    """This is an interface class that provides the methods required for
    EncryptedTokenInterface and links them to the MasterPassword-provided
    functionatlity, accordingly.
    """

    def __init__(self, *args, **kwargs):
        EncryptedTokenInterface.__init__(self, *args, **kwargs)
        MasterPassword.__init__(self, *args, **kwargs)

    # Interface to deal with encrypted keys
    def getPublicNames(self):
        return [k for k, v in self.items()]

    def getTokenForName(self, name):
        token = self.get(str(name), None)
        if token:
            return self.decrypt_text(token)  # From Masterpassword

    def add(self, token, name=None):
        if name is None:
            raise ValueError("name required")
        if str(name) in self:
            raise KeyAlreadyInStoreException
        self[str(name)] = self.encrypt_text(str(token))  # From Masterpassword

    def updateToken(self, name, token):
        self[str(name)] = self.encrypt_text(str(token))  # From Masterpassword

    def is_encrypted(self):
        return True


class InRamEncryptedTokenStore(InRamStore, TokenEncryption):
    """An in-RAM Store that stores token **encrypted** in RAM.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.TokenInterface`.

    .. note:: This module also inherits
        :class:`nectarstorage.masterpassword.MasterPassword` which offers
        additional methods and deals with encrypting the keys.
    """

    def __init__(self, *args, **kwargs):
        InRamStore.__init__(self, *args, **kwargs)
        TokenEncryption.__init__(self, *args, **kwargs)


class SqliteEncryptedTokenStore(SQLiteStore, TokenEncryption):
    """This is the key storage that stores the account name and the
    **encrypted** token in the `token` table in the SQLite3 database.

    Internally, this works by simply inheriting
    :class:`nectarstorage.ram.InRamStore`. The interface is defined in
    :class:`nectarstorage.interfaces.TokenInterface`.

    .. note:: This module also inherits
        :class:`nectarstorage.masterpassword.MasterPassword` which offers
        additional methods and deals with encrypting the token.
    """

    __tablename__ = "token"
    __key__ = "name"
    __value__ = "token"

    def __init__(self, *args, **kwargs):
        SQLiteStore.__init__(self, *args, **kwargs)
        TokenEncryption.__init__(self, *args, **kwargs)
