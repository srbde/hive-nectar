# Load modules from other classes
# # Inspired by https://raw.githubusercontent.com/xeroc/python-graphenelib/master/graphenestorage/__init__.py
from .base import (
    InRamConfigurationStore,
    InRamEncryptedKeyStore,
    InRamEncryptedTokenStore,
    InRamPlainKeyStore,
    InRamPlainTokenStore,
    SqliteConfigurationStore,
    SqliteEncryptedKeyStore,
    SqliteEncryptedTokenStore,
    SqlitePlainKeyStore,
    SqlitePlainTokenStore,
)
from .interfaces import KeyStoreInterface
from .sqlite import SQLiteCommon, SQLiteFile

__all__ = [
    # submodules
    "interfaces",
    "masterpassword",
    "base",
    "sqlite",
    "ram",
    # store classes re-exported for convenience
    "InRamConfigurationStore",
    "InRamEncryptedKeyStore",
    "InRamEncryptedTokenStore",
    "InRamPlainKeyStore",
    "InRamPlainTokenStore",
    "SqliteConfigurationStore",
    "SqliteEncryptedKeyStore",
    "SqliteEncryptedTokenStore",
    "SqlitePlainKeyStore",
    "SqlitePlainTokenStore",
    "SQLiteCommon",
    "SQLiteFile",
    "KeyStoreInterface",
]


def get_default_config_store(*args, **kwargs):
    """This method returns the default **configuration** store
    that uses an SQLite database internally.
    :params str appname: The appname that is used internally to distinguish
        different SQLite files
    """
    kwargs["appname"] = kwargs.get("appname", "nectar")
    return SqliteConfigurationStore(*args, **kwargs)


def get_default_key_store(*args, config, **kwargs):
    """This method returns the default **key** store
    that uses an SQLite database internally.
    :params str appname: The appname that is used internally to distinguish
        different SQLite files
    """
    kwargs["appname"] = kwargs.get("appname", "nectar")
    return SqliteEncryptedKeyStore(config=config, **kwargs)
