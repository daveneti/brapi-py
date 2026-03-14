"""
_base_client.py — BaseBrapiClient: hand-written connection infrastructure.

This module is NEVER overwritten by the code generator.
All authentication, HTTP transport setup, and lifecycle management lives here.
The generated ``BrapiClient`` (client.py) inherits from this class and adds
the entity entry-point properties.
"""
from __future__ import annotations

from typing import Optional

import httpx

from ._auth import build_auth
from ._http import HttpTransport, DEFAULT_TIMEOUT


class BaseBrapiClient:
    """
    Base class for BrAPI v2 clients.

    Manages authentication, the HTTP transport lifecycle, and context-manager
    support.  Do not instantiate directly — use the generated ``BrapiClient``
    subclass which adds entity query entry points.

    Args:
        base_url: BrAPI server root URL (e.g. ``https://example.com``).
        token_endpoint: OAuth2 token endpoint URL.
        client_id: OAuth2 client ID (client-credentials flow).
        client_secret: OAuth2 client secret (client-credentials flow).
        username: OAuth2 username (password flow).
        password: OAuth2 password (password flow).
        api_prefix: API path prefix below ``base_url`` (default ``"brapi/v2"``).
        verify_ssl: Pass ``False`` to skip TLS verification (dev/QA environments).
        timeout: httpx Timeout. Defaults to 30 s connect / 10 min read.
    """

    def __init__(
        self,
        base_url: str,
        token_endpoint: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_prefix: str = "brapi/v2",
        verify_ssl: bool = True,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._api_prefix = api_prefix
        self._verify_ssl = verify_ssl
        self._timeout = timeout

        self._auth = build_auth(
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
        )

        # Lazily initialised transport (shared across all entity queries)
        self._transport: Optional[HttpTransport] = None

    @property
    def _http(self) -> HttpTransport:
        """Return the shared HTTP transport, creating it on first access."""
        if self._transport is None:
            self._transport = HttpTransport(
                base_url=self._base_url,
                auth=self._auth,
                api_prefix=self._api_prefix,
                verify_ssl=self._verify_ssl,
                timeout=self._timeout,
            )
        return self._transport

    def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def __enter__(self) -> "BaseBrapiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"base_url={self._base_url!r}, "
            f"api_prefix={self._api_prefix!r})"
        )
