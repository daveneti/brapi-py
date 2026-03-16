"""
_http.py — Low-level HTTP transport for BrAPI endpoints.

Not generated. Handles:
  - Paginated JSON (GET and POST, BrAPI envelope: result.data + metadata.pagination)
  - Direct CSV table downloads (GET /<entity>/table → CSV text via fetch_csv_table)
  - ZIP/CSV search-table downloads (POST search/<entity>/table → presigned URL → ZIP → CSV via fetch_zip_csv)

All methods are synchronous. Async support can be layered here later using httpx's
async client without changing the query/result surface.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import time
import zipfile
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Default timeout: 30 s connect, 10 min read (ZIP endpoints can be very slow)
DEFAULT_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=10.0)


class HttpTransport:
    """
    Thin synchronous HTTP wrapper used by all query builders.

    Args:
        base_url: BrAPI server root (e.g. ``https://phenomeone-qa.basf.net``).
        auth: An ``httpx.Auth`` instance (see ``_auth.py``).
        api_prefix: API path prefix (default ``brapi/v2``).
        verify_ssl: Whether to verify TLS. Set ``False`` for self-signed certs.
        timeout: httpx Timeout object. Defaults to 30 s connect / 10 min read.
    """

    def __init__(
        self,
        base_url: str,
        auth: httpx.Auth,
        api_prefix: str = "brapi/v2",
        verify_ssl: bool = True,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.strip("/")
        self._client = httpx.Client(
            auth=auth,
            verify=verify_ssl,
            timeout=timeout,
        )

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/{self.api_prefix}/{endpoint.lstrip('/')}"

    # ------------------------------------------------------------------
    # Paginated JSON
    # ------------------------------------------------------------------

    def fetch_page(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        page: int = 0,
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """
        Fetch a single page from a paginated BrAPI JSON endpoint.

        Args:
            endpoint: BrAPI endpoint path (e.g. ``search/germplasm``).
            method: ``"GET"`` or ``"POST"``.
            params: Query parameters (GET) or request body (POST).
            page: Zero-based page index.
            page_size: Number of records per page.

        Returns:
            Full BrAPI response envelope as a dict.
        """
        request_params = dict(params or {})
        request_params["page"] = page
        request_params["pageSize"] = page_size

        url = self._url(endpoint)
        if method.upper() == "POST":
            response = self._client.post(url, json=request_params)
        else:
            response = self._client.get(url, params=request_params)

        response.raise_for_status()
        return response.json()

    def fetch_all_pages(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 1000,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages of a paginated BrAPI JSON endpoint and return flat list.

        Args:
            endpoint: BrAPI endpoint path.
            method: ``"GET"`` or ``"POST"``.
            params: Query parameters / POST body (excluding pagination keys).
            page_size: Number of records per page.
            max_pages: If set, stop after this many pages.

        Returns:
            Flat list of record dicts from ``result.data``.
        """
        records: List[Dict[str, Any]] = []
        page = 0

        while True:
            response = self.fetch_page(
                endpoint=endpoint,
                method=method,
                params=params,
                page=page,
                page_size=page_size,
            )

            data = response.get("result", {}).get("data", [])
            records.extend(data)

            pagination = response.get("metadata", {}).get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            current_page = pagination.get("currentPage", page)

            logger.debug(
                "Fetched page %d/%d from %s (%d records this page)",
                current_page + 1,
                total_pages,
                endpoint,
                len(data),
            )

            page += 1
            if page >= total_pages:
                break
            if max_pages is not None and page >= max_pages:
                logger.info("Stopping at max_pages=%d for %s", max_pages, endpoint)
                break

        logger.info("Fetched %d total records from %s", len(records), endpoint)
        return records

    def fetch_pages_iter(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 1000,
        max_pages: Optional[int] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Streaming page-by-page iterator. Yields one page (list of records) at a time.

        Useful for very large datasets where you don't want to hold everything in memory.
        """
        page = 0
        while True:
            response = self.fetch_page(
                endpoint=endpoint,
                method=method,
                params=params,
                page=page,
                page_size=page_size,
            )
            data = response.get("result", {}).get("data", [])
            yield data

            pagination = response.get("metadata", {}).get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            page += 1
            if page >= total_pages:
                break
            if max_pages is not None and page >= max_pages:
                break

    def fetch_all_search_pages(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 1000,
        max_pages: Optional[int] = None,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        POST to a BrAPI search endpoint and return all matching records,
        handling both synchronous (200) and asynchronous (202) response patterns.

        BrAPI search endpoints may:

        * Return **200** with ``result.data`` immediately.  Additional pages are
          fetched by repeating the POST with incrementing ``page`` values.
        * Return **202** (Accepted) with a ``searchResultsDbId`` string in
          ``result``.  Results are retrieved by polling
          ``GET /{endpoint}/{searchResultsDbId}`` until a 200 is received;
          subsequent pages are fetched via GET on the same URL.

        Args:
            endpoint: BrAPI search endpoint path (e.g. ``search/germplasm``).
            params: POST body parameters (excluding ``page``/``pageSize``).
            page_size: Number of records per page.
            max_pages: If set, stop after this many pages.
            poll_interval: Seconds to wait between 202 retry attempts.
            max_poll_attempts: Maximum polling retries before raising
                ``TimeoutError``.

        Returns:
            Flat list of record dicts from ``result.data``.

        Raises:
            ValueError: If a 202 response contains no ``searchResultsDbId``.
            TimeoutError: If polling exceeds ``max_poll_attempts``.
        """
        request_body = dict(params or {})
        request_body["page"] = 0
        request_body["pageSize"] = page_size

        url = self._url(endpoint)
        response = self._client.post(url, json=request_body)
        response.raise_for_status()

        if response.status_code == 202:
            # Async path — server accepted the search, poll for results.
            search_id = response.json().get("result")
            if not search_id or not isinstance(search_id, str):
                raise ValueError(
                    f"202 response from {endpoint} contained no searchResultsDbId "
                    f"in 'result'. Body: {response.text[:200]}"
                )
            logger.info(
                "Search %s returned 202; polling /%s/%s (max %d attempts, %.1fs interval)",
                endpoint,
                endpoint,
                search_id,
                max_poll_attempts,
                poll_interval,
            )
            poll_endpoint = f"{endpoint}/{search_id}"
            poll_url = self._url(poll_endpoint)
            first_response: Optional[Dict[str, Any]] = None
            for attempt in range(1, max_poll_attempts + 1):
                time.sleep(poll_interval)
                poll_resp = self._client.get(
                    poll_url, params={"page": 0, "pageSize": page_size}
                )
                if poll_resp.status_code == 200:
                    first_response = poll_resp.json()
                    logger.info(
                        "Search %s ready after %d poll attempt(s)",
                        endpoint,
                        attempt,
                    )
                    break
                elif poll_resp.status_code == 202:
                    logger.debug(
                        "Poll attempt %d/%d: still processing", attempt, max_poll_attempts
                    )
                    continue
                else:
                    poll_resp.raise_for_status()
            if first_response is None:
                raise TimeoutError(
                    f"Search {endpoint}/{search_id} did not complete after "
                    f"{max_poll_attempts} attempts "
                    f"({max_poll_attempts * poll_interval:.0f} s)"
                )
            return self._collect_get_pages(
                first_response, poll_endpoint, page_size, max_pages
            )

        # Synchronous 200 path — immediate results in result.data.
        first_response = response.json()
        # Some servers return 200 + a searchResultsDbId string even synchronously.
        result = first_response.get("result", {})
        if isinstance(result, str):
            poll_endpoint = f"{endpoint}/{result}"
            return self._collect_get_pages(first_response, poll_endpoint, page_size, max_pages)

        return self._collect_post_pages(
            first_response, endpoint, params or {}, page_size, max_pages
        )

    # ------------------------------------------------------------------
    # Private pagination helpers
    # ------------------------------------------------------------------

    def _collect_get_pages(
        self,
        first_response: Dict[str, Any],
        endpoint: str,
        page_size: int,
        max_pages: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Collect all pages via GET, using an already-fetched first-page response."""
        records: List[Dict[str, Any]] = []
        data = first_response.get("result", {}).get("data", [])
        records.extend(data)
        pagination = first_response.get("metadata", {}).get("pagination", {})
        total_pages = pagination.get("totalPages", 1)
        logger.debug("GET %s: page 1/%d (%d records)", endpoint, total_pages, len(data))

        for page in range(1, total_pages):
            if max_pages is not None and page >= max_pages:
                logger.info("Stopping at max_pages=%d for %s", max_pages, endpoint)
                break
            resp = self._client.get(
                self._url(endpoint), params={"page": page, "pageSize": page_size}
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("data", [])
            records.extend(data)
            logger.debug(
                "GET %s: page %d/%d (%d records)", endpoint, page + 1, total_pages, len(data)
            )

        logger.info("Fetched %d total records from GET %s", len(records), endpoint)
        return records

    def _collect_post_pages(
        self,
        first_response: Dict[str, Any],
        endpoint: str,
        params: Dict[str, Any],
        page_size: int,
        max_pages: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Collect all pages via POST, using an already-fetched first-page response."""
        records: List[Dict[str, Any]] = []
        data = first_response.get("result", {}).get("data", [])
        records.extend(data)
        pagination = first_response.get("metadata", {}).get("pagination", {})
        total_pages = pagination.get("totalPages", 1)
        logger.debug("POST %s: page 1/%d (%d records)", endpoint, total_pages, len(data))

        for page in range(1, total_pages):
            if max_pages is not None and page >= max_pages:
                logger.info("Stopping at max_pages=%d for %s", max_pages, endpoint)
                break
            body = dict(params)
            body["page"] = page
            body["pageSize"] = page_size
            resp = self._client.post(self._url(endpoint), json=body)
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("data", [])
            records.extend(data)
            logger.debug(
                "POST %s: page %d/%d (%d records)", endpoint, page + 1, total_pages, len(data)
            )

        logger.info("Fetched %d total records from POST %s", len(records), endpoint)
        return records

    # ------------------------------------------------------------------
    # ZIP / CSV table endpoints
    # ------------------------------------------------------------------

    def fetch_csv_table(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        GET a BrAPI ``/<entity>/table`` endpoint with ``Accept: text/csv`` and
        return parsed rows.

        The server returns CSV text directly in the response body.

        Args:
            endpoint: BrAPI endpoint path (e.g. ``observations/table``).
            params:   Query parameters.

        Returns:
            Tuple of:
              - ``rows``: List of dicts (one per CSV row, column names as-is).
              - ``metadata``: Dict with ``row_count``.

        Raises:
            httpx.HTTPStatusError: On HTTP errors.
        """
        url = self._url(endpoint)
        logger.info("GET %s to fetch CSV table", endpoint)
        response = self._client.get(
            url, params=params or {}, headers={"Accept": "text/csv"}
        )
        response.raise_for_status()

        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        logger.info("Fetched %d rows from CSV table %s", len(rows), endpoint)
        return rows, {"row_count": len(rows)}

    def fetch_zip_csv(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        POST to a BrAPI ``/table`` endpoint, download the returned ZIP, extract
        the CSV, and return parsed rows.

        The server is expected to respond with a presigned download URL in
        ``result`` (string). The ZIP contains exactly one CSV file.

        Args:
            endpoint: BrAPI endpoint path (e.g. ``search/germplasm/table``).
            params: POST body parameters.

        Returns:
            Tuple of:
              - ``rows``: List of dicts (one per CSV row, column names un-sanitised).
              - ``metadata``: Dict with ``zip_url``, ``csv_filename``, ``row_count``,
                ``download_duration_ms``, ``extraction_duration_ms``, ``zip_file_size``.

        Raises:
            ValueError: If no download URL or no CSV in archive.
            zipfile.BadZipFile: If downloaded content is not a valid ZIP.
            httpx.HTTPStatusError: On HTTP errors.
        """
        url = self._url(endpoint)
        request_params = dict(params or {})

        logger.info("POSTing to %s to request ZIP/CSV table", endpoint)
        response = self._client.post(url, json=request_params)
        response.raise_for_status()
        response_json = response.json()

        zip_url: Optional[str] = response_json.get("result")
        if not zip_url:
            raise ValueError(
                f"No download URL in 'result' field from {endpoint}. "
                f"Response keys: {list(response_json.keys())}"
            )

        logger.info("Downloading ZIP from %s", zip_url)
        download_start = time.time()

        # Download using a plain httpx GET (no auth — presigned URL is self-contained)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            zip_response = httpx.get(zip_url)
            zip_response.raise_for_status()
            tmp.write(zip_response.content)
            tmp_path = tmp.name

        zip_size = os.path.getsize(tmp_path)
        download_ms = int((time.time() - download_start) * 1000)
        logger.info("Downloaded ZIP (%d bytes) in %d ms", zip_size, download_ms)

        # Extract CSV
        extract_start = time.time()
        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
                if not csv_files:
                    raise ValueError(f"No CSV file found in ZIP. Files: {zf.namelist()}")
                csv_filename = csv_files[0]
                csv_bytes = zf.read(csv_filename)
        except zipfile.BadZipFile as exc:
            os.remove(tmp_path)
            raise zipfile.BadZipFile(f"Downloaded file is not a valid ZIP: {exc}") from exc

        os.remove(tmp_path)
        extract_ms = int((time.time() - extract_start) * 1000)

        # Parse CSV
        csv_text = csv_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)

        logger.info(
            "Extracted %d rows from %s in %d ms", len(rows), csv_filename, extract_ms
        )

        metadata = {
            "zip_url": zip_url,
            "csv_filename": csv_filename,
            "row_count": len(rows),
            "download_duration_ms": download_ms,
            "extraction_duration_ms": extract_ms,
            "zip_file_size": zip_size,
            "response_metadata": response_json.get("metadata", {}),
        }
        return rows, metadata

    # ------------------------------------------------------------------
    # Single-resource CRUD
    # ------------------------------------------------------------------

    def get_one(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        GET a single resource from a BrAPI endpoint.

        Args:
            endpoint: Endpoint path including the ID segment
                (e.g. ``germplasm/abc123``).
            params: Optional query parameters.

        Returns:
            The ``result`` object from the BrAPI response envelope.
        """
        url = self._url(endpoint)
        response = self._client.get(url, params=params or {})
        response.raise_for_status()
        return response.json().get("result", {})

    def post_one(
        self,
        endpoint: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        POST a single item (wrapped in a list) to a BrAPI endpoint.

        BrAPI POST create endpoints expect a JSON array body and return
        ``result.data`` as a list.  This helper wraps *body* in a list and
        returns the first element of ``result.data``.

        Args:
            endpoint: Endpoint path (e.g. ``germplasm``).
            body: Single resource dict to create.

        Returns:
            The first record from ``result.data`` in the BrAPI envelope.

        Raises:
            ValueError: If the server returns an empty ``result.data``.
        """
        url = self._url(endpoint)
        response = self._client.post(url, json=[body])
        response.raise_for_status()
        data = response.json().get("result", {}).get("data", [])
        if not data:
            raise ValueError(f"Empty result.data returned from POST {endpoint}")
        return data[0]

    def post_many(
        self,
        endpoint: str,
        body: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        POST a list of items to a BrAPI endpoint (batch create).

        Args:
            endpoint: Endpoint path (e.g. ``germplasm``).
            body: List of resource dicts to create.

        Returns:
            List of records from ``result.data`` in the BrAPI envelope.
        """
        url = self._url(endpoint)
        response = self._client.post(url, json=body)
        response.raise_for_status()
        return response.json().get("result", {}).get("data", [])

    def put_one(
        self,
        endpoint: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        PUT (replace) a single resource at a BrAPI endpoint.

        Args:
            endpoint: Endpoint path including the ID segment
                (e.g. ``germplasm/abc123``).
            body: Updated resource dict.

        Returns:
            The ``result`` object from the BrAPI response envelope.
        """
        url = self._url(endpoint)
        response = self._client.put(url, json=body)
        response.raise_for_status()
        return response.json().get("result", {})

    def delete_one(self, endpoint: str) -> bool:
        """
        DELETE a resource at a BrAPI endpoint.

        Args:
            endpoint: Endpoint path including the ID segment
                (e.g. ``germplasm/abc123``).

        Returns:
            ``True`` on a successful (2xx) response.

        Raises:
            httpx.HTTPStatusError: On HTTP 4xx/5xx responses.
        """
        url = self._url(endpoint)
        response = self._client.delete(url)
        response.raise_for_status()
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> "HttpTransport":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
