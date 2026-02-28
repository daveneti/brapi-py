"""
_auth.py — OAuth2 authentication helpers.

Not generated. Supports client-credentials and resource-owner-password flows
using requests-oauth2client under the hood, but surfaces an httpx-compatible
auth object so the rest of the client can use httpx only.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class _TokenCache:
    """Simple in-memory token holder shared across requests."""

    def __init__(self) -> None:
        self._token: Optional[str] = None

    def set(self, token: str) -> None:
        self._token = token

    def get(self) -> Optional[str]:
        return self._token

    def clear(self) -> None:
        self._token = None


class OAuth2ClientCredentialsAuth(httpx.Auth):
    """
    httpx.Auth implementation for OAuth2 client-credentials flow.

    Fetches a bearer token on the first request and attaches it as an
    Authorization header. Token refresh on 401 is handled via a single retry.

    Args:
        token_endpoint: Full URL of the OAuth2 token endpoint.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret.
        verify_ssl: Whether to verify TLS certificates when fetching tokens.
    """

    def __init__(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
    ) -> None:
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = verify_ssl
        self._cache = _TokenCache()

    def _fetch_token(self) -> str:
        response = httpx.post(
            self.token_endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self._cache.set(token)
        logger.debug("Fetched new OAuth2 token (client-credentials)")
        return token

    def auth_flow(self, request: httpx.Request):
        token = self._cache.get() or self._fetch_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request

        if response.status_code == 401:
            # Token may have expired — clear cache and retry once
            self._cache.clear()
            token = self._fetch_token()
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


class OAuth2PasswordAuth(httpx.Auth):
    """
    httpx.Auth implementation for OAuth2 resource-owner-password-credentials flow.

    Args:
        token_endpoint: Full URL of the OAuth2 token endpoint.
        client_id: OAuth2 client ID.
        username: Resource-owner username.
        password: Resource-owner password.
        verify_ssl: Whether to verify TLS certificates when fetching tokens.
    """

    def __init__(
        self,
        token_endpoint: str,
        client_id: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ) -> None:
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._cache = _TokenCache()

    def _fetch_token(self) -> str:
        response = httpx.post(
            self.token_endpoint,
            data={
                "grant_type": "password",
                "client_id": self.client_id,
                "username": self.username,
                "password": self.password,
            },
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self._cache.set(token)
        logger.debug("Fetched new OAuth2 token (password-credentials)")
        return token

    def auth_flow(self, request: httpx.Request):
        token = self._cache.get() or self._fetch_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request

        if response.status_code == 401:
            self._cache.clear()
            token = self._fetch_token()
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


def build_auth(
    token_endpoint: str,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = True,
) -> httpx.Auth:
    """
    Factory that returns the appropriate httpx.Auth object.

    Exactly one of (client_id + client_secret) or (username + password) must be
    provided. Raises ValueError otherwise.
    """
    has_client = bool(client_id and client_secret)
    has_password = bool(username and password)

    if has_client and has_password:
        raise ValueError(
            "Provide either client credentials (client_id + client_secret) "
            "or user credentials (username + password), not both."
        )
    if not has_client and not has_password:
        raise ValueError(
            "Must provide client credentials (client_id + client_secret) "
            "or user credentials (username + password)."
        )

    if has_client:
        return OAuth2ClientCredentialsAuth(
            token_endpoint=token_endpoint,
            client_id=client_id,  # type: ignore[arg-type]
            client_secret=client_secret,  # type: ignore[arg-type]
            verify_ssl=verify_ssl,
        )

    return OAuth2PasswordAuth(
        token_endpoint=token_endpoint,
        client_id=client_id or "",
        username=username,  # type: ignore[arg-type]
        password=password,  # type: ignore[arg-type]
        verify_ssl=verify_ssl,
    )
