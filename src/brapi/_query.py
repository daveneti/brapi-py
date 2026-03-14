"""
_query.py — BaseQuery: shared fluent query-builder infrastructure.

Not generated. Entity-specific query classes (e.g. GermplasmQuery) extend
BaseQuery and add entity-specific filter methods that call _set_param().

Design:
  - Every filter method returns ``self`` for chaining.
  - No HTTP call is made until the query is materialised via .fetch() or a
    BrapiResult terminal method (.to_list() / .to_df()).
  - .as_table() switches the query to use the ZIP/CSV endpoint instead of the
    default paginated JSON endpoint.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, Union

import pandas as pd

from ._http import HttpTransport
from ._result import BrapiResult

T = TypeVar("T")

logger = logging.getLogger(__name__)


class BaseQuery(Generic[T]):
    """
    Fluent query builder base class.

    Subclasses should:
    1. Supply ``endpoint`` (JSON) and optionally ``table_endpoint`` (ZIP/CSV).
    2. Implement a ``_parse(record: dict) -> T`` classmethod or staticmethod.
    3. Add entity-specific filter methods that delegate to ``_set_param()``.

    Args:
        http: Shared ``HttpTransport`` instance.
        endpoint: Primary BrAPI endpoint (paginated JSON).
        model_cls: Pydantic model class used to parse individual records.
        http_method: ``"GET"`` or ``"POST"`` for the JSON endpoint.
        table_endpoint: Optional ZIP/CSV endpoint (e.g. ``search/germplasm/table``).
        to_df_fn: Optional callable ``(List[T]) -> pd.DataFrame`` for custom
            DataFrame conversion (e.g. to flatten nested fields).
        default_page_size: Default number of records per JSON page.
    """

    def __init__(
        self,
        http: HttpTransport,
        endpoint: str,
        model_cls: Type[T],
        http_method: str = "POST",
        table_endpoint: Optional[str] = None,
        to_df_fn: Optional[Callable[[List[T]], pd.DataFrame]] = None,
        default_page_size: int = 1000,
    ) -> None:
        self._http = http
        self._endpoint = endpoint
        self._model_cls = model_cls
        self._http_method = http_method
        self._table_endpoint = table_endpoint
        self._to_df_fn = to_df_fn
        self._default_page_size = default_page_size

        self._params: Dict[str, Any] = {}
        self._page_size: int = default_page_size
        self._max_pages: Optional[int] = None
        self._use_table: bool = False  # True → use ZIP/CSV endpoint

    # ------------------------------------------------------------------
    # Internal helpers — used by subclass filter methods
    # ------------------------------------------------------------------

    def _set_param(self, key: str, value: Any) -> "BaseQuery[T]":
        """
        Set a request parameter and return self for chaining.

        Creates a shallow copy to preserve immutability of the builder chain.
        Each filter call produces a new independent state so that the original
        query object can be reused.
        """
        clone = copy.copy(self)
        clone._params = dict(self._params)
        clone._params[key] = value
        return clone

    def _remove_param(self, key: str) -> "BaseQuery[T]":
        clone = copy.copy(self)
        clone._params = {k: v for k, v in self._params.items() if k != key}
        return clone

    @staticmethod
    def _listify(value: Union[str, List[str]]) -> List[str]:
        """Normalise a bare string or a list of strings to always return a list."""
        return [value] if isinstance(value, str) else list(value)

    # ------------------------------------------------------------------
    # Common filter methods (applicable to most BrAPI entities)
    # ------------------------------------------------------------------

    def modified_after(self, timestamp: int) -> "BaseQuery[T]":
        """
        Filter records modified after *timestamp* (Unix epoch, seconds).

        Maps to the ``modifiedAfter`` BrAPI parameter. Only applied on endpoints
        that support incremental fetch.

        Args:
            timestamp: Unix timestamp (int).  Use ``int(datetime(...).timestamp())``.
        """
        return self._set_param("modifiedAfter", timestamp)

    def page_size(self, size: int) -> "BaseQuery[T]":
        """Override the default page size for JSON pagination."""
        clone = copy.copy(self)
        clone._params = dict(self._params)
        clone._page_size = size
        return clone

    def max_pages(self, n: int) -> "BaseQuery[T]":
        """Limit the number of pages fetched (useful for testing)."""
        clone = copy.copy(self)
        clone._params = dict(self._params)
        clone._max_pages = n
        return clone

    # ------------------------------------------------------------------
    # Output format selector
    # ------------------------------------------------------------------

    def as_table(self) -> "BaseQuery[T]":
        """
        Switch to the ZIP/CSV table endpoint for this query.

        When materialised, ``fetch_zip_csv`` will be called instead of
        ``fetch_all_pages``.  The same model class is used to parse rows;
        column names from the CSV are matched to model fields by name.

        Raises:
            ValueError: If no ``table_endpoint`` was configured for this entity.
        """
        if not self._table_endpoint:
            raise ValueError(
                f"No table endpoint configured for this query "
                f"(JSON endpoint: {self._endpoint})"
            )
        clone = copy.copy(self)
        clone._params = dict(self._params)
        clone._use_table = True
        return clone

    # ------------------------------------------------------------------
    # Materialisation — returns a BrapiResult (lazy)
    # ------------------------------------------------------------------

    def fetch(self) -> BrapiResult[T]:
        """
        Build and return a lazy ``BrapiResult[T]``.

        No HTTP call is made here. The call happens when a terminal method
        (.to_list() / .to_df() / __iter__()) is invoked on the result.

        Returns:
            ``BrapiResult[T]`` wrapping this query's fetch logic.
        """
        # Capture current state so the closure is independent of future mutations
        params = dict(self._params)
        page_size = self._page_size
        max_pages = self._max_pages
        use_table = self._use_table

        if use_table:
            endpoint = self._table_endpoint
            http = self._http
            model_cls = self._model_cls
            to_df_fn = self._to_df_fn

            def _fetcher_table() -> List[T]:
                rows, metadata = http.fetch_zip_csv(endpoint=endpoint, params=params)  # type: ignore[arg-type]
                logger.debug("ZIP/CSV fetch metadata: %s", metadata)
                return [model_cls(**row) for row in rows]  # type: ignore[call-arg]

            return BrapiResult(fetcher=_fetcher_table, to_df_fn=to_df_fn)  # type: ignore[arg-type]

        # JSON pagination path
        endpoint = self._endpoint
        method = self._http_method
        http = self._http
        model_cls = self._model_cls
        to_df_fn = self._to_df_fn

        def _fetcher_json() -> List[T]:
            records = http.fetch_all_pages(
                endpoint=endpoint,
                method=method,
                params=params,
                page_size=page_size,
                max_pages=max_pages,
            )
            return [model_cls(**record) for record in records]  # type: ignore[call-arg]

        return BrapiResult(fetcher=_fetcher_json, to_df_fn=to_df_fn)  # type: ignore[arg-type]

    from typing import Generator

    def stream(self) -> Generator[List[T], None, None]:
        """
        Return a page-streaming iterator (does not buffer all pages in memory).

        Usage::

            for page in client.germplasm.filter(...).stream():
                process(page)   # page is List[T]

        Yields:
            One page (``List[T]``) at a time.

        Note: This is a regular generator — not a ``BrapiResult``.
        """
        for page_records in self._http.fetch_pages_iter(
            endpoint=self._endpoint,
            method=self._http_method,
            params=dict(self._params),
            page_size=self._page_size,
            max_pages=self._max_pages,
        ):
            yield [self._model_cls(**r) for r in page_records]  # type: ignore[call-arg]

    # ------------------------------------------------------------------
    # Debug / introspection
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        mode = "table" if self._use_table else "json"
        return (
            f"{self.__class__.__name__}("
            f"endpoint={self._endpoint!r}, mode={mode!r}, "
            f"params={self._params!r})"
        )
