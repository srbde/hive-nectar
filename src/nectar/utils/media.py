import io
from binascii import hexlify
from typing import Any

import httpx2
from httpx2 import ConnectError, HTTPStatusError, RequestError, TimeoutException

from nectar.account import Account
from nectar.exceptions import MissingKeyError
from nectar.instance import shared_blockchain_instance
from nectargraphenebase.ecdsasig import sign_message


class ImageUploader:
    def __init__(
        self,
        base_url: str = "https://images.hive.blog",
        challenge: str = "ImageSigningChallenge",
        blockchain_instance: Any | None = None,
    ) -> None:
        """
        Initialize the ImageUploader.

        Parameters:
            base_url (str): Base URL of the image upload service (default: "https://images.hive.blog").
            challenge (str): ASCII string prepended to the image bytes when constructing the signing message; ensures signatures are bound to this uploader's purpose.

        Notes:
            blockchain_instance is an optional blockchain client; if not provided a shared instance is used.
        """
        self.challenge = challenge
        self.base_url = base_url
        self.blockchain = blockchain_instance or shared_blockchain_instance()

    def upload(
        self,
        image: str | bytes | io.BytesIO,
        account: str | Account,
        image_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload an image to the configured image service, signing the upload with the account's posting key.

        The function accepts a filesystem path (str), raw bytes, or an io.BytesIO for the image. It locates the account's posting private key from the blockchain wallet, signs the image data together with the uploader's challenge string, and POSTs the image under the key `image_name` (defaults to "image") to: <base_url>/<account_name>/<signature_hex>.

        Parameters:
            image (str | bytes | io.BytesIO): Path to an image file, raw image bytes, or an in-memory bytes buffer.
            account (str | Account): Account identifier (must have posting permission); used to select the signing key.
            image_name (str, optional): Form field name for the uploaded image (defaults to "image").

        Returns:
            dict: Parsed JSON response from the image service.

        Raises:
            AssertionError: If the account's posting permission (and therefore a posting key) cannot be accessed.
        """
        account = Account(account, blockchain_instance=self.blockchain)
        if "posting" not in account:
            account.refresh()
        if "posting" not in account:
            raise AssertionError("Could not access posting permission")
        posting_wif = None
        for authority in account["posting"]["key_auths"]:
            try:
                posting_wif = self.blockchain.wallet.getPrivateKeyForPublicKey(authority[0])
                break
            except MissingKeyError:
                continue
        if not posting_wif:
            raise AssertionError("No local private posting key available to sign the image.")

        if isinstance(image, str):
            with open(image, "rb") as f:
                image_data = f.read()
        elif isinstance(image, io.BytesIO):
            image_data = image.read()
        else:
            image_data = image

        message = bytes(self.challenge, "ascii") + image_data
        signature = sign_message(message, posting_wif)
        signature_in_hex = hexlify(signature).decode("ascii")

        # Prepare files for httpx
        # We want to send the file with the field name "image" (expected by images.hive.blog)
        # and the filename specified by image_name.
        # If image_name is not provided, we default to "image".
        filename = image_name or "image"
        # files = {'field_name': ('filename', file_data)}
        files = {"image": (filename, image_data)}
        url = "{}/{}/{}".format(self.base_url, account["name"], signature_in_hex)

        retries = 3
        timeout = 60

        with httpx2.Client(timeout=timeout) as client:
            for i in range(retries + 1):
                try:
                    r = client.post(url, files=files)
                    r.raise_for_status()
                    return r.json()
                except (
                    ConnectError,
                    RequestError,
                    TimeoutException,
                    HTTPStatusError,
                ) as e:
                    if i < retries:
                        continue
                    raise AssertionError(f"Upload failed after {retries} retries: {str(e)}") from e

        # Should be unreachable if loop works correctly
        raise AssertionError("Upload failed")
