"""
client.py — BrapiClient: entity entry points.

THIS FILE IS GENERATED — do not edit manually.
Re-generate with PythonGenerator whenever entities are added or removed.

Hand-written infrastructure (auth, transport, lifecycle) lives in
_base_client.py (BaseBrapiClient).
"""
from __future__ import annotations

from ._base_client import BaseBrapiClient
from .entities.germplasm import GermplasmQuery


class BrapiClient(BaseBrapiClient):
    """
    Single entry-point for all BrAPI v2 queries.

    Inherits connection setup, authentication, and transport lifecycle from
    :class:`BaseBrapiClient`.  Each property below returns a fresh query object
    bound to the shared HTTP transport.

    Example::

        from brapi import BrapiClient

        client = BrapiClient(
            base_url="https://brapi.example.org",
            token_endpoint="https://brapi.example.org/token",
            client_id="svc-account",
            client_secret="...",
        )

        df = client.germplasm.by_crop(["Wheat"]).fetch().to_df()
    """

    # ------------------------------------------------------------------
    # Entity entry points
    # ------------------------------------------------------------------

    @property
    def germplasm(self) -> GermplasmQuery:
        """
        Entry point for Germplasm queries.

        Returns a fresh :class:`GermplasmQuery` bound to the shared transport.
        Filter methods are chainable and immutable — each call returns a new
        query object leaving this initial query unmodified.

        Example::

            client.germplasm.fetch().to_df()
        """
        return GermplasmQuery(http=self._http)
