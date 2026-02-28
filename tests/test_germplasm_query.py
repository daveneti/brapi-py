"""
tests/test_germplasm_query.py

Tests for GermplasmQuery, BrapiResult, and BrapiClient.
Uses `respx` to mock httpx calls — no real network required.

Run with:
    pip install -e ".[dev]"
    pytest tests/test_germplasm_query.py -v
"""
from __future__ import annotations

import json
import zipfile
import io
from typing import List
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest
import respx  # pip install respx

from brapi import BrapiClient, BrapiResult, Germplasm
from brapi.entities.germplasm import GermplasmQuery, germplasm_to_df
from brapi._http import HttpTransport
from brapi._result import BrapiResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://brapi.test"
TOKEN_URL = "https://brapi.test/token"


def _germplasm_record(**overrides) -> dict:
    """Return a minimal valid germplasm record dict."""
    base = {
        "germplasmDbId": "g-001",
        "germplasmName": "TestWheat-1",
        "germplasmPUI": "http://pui.example/g-001",
        "commonCropName": "Wheat",
    }
    base.update(overrides)
    return base


def _brapi_page(records: list, page: int = 0, total_pages: int = 1) -> dict:
    """Wrap records in a BrAPI response envelope."""
    return {
        "metadata": {
            "pagination": {
                "currentPage": page,
                "pageSize": len(records),
                "totalPages": total_pages,
                "totalCount": len(records),
            },
            "status": [],
        },
        "result": {"data": records},
    }


@pytest.fixture
def token_response():
    """Respx pattern that returns a dummy OAuth2 token."""
    return {
        "access_token": "test-token-abc",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


# ---------------------------------------------------------------------------
# Unit tests: Germplasm model
# ---------------------------------------------------------------------------


class TestGermplasmModel:
    def test_required_fields(self):
        g = Germplasm(**_germplasm_record())
        assert g.germplasmDbId == "g-001"
        assert g.germplasmName == "TestWheat-1"
        assert g.commonCropName == "Wheat"

    def test_optional_fields_default_none(self):
        g = Germplasm(**_germplasm_record())
        assert g.genus is None
        assert g.species is None
        assert g.pedigree is None

    def test_optional_fields_populated(self):
        g = Germplasm(
            **_germplasm_record(
                genus="Triticum",
                species="aestivum",
                pedigree="ParentA/ParentB",
                genus_extra_future_field="ignored_but_stored",
            )
        )
        assert g.genus == "Triticum"
        assert g.species == "aestivum"

    def test_nested_donors(self):
        record = _germplasm_record(
            donors=[{"donorAccessionNumber": "D-001", "donorInstituteCode": "DEU001"}]
        )
        g = Germplasm(**record)
        assert g.donors is not None
        assert len(g.donors) == 1
        assert g.donors[0].donorAccessionNumber == "D-001"

    def test_extra_fields_accepted(self):
        """Schema evolution: unknown fields should not raise."""
        record = _germplasm_record(futureField="some_value", anotherNew=42)
        g = Germplasm(**record)  # should not raise
        assert g.germplasmDbId == "g-001"


# ---------------------------------------------------------------------------
# Unit tests: GermplasmQuery builder (no HTTP)
# ---------------------------------------------------------------------------


class TestGermplasmQueryBuilder:
    @pytest.fixture
    def mock_transport(self):
        return MagicMock(spec=HttpTransport)

    def test_filter_sets_params(self, mock_transport):
        q = GermplasmQuery(http=mock_transport)
        q2 = q.by_crop(["Wheat"]).genus(["Triticum"])
        assert q2._params.get("commonCropNames") == ["Wheat"]
        assert q2._params.get("genus") == ["Triticum"]

    def test_builder_immutability(self, mock_transport):
        """Original query must not be mutated by filter calls."""
        base = GermplasmQuery(http=mock_transport)
        _ = base.by_crop(["Wheat"])
        assert "commonCropNames" not in base._params

    def test_filter_convenience_method(self, mock_transport):
        q = GermplasmQuery(http=mock_transport)
        q2 = q.filter(common_crop_names=["Barley"], genus=["Hordeum"])
        assert q2._params["commonCropNames"] == ["Barley"]
        assert q2._params["genus"] == ["Hordeum"]

    def test_as_table_switches_mode(self, mock_transport):
        q = GermplasmQuery(http=mock_transport).as_table()
        assert q._use_table is True

    def test_page_size_override(self, mock_transport):
        q = GermplasmQuery(http=mock_transport).page_size(500)
        assert q._page_size == 500

    def test_max_pages(self, mock_transport):
        q = GermplasmQuery(http=mock_transport).max_pages(3)
        assert q._max_pages == 3

    def test_fetch_returns_brapi_result(self, mock_transport):
        q = GermplasmQuery(http=mock_transport)
        result = q.fetch()
        assert isinstance(result, BrapiResult)

    def test_fetch_calls_transport_on_materialise(self, mock_transport):
        mock_transport.fetch_all_pages.return_value = [_germplasm_record()]
        q = GermplasmQuery(http=mock_transport)
        items = q.fetch().to_list()
        mock_transport.fetch_all_pages.assert_called_once()
        assert len(items) == 1
        assert isinstance(items[0], Germplasm)

    def test_as_table_calls_fetch_zip_csv(self, mock_transport):
        mock_transport.fetch_zip_csv.return_value = (
            [_germplasm_record()],
            {"zip_url": "http://s3/test.zip", "csv_filename": "germplasm.csv",
             "row_count": 1, "download_duration_ms": 100,
             "extraction_duration_ms": 10, "zip_file_size": 512,
             "response_metadata": {}},
        )
        q = GermplasmQuery(http=mock_transport).as_table()
        items = q.fetch().to_list()
        mock_transport.fetch_zip_csv.assert_called_once()
        assert len(items) == 1

    def test_repr(self, mock_transport):
        q = GermplasmQuery(http=mock_transport).by_crop(["Wheat"])
        r = repr(q)
        assert "GermplasmQuery" in r
        assert "search/germplasm" in r


# ---------------------------------------------------------------------------
# Unit tests: BrapiResult lazy transforms
# ---------------------------------------------------------------------------


class TestBrapiResult:
    def _make_result(self, records: list) -> BrapiResult:
        germplasms = [Germplasm(**r) for r in records]
        return BrapiResult(fetcher=lambda: germplasms)

    def test_to_list(self):
        result = self._make_result([_germplasm_record()])
        items = result.to_list()
        assert len(items) == 1
        assert isinstance(items[0], Germplasm)

    def test_to_df_returns_dataframe(self):
        result = self._make_result([_germplasm_record()])
        df = result.to_df()
        assert isinstance(df, pd.DataFrame)
        assert "germplasmDbId" in df.columns

    def test_pipe_transform_applied(self):
        result = self._make_result([_germplasm_record()])
        piped = result.pipe(lambda items: [i.germplasmName for i in items])
        names = piped.to_list()
        assert names == ["TestWheat-1"]

    def test_pipe_chaining(self):
        result = self._make_result(
            [_germplasm_record(germplasmDbId="g-001"), _germplasm_record(germplasmDbId="g-002")]
        )
        piped = (
            result
            .pipe(lambda items: [i for i in items if i.germplasmDbId == "g-001"])
        )
        assert len(piped.to_list()) == 1

    def test_fetch_is_idempotent(self):
        call_count = 0

        def fetcher():
            nonlocal call_count
            call_count += 1
            return [Germplasm(**_germplasm_record())]

        result = BrapiResult(fetcher=fetcher)
        result.fetch()
        result.fetch()
        assert call_count == 1  # HTTP called only once

    def test_iter(self):
        result = self._make_result([_germplasm_record(germplasmDbId=f"g-{i}") for i in range(5)])
        items = list(result)
        assert len(items) == 5

    def test_len(self):
        result = self._make_result([_germplasm_record()] * 3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Unit tests: germplasm_to_df flattener
# ---------------------------------------------------------------------------


class TestGermplasmToDf:
    def test_basic_flat_record(self):
        g = Germplasm(**_germplasm_record(genus="Triticum", species="aestivum"))
        df = germplasm_to_df([g])
        assert df.loc[0, "genus"] == "Triticum"
        assert df.loc[0, "species"] == "aestivum"

    def test_nested_donors_serialised_to_string(self):
        record = _germplasm_record(
            donors=[{"donorAccessionNumber": "D-001", "donorInstituteCode": "DEU001"}]
        )
        g = Germplasm(**record)
        df = germplasm_to_df([g])
        assert "donors" in df.columns
        # Should be a JSON string (not a list)
        assert isinstance(df.loc[0, "donors"], str)

    def test_relationship_object_flattened(self):
        record = _germplasm_record(
            breedingMethod={"breedingMethodDbId": "bm-1", "breedingMethodName": "Single Cross"}
        )
        g = Germplasm(**record)
        df = germplasm_to_df([g])
        assert "breedingMethod_breedingMethodDbId" in df.columns
        assert df.loc[0, "breedingMethod_breedingMethodDbId"] == "bm-1"

    def test_multiple_records_rows(self):
        records = [_germplasm_record(germplasmDbId=f"g-{i}") for i in range(10)]
        germplasms = [Germplasm(**r) for r in records]
        df = germplasm_to_df(germplasms)
        assert len(df) == 10


# ---------------------------------------------------------------------------
# Integration tests: BrapiClient with respx HTTP mocking
# ---------------------------------------------------------------------------


@respx.mock
class TestBrapiClientIntegration:
    """
    End-to-end tests using respx to intercept httpx calls.
    Validates the full client → query → transport → result pipeline.
    """

    def _setup_token(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "mock-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        )

    def test_germplasm_property_returns_query(self):
        client = BrapiClient(
            base_url=BASE_URL,
            token_endpoint=TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        )
        assert isinstance(client.germplasm, GermplasmQuery)

    def test_full_fetch_pipeline(self):
        self._setup_token()
        records = [_germplasm_record(germplasmDbId=f"g-{i}", genus="Triticum") for i in range(5)]
        respx.post(f"{BASE_URL}/brapi/v2/search/germplasm").mock(
            return_value=httpx.Response(200, json=_brapi_page(records))
        )

        with BrapiClient(
            base_url=BASE_URL,
            token_endpoint=TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        ) as client:
            df = client.germplasm.by_crop(["Wheat"]).fetch().to_df()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert df.loc[0, "genus"] == "Triticum"

    def test_multi_page_fetch(self):
        """Transport should follow pagination and stitch pages together."""
        self._setup_token()
        page0 = [_germplasm_record(germplasmDbId="g-0")]
        page1 = [_germplasm_record(germplasmDbId="g-1")]

        call_count = 0

        def _side_effect(request, route):
            nonlocal call_count
            body = json.loads(request.content)
            page = body.get("page", 0)
            data = page0 if page == 0 else page1
            call_count += 1
            return httpx.Response(200, json=_brapi_page(data, page=page, total_pages=2))

        respx.post(f"{BASE_URL}/brapi/v2/search/germplasm").mock(side_effect=_side_effect)

        with BrapiClient(
            base_url=BASE_URL,
            token_endpoint=TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        ) as client:
            items = client.germplasm.fetch().to_list()

        assert call_count == 2
        assert len(items) == 2

    def test_client_context_manager(self):
        """BrapiClient used as context manager should close transport."""
        client = BrapiClient(
            base_url=BASE_URL,
            token_endpoint=TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        )
        with client:
            pass
        # After __exit__, transport should be cleaned up
        assert client._transport is None

    def test_repr(self):
        client = BrapiClient(
            base_url=BASE_URL,
            token_endpoint=TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        )
        assert "brapi.test" in repr(client)
