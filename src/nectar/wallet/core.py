from __future__ import annotations

import logging
from typing import Any, Dict, Generator, List, Optional, Union

from nectar.account import Account
from nectar.exceptions import (
    AccountDoesNotExistsException,
    InvalidWifError,
    MissingKeyError,
    OfflineHasNoRPCException,
    WalletExists,
)
from nectar.instance import shared_blockchain_instance
from nectargraphenebase.account import PrivateKey
from nectarstorage import KeyStoreInterface
from nectarstorage.exceptions import KeyAlreadyInStoreException

log = logging.getLogger(__name__)


class Wallet:
    """The wallet is meant to maintain access to private keys for
    your accounts. It either uses manually provided private keys
    or uses a SQLite database managed by storage.py.

    :param Rpc rpc: RPC connection to a Hive node
    :param keys: Predefine the wif keys to shortcut the
           wallet database
    :type keys: array, dict, str

    Three wallet operation modes are possible:

    * **Wallet Database**: Here, nectar loads the keys from the
      locally stored wallet SQLite database (see ``storage.py``).
      To use this mode, simply call :class:`nectar.hive.Hive` without the
      ``keys`` parameter
    * **Providing Keys**: Here, you can provide the keys for
      your accounts manually. All you need to do is add the wif
      keys for the accounts you want to use as a simple array
      using the ``keys`` parameter to :class:`nectar.hive.Hive`.
    * **Force keys**: This more is for advanced users and
      requires that you know what you are doing. Here, the
      ``keys`` parameter is a dictionary that overwrite the
      ``active``, ``owner``, ``posting`` or ``memo`` keys for
      any account. This mode is only used for *foreign*
      signatures!

    A new wallet can be created by using:

    .. code-block:: python

       from nectar import Hive
       hive = Hive()
       hive.wallet.wipe(True)
       hive.wallet.create("supersecret-passphrase")

    This will raise :class:`nectar.exceptions.WalletExists` if you already have a wallet installed.


    The wallet can be unlocked for signing using

    .. code-block:: python

       from nectar import Hive
       hive = Hive()
       hive.wallet.unlock("supersecret-passphrase")

    A private key can be added by using the
    :func:`addPrivateKey` method that is available
    **after** unlocking the wallet with the correct passphrase:

    .. code-block:: python

       from nectar import Hive
       hive = Hive()
       hive.wallet.unlock("supersecret-passphrase")
       hive.wallet.addPrivateKey("5xxxxxxxxxxxxxxxxxxxx")

    .. note:: The private key has to be either in hexadecimal or in wallet
              import format (wif) (starting with a ``5``).

    """

    def __init__(
        self,
        blockchain_instance: Optional[Any] = None,
        store: Optional[KeyStoreInterface] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the Wallet, binding it to a blockchain instance and setting up the underlying key store.

        If a blockchain_instance is provided, it is used; otherwise the shared blockchain instance is used. Accepts legacy "wif" argument (aliased to "keys"). If non-empty "keys" are supplied, an in-memory plain key store is created and populated; otherwise a SQLite-encrypted key store is instantiated (can be overridden via the `key_store` kwarg).

        Parameters:
            blockchain_instance (optional): Explicit blockchain/RPC wrapper to use; if omitted the module's shared blockchain instance is used.
            store (optional): Explicit key store conforming to KeyStoreInterface.

        Side effects:
            - Creates and assigns self.store to either an in-memory, injected, or persistent key store.
            - Calls setKeys when an in-memory store is selected.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        # Compatibility after name change from wif->keys
        if "wif" in kwargs and "keys" not in kwargs:
            kwargs["keys"] = kwargs["wif"]

        self.store: Any
        if store is not None:
            self.store = store
        elif "keys" in kwargs and len(kwargs["keys"]) > 0:
            from nectarstorage import InRamPlainKeyStore

            self.store = InRamPlainKeyStore()
            self.setKeys(kwargs["keys"])
        else:
            """ If no keys are provided manually we load the SQLite
                keyStorage
            """
            from nectarstorage import SqliteEncryptedKeyStore

            self.store = kwargs.get(
                "key_store",
                SqliteEncryptedKeyStore(config=self.blockchain.config, **kwargs),
            )

    @property
    def prefix(self) -> str:
        if self.blockchain.is_connected():
            prefix = self.blockchain.prefix
        else:
            # If not connected, load prefix from config
            prefix = self.blockchain.config["prefix"]
        return prefix or "STM"  # default prefix is STM

    @property
    def rpc(self) -> Any:
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        return self.blockchain.rpc

    def setKeys(self, loadkeys: Union[Dict[str, Any], List[Any], set, str]) -> None:
        """This method is strictly only for in memory keys that are
        passed to Wallet with the ``keys`` argument
        """
        log.debug("Force setting of private keys. Not using the wallet database!")
        if isinstance(loadkeys, dict):
            loadkeys = list(loadkeys.values())
        elif not isinstance(loadkeys, (list, set)):
            loadkeys = [loadkeys]
        for wif in loadkeys:
            pub = self.publickey_from_wif(wif)
            self.store.add(str(wif), pub)

    def is_encrypted(self) -> bool:
        """Is the key store encrypted?"""
        return self.store.is_encrypted()

    def unlock(self, pwd: str) -> Optional[bool]:
        """Unlock the wallet database"""
        unlock_ok = None
        if self.store.is_encrypted():
            unlock_ok = self.store.unlock(pwd)
        return unlock_ok

    def lock(self) -> bool:
        """Lock the wallet database"""
        lock_ok = False
        if self.store.is_encrypted():
            lock_ok = self.store.lock()
        return lock_ok

    def unlocked(self) -> bool:
        """Is the wallet database unlocked?"""
        unlocked = True
        if self.store.is_encrypted():
            unlocked = not self.store.locked()
        return unlocked

    def locked(self) -> bool:
        """Is the wallet database locked?"""
        if self.store.is_encrypted():
            return self.store.locked()
        else:
            return False

    def changePassphrase(self, new_pwd: str) -> None:
        """Change the passphrase for the wallet database"""
        self.store.change_password(new_pwd)

    def created(self) -> bool:
        """Do we have a wallet database already?"""
        if len(self.store.getPublicKeys()):
            # Already keys installed
            return True
        else:
            return False

    def create(self, pwd: str) -> None:
        """Alias for :func:`newWallet`

        :param str pwd: Passphrase for the created wallet
        """
        self.newWallet(pwd)

    def newWallet(self, pwd: str) -> None:
        """Create a new wallet database

        :param str pwd: Passphrase for the created wallet
        """
        if self.created():
            raise WalletExists("You already have created a wallet!")
        self.store.unlock(pwd)

    def privatekey(self, key: str) -> PrivateKey:
        return PrivateKey(key, prefix=self.prefix)

    def publickey_from_wif(self, wif: str) -> str:
        return str(self.privatekey(str(wif)).pubkey)

    def addPrivateKey(self, wif: str) -> None:
        """Add a private key to the wallet database

        :param str wif: Private key
        """
        try:
            pub = self.publickey_from_wif(wif)
        except Exception:
            raise InvalidWifError("Invalid Key format!")
        if str(pub) in self.store:
            raise KeyAlreadyInStoreException("Key already in the store")
        self.store.add(str(wif), str(pub))

    def getPrivateKeyForPublicKey(self, pub: str) -> Optional[str]:
        """Obtain the private key for a given public key

        :param str pub: Public Key
        """
        if str(pub) not in self.store:
            raise MissingKeyError
        return self.store.getPrivateKeyForPublicKey(str(pub))

    def removePrivateKeyFromPublicKey(self, pub: str) -> None:
        """Remove a key from the wallet database

        :param str pub: Public key
        """
        self.store.delete(str(pub))

    def removeAccount(self, account: str) -> None:
        """Remove all keys associated with a given account

        :param str account: name of account to be removed
        """
        accounts = self.getAccounts()
        for a in accounts:
            if a["name"] == account:
                self.store.delete(a["pubkey"])

    def getKeyForAccount(self, name: str, key_type: str) -> Optional[str]:
        """Obtain `key_type` Private Key for an account from the wallet database

        :param str name: Account name
        :param str key_type: key type, has to be one of "owner", "active",
            "posting" or "memo"
        """
        if key_type not in ["owner", "active", "posting", "memo"]:
            raise AssertionError("Wrong key type")

        account = self.rpc.find_accounts({"accounts": [name]})["accounts"]
        if not account:
            return
        if len(account) == 0:
            return
        if key_type == "memo":
            key = self.getPrivateKeyForPublicKey(account[0]["memo_key"])
            if key:
                return key
        else:
            key = None
            for authority in account[0][key_type]["key_auths"]:
                try:
                    key = self.getPrivateKeyForPublicKey(authority[0])
                    if key:
                        return key
                except MissingKeyError:
                    key = None
            if key is None:
                raise MissingKeyError("No private key for {} found".format(name))
        return

    def getKeysForAccount(self, name: str, key_type: str) -> Optional[List[str]]:
        """Obtain a List of `key_type` Private Keys for an account from the wallet database

        :param str name: Account name
        :param str key_type: key type, has to be one of "owner", "active",
            "posting" or "memo"
        """
        if key_type not in ["owner", "active", "posting", "memo"]:
            raise AssertionError("Wrong key type")

        account = self.rpc.find_accounts({"accounts": [name]})["accounts"]
        if not account:
            return
        if len(account) == 0:
            return
        if key_type == "memo":
            key = self.getPrivateKeyForPublicKey(account[0]["memo_key"])
            if key:
                return [key]
        else:
            keys = []
            key = None
            for authority in account[0][key_type]["key_auths"]:
                try:
                    key = self.getPrivateKeyForPublicKey(authority[0])
                    if key:
                        keys.append(key)
                except MissingKeyError:
                    key = None
            if not keys:
                raise MissingKeyError("No private key for {} found".format(name))
            return keys
        return

    def getOwnerKeyForAccount(self, name: str) -> Optional[str]:
        """Obtain owner Private Key for an account from the wallet database"""
        return self.getKeyForAccount(name, "owner")

    def getMemoKeyForAccount(self, name: str) -> Optional[str]:
        """Obtain owner Memo Key for an account from the wallet database"""
        return self.getKeyForAccount(name, "memo")

    def getActiveKeyForAccount(self, name: str) -> Optional[str]:
        """Obtain owner Active Key for an account from the wallet database"""
        return self.getKeyForAccount(name, "active")

    def getPostingKeyForAccount(self, name: str) -> Optional[str]:
        """Obtain owner Posting Key for an account from the wallet database"""
        return self.getKeyForAccount(name, "posting")

    def getOwnerKeysForAccount(self, name: str) -> Optional[List[str]]:
        """Obtain list of all owner Private Keys for an account from the wallet database"""
        return self.getKeysForAccount(name, "owner")

    def getActiveKeysForAccount(self, name: str) -> Optional[List[str]]:
        """Obtain list of all owner Active Keys for an account from the wallet database"""
        return self.getKeysForAccount(name, "active")

    def getPostingKeysForAccount(self, name: str) -> Optional[List[str]]:
        """Obtain list of all owner Posting Keys for an account from the wallet database"""
        return self.getKeysForAccount(name, "posting")

    def getAccountFromPrivateKey(self, wif: str) -> Optional[str]:
        """Obtain account name from private key"""
        pub = self.publickey_from_wif(wif)
        return self.getAccountFromPublicKey(pub)

    def getAccountsFromPublicKey(self, pub: str) -> Generator[str, None, None]:
        """Obtain all account names associated with a public key

        :param str pub: Public key
        """
        if not self.blockchain.is_connected():
            raise OfflineHasNoRPCException("No RPC available in offline mode!")
        self.blockchain.rpc.set_next_node_on_empty_reply(False)
        names = self.blockchain.rpc.get_key_references({"keys": [pub]})["accounts"]
        for name in names:
            yield from name

    def getAccountFromPublicKey(self, pub: str) -> Optional[str]:
        """Obtain the first account name from public key

        :param str pub: Public key

        Note: this returns only the first account with the given key. To
        get all accounts associated with a given public key, use
        :func:`getAccountsFromPublicKey`.
        """
        names = list(self.getAccountsFromPublicKey(pub))
        if not names:
            return None
        else:
            return names[0]

    def getAllAccounts(self, pub: str) -> Generator[Dict[str, Any], None, None]:
        """Get the account data for a public key (all accounts found for this
        public key)

        :param str pub: Public key
        """
        for name in self.getAccountsFromPublicKey(pub):
            try:
                account = Account(name, blockchain_instance=self.blockchain)
            except AccountDoesNotExistsException:
                continue
            yield {
                "name": account["name"],
                "account": account,
                "type": self.getKeyType(account, pub),
                "pubkey": pub,
            }

    def getAccount(self, pub: str) -> Optional[Dict[str, Any]]:
        """Get the account data for a public key (first account found for this
        public key)

        :param str pub: Public key
        """
        name = self.getAccountFromPublicKey(pub)
        if not name:
            return {"name": None, "type": None, "pubkey": pub}
        else:
            try:
                account = Account(name, blockchain_instance=self.blockchain)
            except Exception:
                return
            return {
                "name": account["name"],
                "account": account,
                "type": self.getKeyType(account, pub),
                "pubkey": pub,
            }

    def getKeyType(self, account: Union[Account, Dict[str, Any]], pub: str) -> Optional[str]:
        """Get key type

        :param nectar.account.Account/dict account: Account data
        :type account: Account, dict
        :param str pub: Public key

        """
        for authority in ["owner", "active", "posting"]:
            for key in account[authority]["key_auths"]:
                if str(pub) == key[0]:
                    return authority
        if str(pub) == account["memo_key"]:
            return "memo"
        return None

    def getAccounts(self) -> List[Dict[str, Any]]:
        """Return all accounts installed in the wallet database"""
        pubkeys = self.getPublicKeys()
        accounts = []
        for pubkey in pubkeys:
            # Filter those keys not for our network
            if pubkey[: len(self.prefix)] == self.prefix:
                accounts.extend(self.getAllAccounts(pubkey))
        return accounts

    def getPublicKeys(self, current: bool = False) -> List[str]:
        """Return all installed public keys
        :param bool current: If true, returns only keys for currently
            connected blockchain
        """
        pubkeys = self.store.getPublicKeys()
        if not current:
            return pubkeys
        pubs = []
        for pubkey in pubkeys:
            # Filter those keys not for our network
            if pubkey[: len(self.prefix)] == self.prefix:
                pubs.append(pubkey)
        return pubs

    def wipe(self, sure: bool = False) -> None:
        if not sure:
            log.error(
                "You need to confirm that you are sure "
                "and understand the implications of "
                "wiping your wallet!"
            )
            return
        else:
            self.store.wipe()
            self.store.wipe_masterpassword()
