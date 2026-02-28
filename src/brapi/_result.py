"""
_result.py — BrapiResult: lazy, pipeable result container.

Not generated. This is the return type of every .fetch() call.
It wraps a callable that produces data, and exposes:
  - .fetch()     → executes the callable (idempotent)
  - .to_list()   → List[T]
  - .to_df()     → pd.DataFrame
  - .pipe(fn)    → BrapiResult[R]  (lazy transform)
"""
from __future__ import annotations

from typing import Any, Callable, Generic, Iterator, List, Optional, TypeVar

import pandas as pd

T = TypeVar("T")
R = TypeVar("R")


class BrapiResult(Generic[T]):
    """
    Lazy, pipeable container for BrAPI entity results.

    The underlying HTTP call is not made until a terminal method is invoked.
    Terminal methods: .fetch(), .to_list(), .to_df(), __iter__().

    Examples::

        result = client.germplasm.filter(commonCropNames=["Soybean"]).fetch()

        # Terminal: materialise as list
        items: list[Germplasm] = result.to_list()

        # Terminal: materialise as DataFrame
        df: pd.DataFrame = result.to_df()

        # Non-terminal: attach a transform (lazy)
        result2 = result.pipe(lambda items: [g for g in items if g.genus == "Glycine"])

        # Chained pipeline — only one HTTP call is made at the end
        df = (
            client.germplasm
            .filter(genus=["Glycine"])
            .fetch()
            .pipe(my_filter)
            .pipe(my_enrich)
            .to_df()
        )
    """

    def __init__(
        self,
        fetcher: Callable[[], List[T]],
        to_df_fn: Optional[Callable[[List[T]], pd.DataFrame]] = None,
    ) -> None:
        """
        Args:
            fetcher: Zero-argument callable that performs the HTTP fetch and returns
                a list of entity objects. Called at most once (result is cached).
            to_df_fn: Optional callable that converts List[T] → DataFrame.
                If None, a default ``pd.DataFrame([vars(x) for x in items])``
                is used, which works for flat Pydantic models.
        """
        self._fetcher = fetcher
        self._to_df_fn = to_df_fn
        self._data: Optional[List[T]] = None
        # Chain of post-fetch transforms: each is List[Any] → List[Any]
        self._transforms: List[Callable[[List[Any]], List[Any]]] = []

    # ------------------------------------------------------------------
    # Non-terminal (builder) methods
    # ------------------------------------------------------------------

    def pipe(self, fn: Callable[[List[T]], List[R]], *args: Any, **kwargs: Any) -> "BrapiResult[R]":
        """
        Attach a lazy transform to the pipeline.

        The transform receives the full list of entity objects and must return a
        list (which may be a different type). The transform is not executed until a
        terminal method is called.

        Args:
            fn: A callable ``(List[T], *args, **kwargs) -> List[R]``.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            A new ``BrapiResult[R]`` sharing the same underlying fetcher.

        Example::

            result.pipe(lambda items: [i for i in items if i.genus == "Glycine"])
            result.pipe(enrich, lookup_table=my_table)
        """
        child: BrapiResult[R] = BrapiResult(  # type: ignore[assignment]
            fetcher=self._fetcher,
            to_df_fn=None,
        )
        child._transforms = self._transforms + [lambda data: fn(data, *args, **kwargs)]
        return child

    # ------------------------------------------------------------------
    # Terminal methods
    # ------------------------------------------------------------------

    def fetch(self) -> "BrapiResult[T]":
        """
        Execute the HTTP call (if not already done) and cache the raw result.

        Calling this multiple times is safe — the HTTP call is only made once.

        Returns:
            self — allows chaining terminal operations.
        """
        if self._data is None:
            self._data = self._fetcher()
        return self

    def to_list(self) -> List[T]:
        """
        Return results as a Python list, executing the fetch if necessary.

        Returns:
            List of entity objects (e.g. ``List[Germplasm]``).
        """
        self.fetch()
        data: List[Any] = list(self._data)  # type: ignore[arg-type]
        for transform in self._transforms:
            data = transform(data)
        return data  # type: ignore[return-value]

    def to_df(self) -> pd.DataFrame:
        """
        Return results as a pandas DataFrame, executing the fetch if necessary.

        If a custom ``to_df_fn`` was supplied at construction time (e.g. by an
        entity-specific flattening function) it is called on the final list.
        Otherwise a default conversion from model dicts is used.

        Returns:
            ``pd.DataFrame`` with one row per entity.
        """
        items = self.to_list()
        if not items:
            return pd.DataFrame()

        if self._to_df_fn is not None:
            return self._to_df_fn(items)  # type: ignore[arg-type]

        # Default: use Pydantic model_dump if available, else vars()
        try:
            rows = [item.model_dump() for item in items]  # type: ignore[union-attr]
        except AttributeError:
            rows = [vars(item) for item in items]

        return pd.DataFrame(rows)

    def __iter__(self) -> Iterator[T]:
        """Iterate over results, triggering fetch if needed."""
        yield from self.to_list()

    def __len__(self) -> int:
        """Return the number of results, triggering fetch if needed."""
        return len(self.to_list())

    def __repr__(self) -> str:
        status = f"{len(self._data)} items fetched" if self._data is not None else "not yet fetched"
        return f"BrapiResult<{status}>"
