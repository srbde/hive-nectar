import json
import logging
import re
from binascii import hexlify, unhexlify
from datetime import datetime, timezone
from typing import Any

from nectar.account import Account
from nectar.exceptions import (
    AccountDoesNotExistsException,
    InvalidMemoKeyException,
    InvalidMessageSignature,
    WrongMemoKey,
)
from nectar.instance import shared_blockchain_instance
from nectargraphenebase.account import PublicKey
from nectargraphenebase.ecdsasig import sign_message, verify_message

log = logging.getLogger(__name__)


class MessageV1:
    """Allow to sign and verify Messages that are sigend with a private key"""

    MESSAGE_SPLIT = (
        "-----BEGIN HIVE SIGNED MESSAGE-----",
        "-----BEGIN META-----",
        "-----BEGIN SIGNATURE-----",
        "-----END HIVE SIGNED MESSAGE-----",
    )

    # This is the message that is actually signed
    SIGNED_MESSAGE_META = """{message}
account={meta[account]}
memokey={meta[memokey]}
block={meta[block]}
timestamp={meta[timestamp]}"""

    SIGNED_MESSAGE_ENCAPSULATED = """
{MESSAGE_SPLIT[0]}
{message}
{MESSAGE_SPLIT[1]}
account={meta[account]}
memokey={meta[memokey]}
block={meta[block]}
timestamp={meta[timestamp]}
{MESSAGE_SPLIT[2]}
{signature}
{MESSAGE_SPLIT[3]}"""

    def __init__(
        self, message: str, blockchain_instance: Any | None = None, *args: Any, **kwargs: Any
    ) -> None:
        """
        Initialize the message handler, normalize line endings, and set up signing context.

        Parameters:
            message (str): The raw message text to be signed or verified. Line endings are normalized to LF.

        Description:
            - Assigns self.blockchain to the provided blockchain_instance or to shared_blockchain_instance() when none is given.
            - Normalizes CRLF ("\r\n") to LF ("\n") and stores the result in self.message.
            - Initializes signing/verification context attributes: signed_by_account, signed_by_name, meta, and plain_message to None.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.message = message.replace("\r\n", "\n")
        self.signed_by_account = None
        self.signed_by_name = None
        self.meta = None
        self.plain_message = None

    def sign(self, account: str | Account | None = None, **kwargs: Any) -> Any:
        """Sign a message with an account's memo key
        :param str account: (optional) the account that owns the bet
            (defaults to ``default_account``)
        :raises ValueError: If not account for signing is provided
        :returns: the signed message encapsulated in a known format
        """
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")

        # Data for message
        account = Account(account, blockchain_instance=self.blockchain)
        info = self.blockchain.info()
        meta = dict(
            timestamp=info["time"],
            block=info["head_block_number"],
            memokey=account["memo_key"],
            account=account["name"],
        )

        # wif key
        wif = self.blockchain.wallet.getPrivateKeyForPublicKey(account["memo_key"])

        # We strip the message here so we know for sure there are no trailing
        # whitespaces or returns
        message = self.message.strip()

        enc_message = self.SIGNED_MESSAGE_META.format(**locals())

        # signature
        signature = hexlify(sign_message(enc_message, wif)).decode("ascii")

        self.signed_by_account = account
        self.signed_by_name = account["name"]
        self.meta = meta
        self.plain_message = message

        return self.SIGNED_MESSAGE_ENCAPSULATED.format(MESSAGE_SPLIT=self.MESSAGE_SPLIT, **locals())

    def verify(self, **kwargs: Any) -> bool:
        """Verify a message with an account's memo key
        :param str account: (optional) the account that owns the bet
            (defaults to ``default_account``)
        :returns: True if the message is verified successfully
        :raises InvalidMessageSignature if the signature is not ok
        """
        # Split message into its parts
        parts = re.split("|".join(self.MESSAGE_SPLIT), self.message)
        parts = [x for x in parts if x.strip()]

        assert len(parts) > 2, "Incorrect number of message parts"

        # Strip away all whitespaces before and after the message
        message = parts[0].strip()
        signature = parts[2].strip()
        # Parse the meta data
        meta = dict(re.findall(r"(\S+)=(.*)", parts[1]))

        log.info(f"Message is: {message}")
        log.info(f"Meta is: {json.dumps(meta)}")
        log.info(f"Signature is: {signature}")

        # Ensure we have all the data in meta
        assert "account" in meta, "No 'account' could be found in meta data"
        assert "memokey" in meta, "No 'memokey' could be found in meta data"
        assert "block" in meta, "No 'block' could be found in meta data"
        assert "timestamp" in meta, "No 'timestamp' could be found in meta data"

        account_name = meta.get("account", "").strip()
        memo_key = meta.get("memokey", "").strip()

        try:
            PublicKey(memo_key, prefix=self.blockchain.prefix)
        except Exception:
            raise InvalidMemoKeyException("The memo key in the message is invalid")

        # Load account from blockchain
        try:
            account = Account(account_name, blockchain_instance=self.blockchain)
        except AccountDoesNotExistsException:
            raise AccountDoesNotExistsException(
                "Could not find account {}. Are you connected to the right chain?".format(
                    account_name
                )
            )

        # Test if memo key is the same as on the blockchain
        if not account["memo_key"] == memo_key:
            raise WrongMemoKey(
                "Memo Key of account {} on the Blockchain ".format(account["name"])
                + "differs from memo key in the message: {} != {}".format(
                    account["memo_key"], memo_key
                )
            )

        # Reformat message
        enc_message = self.SIGNED_MESSAGE_META.format(**locals())

        # Verify Signature
        pubkey = verify_message(enc_message, unhexlify(signature))
        if pubkey is None:
            raise InvalidMessageSignature("No public key recovered from signature")

        # Verify pubky
        pk = PublicKey(hexlify(pubkey).decode("ascii"), prefix=self.blockchain.prefix)
        if format(pk, self.blockchain.prefix) != memo_key:
            raise InvalidMessageSignature("The signature doesn't match the memo key")

        self.signed_by_account = account
        self.signed_by_name = account["name"]
        self.meta = meta
        self.plain_message = message

        return True


class MessageV2:
    """Allow to sign and verify Messages that are sigend with a private key"""

    def __init__(
        self, message: str, blockchain_instance: Any | None = None, *args: Any, **kwargs: Any
    ) -> None:
        """
        Initialize the message handler and set up default signing context.

        Parameters:
            message (str): The raw message text to be signed or verified.

        Description:
            Stores the provided message and sets up the signing context attributes
            (signed_by_account, signed_by_name, meta, plain_message) to None.
            If no blockchain instance is supplied, assigns a shared blockchain instance
            via shared_blockchain_instance().
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()

        self.message = message
        self.signed_by_account = None
        self.signed_by_name = None
        self.meta = None
        self.plain_message = None

    def sign(self, account: str | Account | None = None, **kwargs: Any) -> Any:
        """Sign a message with an account's memo key
        :param str account: (optional) the account that owns the bet
            (defaults to ``default_account``)
        :raises ValueError: If not account for signing is provided
        :returns: the signed message encapsulated in a known format
        """
        if not account:
            if "default_account" in self.blockchain.config:
                account = self.blockchain.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")

        # Data for message
        account = Account(account, blockchain_instance=self.blockchain)

        # wif key
        wif = self.blockchain.wallet.getPrivateKeyForPublicKey(account["memo_key"])

        payload = [
            "from",
            account["name"],
            "key",
            account["memo_key"],
            "time",
            str(datetime.now(timezone.utc)),
            "text",
            self.message,
        ]
        enc_message = json.dumps(payload, separators=(",", ":"))

        # signature
        signature = hexlify(sign_message(enc_message, wif)).decode("ascii")

        return dict(signed=enc_message, payload=payload, signature=signature)

    def verify(self, **kwargs: Any) -> bool:
        """Verify a message with an account's memo key
        :param str account: (optional) the account that owns the bet
            (defaults to ``default_account``)
        :returns: True if the message is verified successfully
        :raises InvalidMessageSignature if the signature is not ok
        """
        if not isinstance(self.message, dict):
            try:
                self.message = json.loads(self.message)
            except Exception:
                raise ValueError("Message must be valid JSON")

        payload = self.message.get("payload")
        assert payload, "Missing payload"
        payload_dict = {k[0]: k[1] for k in zip(payload[::2], payload[1::2])}
        signature = self.message.get("signature")

        account_name = payload_dict.get("from", "").strip()
        memo_key = payload_dict.get("key", "").strip()

        assert account_name, "Missing account name 'from'"
        assert memo_key, "missing 'key'"

        try:
            # Validate that the memo key is a syntactically valid public key
            PublicKey(memo_key, prefix=self.blockchain.prefix)
        except Exception:
            raise InvalidMemoKeyException("The memo key in the message is invalid")

        # Load account from blockchain
        try:
            account = Account(account_name, blockchain_instance=self.blockchain)
        except AccountDoesNotExistsException:
            raise AccountDoesNotExistsException(
                "Could not find account {}. Are you connected to the right chain?".format(
                    account_name
                )
            )

        # Test if memo key is the same as on the blockchain
        if not account["memo_key"] == memo_key:
            raise WrongMemoKey(
                "Memo Key of account {} on the Blockchain ".format(account["name"])
                + "differs from memo key in the message: {} != {}".format(
                    account["memo_key"], memo_key
                )
            )

        # Ensure payload and signed match
        signed_target = json.dumps(self.message.get("payload"), separators=(",", ":"))
        signed_actual = self.message.get("signed")
        assert signed_target == signed_actual, (
            f"payload doesn't match signed message: \n{signed_target}\n{signed_actual}"
        )

        # Reformat message
        enc_message = self.message.get("signed")

        # Verify Signature
        pubkey = verify_message(enc_message, unhexlify(signature))

        # Verify pubky
        if pubkey is None:
            raise InvalidMessageSignature("No public key recovered from signature")
        pk = PublicKey(hexlify(pubkey).decode("ascii"), prefix=self.blockchain.prefix)
        if format(pk, self.blockchain.prefix) != memo_key:
            raise InvalidMessageSignature("The signature doesn't match the memo key")

        self.signed_by_account = account
        self.signed_by_name = account["name"]
        self.plain_message = payload_dict.get("text")

        return True


class Message(MessageV1, MessageV2):
    supported_formats = (MessageV1, MessageV2)
    valid_exceptions = (
        AccountDoesNotExistsException,
        InvalidMessageSignature,
        WrongMemoKey,
        InvalidMemoKeyException,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for _format in self.supported_formats:
            try:
                _format.__init__(self, *args, **kwargs)
                return
            except self.valid_exceptions as e:
                raise e
            except Exception as e:
                log.warning(f"{_format.__name__}: Couldn't init: {e.__class__.__name__}: {e}")

    def verify(self, **kwargs: Any) -> bool:
        for _format in self.supported_formats:
            try:
                return _format.verify(self, **kwargs)
            except self.valid_exceptions as e:
                raise e
            except Exception as e:
                log.warning(f"{_format.__name__}: Couldn't verify: {e.__class__.__name__}: {e}")
        raise ValueError("No Decoder accepted the message")

    def sign(self, account: str | Account | None = None, **kwargs: Any) -> Any:
        for _format in self.supported_formats:
            try:
                return _format.sign(self, account=account, **kwargs)
            except self.valid_exceptions as e:
                raise e
            except Exception as e:
                log.warning(f"{_format.__name__}: Couldn't sign: {e.__class__.__name__}: {e}")
        raise ValueError("No Decoder accepted the message")
