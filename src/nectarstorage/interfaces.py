# Inspired by https://raw.githubusercontent.com/xeroc/python-graphenelib/master/graphenestorage/interfaces.py
from typing import Any, Iterator, Optional, Protocol


class StoreInterface(object):
    """The store interface is the most general store that we can have.

    It behaves like a dictionary but allows returning None for missing keys and
    keeps a `defaults` mapping that can supply fallback values.

    .. note:: This class defines ``defaults`` that are used to return
        reasonable defaults for the library.

    .. warning:: If you are trying to obtain a value for a key that does
        **not** exist in the store, the library will **NOT** raise but
        return a ``None`` value. This represents the biggest difference to
        a regular ``dict`` class.
    """

    defaults: dict[str, Any] = {}

    def setdefault(self, key, value=None):
        """Allows to define default values on this store instance."""
        if value is None and key in self.defaults:
            return self.defaults[key]
        if value is not None:
            self.defaults[key] = value
        return self._data.setdefault(key, value)

    def __init__(self, *_args, **_kwargs):
        self._data: dict[Any, Any] = {}

    def __setitem__(self, key, value):
        """Sets an item in the store"""
        self._data[key] = value

    def __getitem__(self, key):
        """Gets an item from the store as if it was a dictionary

        .. note:: Returns the value from the store or from defaults if
            the key is found there. Raises ``KeyError`` if not found
            in either.
        """
        if key in self._data:
            return self._data[key]
        if key in self.defaults:
            return self.defaults[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[Any]:
        """Iterates through the store"""
        return iter(self._data)

    def __len__(self) -> int:
        """return length of store"""
        return len(self._data)

    def __contains__(self, key) -> bool:
        """Tests if a key is contained in the store."""
        return key in self._data

    def __delitem__(self, key: Any) -> None:
        if key not in self._data:
            raise KeyError(key)
        self._data.pop(key)

    def keys(self):
        """Returns the keys of the store"""
        return self._data.keys()

    def values(self):
        """Returns the values of the store"""
        return self._data.values()

    def items(self):
        """Returns all items of the store as tuples"""
        return self._data.items()

    def get(self, key, default=None):
        """Return the key if exists or a default value"""
        return self._data.get(key, self.defaults.get(key, default))

    def pop(self, key, default=None):
        """Remove a key and return its value or a default"""
        if key in self._data:
            val = self._data[key]
            self.__delitem__(key)
            return val
        return default

    def clear(self) -> None:
        """Clear all entries from the store"""
        self._data.clear()

    def update(self, other=None, **kwargs) -> None:
        """Update the store with keys and values from other"""
        if other is not None:
            if hasattr(other, "keys"):
                for k in other:
                    self[k] = other[k]
            else:
                for k, v in other:
                    self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    # Specific for this library
    def delete(self, key):
        """Delete a key from the store"""
        raise NotImplementedError

    def wipe(self):
        """Wipe the store"""
        raise NotImplementedError


class KeyInterface(StoreInterface):
    """The KeyInterface defines the interface for key storage.

    .. note:: This class inherits
        :class:`nectarstorage.interfaces.StoreInterface` and defines
        additional key-specific methods.
    """

    def is_encrypted(self):
        """Returns True/False to indicate required use of unlock"""
        return False

    # Interface to deal with encrypted keys
    def getPublicKeys(self):
        """Returns the public keys stored in the database"""
        raise NotImplementedError

    def getPrivateKeyForPublicKey(self, pub):
        """Returns the (possibly encrypted) private key that
         corresponds to a public key

        :param str pub: Public key

        The encryption scheme is BIP38
        """
        raise NotImplementedError

    def add(self, wif, pub=None):
        """Add a new public/private key pair (correspondence has to be checked elsewhere!)

        :param str pub: Public key
        :param str wif: Private key
        """
        raise NotImplementedError

    def delete(self, key):
        """Delete a pubkey/privatekey pair from the store

        :param str key: Public key
        """
        raise NotImplementedError


class EncryptedKeyInterface(KeyInterface):
    """The EncryptedKeyInterface extends KeyInterface to work with encrypted
    keys
    """

    def is_encrypted(self):
        """Returns True/False to indicate required use of unlock"""
        return True

    def unlock(self, password):
        """Tries to unlock the wallet if required

        :param str password: Plain password
        """
        raise NotImplementedError

    def locked(self):
        """is the wallet locked?"""
        return False

    def lock(self):
        """Lock the wallet again"""
        raise NotImplementedError


class ConfigInterface(StoreInterface):
    """The BaseKeyStore defines the interface for key storage

    .. note:: This class inherits
        :class:`nectarstorage.interfaces.StoreInterface` and defines
        **no** additional configuration-specific methods.
    """

    pass


class TokenInterface(StoreInterface):
    """The TokenInterface defines the interface for token storage.

    .. note:: This class inherits
        :class:`nectarstorage.interfaces.StoreInterface` and defines
        additional key-specific methods.
    """

    def is_encrypted(self):
        """Returns True/False to indicate required use of unlock"""
        return False

    # Interface to deal with tokens
    def getPublicNames(self):
        """Returns the public token names stored in the database"""
        raise NotImplementedError

    def getTokenForName(self, name):
        """Returns the (possibly encrypted) token that corresponds to a name"""
        raise NotImplementedError

    def getPrivateKeyForPublicKey(self, pub):
        """Legacy compatibility alias for getTokenForName."""
        return self.getTokenForName(pub)

    def add(self, token, name=None):
        """Add a new token entry (correspondence has to be checked elsewhere!)

        :param str name: Public identifier
        :param str token: Token value
        """
        raise NotImplementedError

    def delete(self, key):
        """Delete a token entry from the store

        :param str key: Public identifier
        """
        raise NotImplementedError


class EncryptedTokenInterface(TokenInterface):
    """The EncryptedKeyInterface extends KeyInterface to work with encrypted
    tokens
    """

    def is_encrypted(self):
        """Returns True/False to indicate required use of unlock"""
        return True

    def unlock(self, password):
        """Tries to unlock the wallet if required

        :param str password: Plain password
        """
        raise NotImplementedError

    def locked(self):
        """is the wallet locked?"""
        return False

    def lock(self):
        """Lock the wallet again"""
        raise NotImplementedError


class KeyStoreInterface(Protocol):
    """Protocol defining the interface for key storage."""

    def is_encrypted(self) -> bool: ...

    def unlock(self, password: str) -> bool: ...

    def lock(self) -> bool: ...

    def locked(self) -> bool: ...

    def change_password(self, new_pwd: str) -> None: ...

    def getPublicKeys(self) -> list[str]: ...

    def getPrivateKeyForPublicKey(self, pub: str) -> Optional[str]: ...

    def add(self, wif: str, pub: Optional[str] = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def wipe(self) -> None: ...

    def wipe_masterpassword(self) -> None: ...
