import json
import logging
from typing import Any, Dict, Optional

import httpx2

from nectar.instance import shared_blockchain_instance

log = logging.getLogger(__name__)


class HAF:
    """Hive Account Feed (HAF) API client for accessing Hive blockchain endpoints.

    This class provides access to various Hive API endpoints that are not part of the
    standard RPC blockchain calls. It supports multiple API providers and handles
    reputation queries and other HAF-related data.

    :param str api: Base API URL to use for requests. Supported endpoints include:
        - 'https://api.hive.blog' (default)
        - 'https://api.syncad.com'
    :param blockchain_instance: Blockchain instance for compatibility with the nectar ecosystem

    .. code-block:: python

        >>> from nectar.haf import HAF
        >>> haf = HAF()  # doctest: +SKIP
        >>> reputation = haf.reputation("thecrazygm")  # doctest: +SKIP
        >>> print(reputation)  # doctest: +SKIP

    """

    DEFAULT_APIS = ["https://api.hive.blog", "https://api.syncad.com"]

    def __init__(
        self, api: Optional[str] = None, blockchain_instance=None, timeout: Optional[float] = None
    ):
        """
        Initialize the HAF client.

        Parameters:
            api (str, optional): Base API URL. If None, uses the first available default API.
            blockchain_instance: Blockchain instance for ecosystem compatibility.
            timeout (float, optional): Timeout for requests in seconds.
        """
        self.api = api or self.DEFAULT_APIS[0]
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self._timeout = float(timeout) if timeout else 30.0

        # Validate API URL
        if not self.api.startswith(("http://", "https://")):
            raise ValueError(f"Invalid API URL: {self.api}. Must start with http:// or https://")

        # Remove trailing slash if present
        self.api = self.api.rstrip("/")

        log.debug(f"Initialized HAF client with API: {self.api}")

    def _make_request(self, endpoint: str, method: str = "GET", **kwargs) -> Any:
        """
        Make an HTTP request to the HAF API.

        Parameters:
            endpoint (str): API endpoint path (without leading slash)
            method (str): HTTP method (default: 'GET')
            **kwargs: Additional arguments passed to requests

        Returns:
            dict: JSON response from the API

        Raises:
            httpx.RequestError: If the request fails
            ValueError: If the response is not valid JSON
        """
        url = f"{self.api}/{endpoint}"

        # Set default headers
        headers = kwargs.pop("headers", {})
        headers.setdefault("accept", "application/json")
        from nectar.version import version as nectar_version

        headers.setdefault("User-Agent", f"hive-nectar/{nectar_version}")

        log.debug(f"Making {method} request to: {url}")

        try:
            timeout = kwargs.pop("timeout", self._timeout)
            with httpx2.Client(timeout=timeout) as client:
                response = client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()

        except httpx2.RequestError as e:
            log.error(f"Request failed for {url}: {e}")
            raise
        except (httpx2.HTTPStatusError, json.JSONDecodeError) as e:
            log.error(f"Invalid response from {url}: {e}")
            raise ValueError(f"Invalid response from API: {e}")

    def reputation(self, account: str) -> Optional[Dict[str, Any]]:
        """
        Get reputation information for a Hive account.

        This method queries the reputation API endpoint to retrieve the account's
        reputation score and related metadata.

        Parameters:
            account (str): Hive account name

        Returns:
            dict or None: Reputation data containing account information and reputation score,
                         or None if the request fails or account is not found

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> rep = haf.reputation("thecrazygm")  # doctest: +SKIP
            >>> print(rep)  # doctest: +SKIP
            {'account': 'thecrazygm', 'reputation': '71', ...}

        """
        if not account or not isinstance(account, str):
            raise ValueError("Account name must be a non-empty string")

        try:
            endpoint = f"reputation-api/accounts/{account}/reputation"
            response = self._make_request(endpoint)

            log.debug(f"Retrieved reputation for account: {account}")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve reputation for account {account}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving reputation for {account}: {e}")
            return None

    def get_available_apis(self) -> list[str]:
        """
        Get the list of available API endpoints.

        Returns:
            list: List of supported API URLs
        """
        return self.DEFAULT_APIS.copy()

    def set_api(self, api: str) -> None:
        """
        Change the API endpoint.

        Parameters:
            api (str): New API URL to use

        Raises:
            ValueError: If the API URL is invalid
        """
        if api not in self.DEFAULT_APIS:
            log.warning(f"Using non-default API: {api}")

        # Validate URL
        if not api.startswith(("http://", "https://")):
            raise ValueError(f"Invalid API URL: {api}. Must start with http:// or https://")

        self.api = api.rstrip("/")
        log.info(f"Switched to API: {self.api}")

    def get_current_api(self) -> str:
        """
        Get the currently active API endpoint.

        Returns:
            str: Current API URL
        """
        return self.api

    def get_account_balances(self, account: str) -> Optional[Dict[str, Any]]:
        """
        Get account balances from the balance API.

        This method retrieves comprehensive balance information including HBD, HIVE,
        vesting shares, rewards, and other balance-related data for an account.

        Parameters:
            account (str): Hive account name

        Returns:
            dict or None: Account balance data or None if request fails

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> balances = haf.get_account_balances("thecrazygm")  # doctest: +SKIP
            >>> print(balances['hive_balance'])  # doctest: +SKIP
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account name must be a non-empty string")

        try:
            endpoint = f"balance-api/accounts/{account}/balances"
            response = self._make_request(endpoint)

            log.debug(f"Retrieved balances for account: {account}")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve balances for account {account}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving balances for {account}: {e}")
            return None

    def get_account_delegations(self, account: str) -> Optional[Dict[str, Any]]:
        """
        Get account delegations from the balance API.

        This method retrieves both incoming and outgoing delegations for an account.

        Parameters:
            account (str): Hive account name

        Returns:
            dict or None: Delegation data containing incoming and outgoing delegations

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> delegations = haf.get_account_delegations("thecrazygm")  # doctest: +SKIP
            >>> print(delegations['incoming_delegations'])  # doctest: +SKIP
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account name must be a non-empty string")

        try:
            endpoint = f"balance-api/accounts/{account}/delegations"
            response = self._make_request(endpoint)

            log.debug(f"Retrieved delegations for account: {account}")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve delegations for account {account}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving delegations for {account}: {e}")
            return None

    def get_account_recurrent_transfers(self, account: str) -> Optional[Dict[str, Any]]:
        """
        Get account recurrent transfers from the balance API.

        This method retrieves both incoming and outgoing recurrent transfers for an account.

        Parameters:
            account (str): Hive account name

        Returns:
            dict or None: Recurrent transfer data containing incoming and outgoing transfers

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> transfers = haf.get_account_recurrent_transfers("thecrazygm")  # doctest: +SKIP
            >>> print(transfers['outgoing_recurrent_transfers'])  # doctest: +SKIP
        """
        if not account or not isinstance(account, str):
            raise ValueError("Account name must be a non-empty string")

        try:
            endpoint = f"balance-api/accounts/{account}/recurrent-transfers"
            response = self._make_request(endpoint)

            log.debug(f"Retrieved recurrent transfers for account: {account}")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve recurrent transfers for account {account}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving recurrent transfers for {account}: {e}")
            return None

    def get_reputation_version(self) -> Optional[str]:
        """
        Get the reputation tracker's version from the reputation API.

        Returns:
            str or None: Version string or None if request fails

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> version = haf.get_reputation_version()  # doctest: +SKIP
            >>> print(version)  # doctest: +SKIP
        """
        try:
            endpoint = "reputation-api/version"
            response = self._make_request(endpoint)

            log.debug("Retrieved reputation tracker version")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve reputation version: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving reputation version: {e}")
            return None

    def get_reputation_last_synced_block(self) -> Optional[int]:
        """
        Get the last block number synced by the reputation tracker.

        Returns:
            int or None: Last synced block number or None if request fails

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> block = haf.get_reputation_last_synced_block()  # doctest: +SKIP
            >>> print(block)  # doctest: +SKIP
        """
        try:
            endpoint = "reputation-api/last-synced-block"
            response = self._make_request(endpoint)

            log.debug("Retrieved last synced block for reputation tracker")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve last synced block: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving last synced block: {e}")
            return None

    def get_balance_version(self) -> Optional[str]:
        """
        Get the balance tracker's version from the balance API.

        Returns:
            str or None: Version string or None if request fails

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> version = haf.get_balance_version()  # doctest: +SKIP
            >>> print(version)  # doctest: +SKIP
        """
        try:
            endpoint = "balance-api/version"
            response = self._make_request(endpoint)

            log.debug("Retrieved balance tracker version")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve balance version: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving balance version: {e}")
            return None

    def get_balance_last_synced_block(self) -> Optional[int]:
        """
        Get the last block number synced by the balance tracker.

        Returns:
            int or None: Last synced block number or None if request fails

        Example:
            >>> haf = HAF()  # doctest: +SKIP
            >>> block = haf.get_balance_last_synced_block()  # doctest: +SKIP
            >>> print(block)  # doctest: +SKIP
        """
        try:
            endpoint = "balance-api/last-synced-block"
            response = self._make_request(endpoint)

            log.debug("Retrieved last synced block for balance tracker")
            return response

        except httpx2.RequestError as e:
            log.warning(f"Failed to retrieve last synced block: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error retrieving last synced block: {e}")
            return None
