"""
entities/germplasm.py — Germplasm Pydantic model + GermplasmQuery.

This file is a candidate for Thymeleaf-based code generation.
Keep hand-written infrastructure dependencies minimal:
  - Pydantic BaseModel for the entity
  - BaseQuery from brapi._query

Generated from:
  BrAPI-Schema/BrAPI-Germplasm/Germplasm.json
  BrAPI-Schema/Requests/GermplasmRequest.json
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .._query import BaseQuery
from .._http import HttpTransport
from .._result import BrapiResult


# ---------------------------------------------------------------------------
# Sub-models (embedded in Germplasm)
# ---------------------------------------------------------------------------


class Donor(BaseModel):
    """Identifier assigned to an accession by the material donor."""

    model_config = ConfigDict(extra="allow")

    donorAccessionNumber: Optional[str] = None
    donorInstituteCode: Optional[str] = None


class GermplasmOrigin(BaseModel):
    """Geographic origin information for germplasm material."""

    model_config = ConfigDict(extra="allow")

    coordinateUncertainty: Optional[str] = None
    coordinates: Optional[List[Any]] = None


class StorageType(BaseModel):
    """Storage type at a genebank."""

    model_config = ConfigDict(extra="allow")

    code: Optional[str] = None
    description: Optional[str] = None


class Synonym(BaseModel):
    """Alternative name or ID for a germplasm."""

    model_config = ConfigDict(extra="allow")

    synonym: Optional[str] = None
    type: Optional[str] = None


class TaxonId(BaseModel):
    """Taxonomic identifier from an external source."""

    model_config = ConfigDict(extra="allow")

    sourceName: Optional[str] = None
    taxonId: Optional[str] = None


class ExternalReference(BaseModel):
    """External reference to this germplasm in another system."""

    model_config = ConfigDict(extra="allow")

    referenceDbId: Optional[str] = None
    referenceName: Optional[str] = None
    referenceSource: Optional[str] = None


# ---------------------------------------------------------------------------
# Primary model
# ---------------------------------------------------------------------------


class Germplasm(BaseModel):
    """
    BrAPI Germplasm entity.

    Required fields: ``germplasmDbId``, ``germplasmName``, ``germplasmPUI``,
    ``commonCropName``.

    All other fields are optional.  Nested relationship lists (``donors``,
    ``germplasmOrigin``, ``storageTypes``, ``synonyms``, ``taxonIds``) are
    parsed into sub-models when present; unknown extra fields are accepted
    (``extra="allow"``) to survive schema evolution without breaking.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # --- Required ---
    germplasmDbId: str
    germplasmName: str
    germplasmPUI: str
    commonCropName: str

    # --- Scalar optional ---
    accessionNumber: Optional[str] = None
    acquisitionDate: Optional[str] = None
    biologicalStatusOfAccessionCode: Optional[str] = None
    biologicalStatusOfAccessionDescription: Optional[str] = None
    collection: Optional[str] = None
    countryOfOriginCode: Optional[str] = None
    defaultDisplayName: Optional[str] = None
    documentationURL: Optional[str] = None
    generationCode: Optional[str] = None
    genus: Optional[str] = None
    germplasmPreprocessing: Optional[str] = None
    instituteCode: Optional[str] = None
    instituteName: Optional[str] = None
    pedigree: Optional[str] = None
    seedSource: Optional[str] = None
    seedSourceDescription: Optional[str] = None
    species: Optional[str] = None
    speciesAuthority: Optional[str] = None
    subtaxa: Optional[str] = None
    subtaxaAuthority: Optional[str] = None

    # --- Nested lists ---
    donors: Optional[List[Donor]] = None
    externalReferences: Optional[List[ExternalReference]] = None
    germplasmOrigin: Optional[List[GermplasmOrigin]] = None
    storageTypes: Optional[List[StorageType]] = None
    synonyms: Optional[List[Synonym]] = None
    taxonIds: Optional[List[TaxonId]] = None

    # --- Relationship IDs (many-to-one; full objects are dropped in list endpoints) ---
    # These arrive as simple dicts when present; use Any to avoid failures.
    breedingMethod: Optional[Any] = None
    cultivar: Optional[Any] = None
    crop: Optional[Any] = None
    additionalInfo: Optional[Any] = None


# ---------------------------------------------------------------------------
# Custom DataFrame flattener
# ---------------------------------------------------------------------------


def germplasm_to_df(items: List[Germplasm]) -> pd.DataFrame:
    """
    Convert a list of ``Germplasm`` objects to a flat ``pd.DataFrame``.

    Nested sub-model lists (``donors``, ``synonyms``, ``taxonIds``,
    ``storageTypes``, ``germplasmOrigin``) are serialised to JSON strings
    so each germplasm remains one row.  Relationship objects
    (``breedingMethod``, ``cultivar``, ``crop``) are expanded one level:
    any ``*DbId`` and ``*Name`` fields are hoisted to top-level columns.
    """
    rows: List[Dict[str, Any]] = []
    for item in items:
        row = item.model_dump(mode="python", exclude_none=True)

        # Flatten one-to-one relationships: extract DbId/Name into top-level cols
        for rel in ("breedingMethod", "cultivar", "crop"):
            obj = row.pop(rel, None)
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.endswith(("DbId", "Name", "PUI")):
                        row[f"{rel}_{k}"] = v

        # Serialise one-to-many lists to strings (one row per germplasm)
        for arr_field in (
            "donors",
            "externalReferences",
            "germplasmOrigin",
            "storageTypes",
            "synonyms",
            "taxonIds",
        ):
            arr = row.pop(arr_field, None)
            if arr:
                import json
                row[arr_field] = json.dumps(arr, default=str)

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

_SEARCH_ENDPOINT = "search/germplasm"
_SEARCH_TABLE_ENDPOINT = "search/germplasm/table"
_CRUD_ENDPOINT = "germplasm"

# Maps POST /search/germplasm body parameter names → GET /germplasm query parameter
# names.  Parameters absent from this dict (or mapped to None) are not forwarded
# to the list endpoint because GET /germplasm does not support them.
_LIST_PARAM_MAP: Dict[str, Optional[str]] = {
    "commonCropNames": "commonCropName",
    "germplasmDbIds": "germplasmDbId",
    "germplasmNames": "germplasmName",
    "germplasmPUIs": "germplasmPUI",
    "accessionNumbers": "accessionNumber",
    "instituteCodes": "instituteCode",
    "programDbIds": "programDbId",
    "programNames": "programName",
    "studyDbIds": "studyDbId",
    "studyNames": "studyName",
    "trialDbIds": "trialDbId",
    "trialNames": "trialName",
    "parentDbIds": "parentDbId",
    "progenyDbIds": "progenyDbId",
    "externalReferenceIds": "externalReferenceId",
    "externalReferenceSources": "externalReferenceSource",
    # Already singular — pass through unchanged:
    "genus": "genus",
    "species": "species",
    "includeAttributeValues": "includeAttributeValues",
    "modifiedAfter": "modifiedAfter",
    # Not supported by GET /germplasm — intentionally omitted:
    # "synonyms", "familyCodes", "binomialNames", "collections"
}


class GermplasmQuery(BaseQuery[Germplasm]):
    """
    Fluent query builder for the BrAPI Germplasm resource.

    Create via ``BrapiClient.germplasm`` — do not instantiate directly.

    All filter methods return a new ``GermplasmQuery`` (immutable builder
    pattern) so the same base query can be forked::

        base = client.germplasm.by_crop(["Wheat"])
        q1 = base.genus(["Triticum"])
        q2 = base.species(["aestivum"])

    **Materialise the query** by calling either terminal builder:

    * ``.search()`` — ``POST /search/germplasm``.  Supports all filter
      parameters and handles the BrAPI asynchronous search pattern
      (HTTP 202 + polling) transparently.
    * ``.list()`` — ``GET /germplasm``.  Uses the same filter state but
      maps parameters to the simpler GET query-string form.  A subset of
      filter parameters is supported (see ``.list()`` docstring).

    Both return a lazy ``BrapiResult[Germplasm]``; the HTTP call is
    deferred until a terminal method is invoked::

        df     = q1.search().to_df()    # POST /search/germplasm
        df     = q1.list().to_df()      # GET  /germplasm
        items  = list(q1.search())      # iterate directly

    Use the ZIP/CSV search-table endpoint (fastest for large exports)::

        df = client.germplasm.by_crop(["Wheat"]).as_search_table().fetch().to_df()
    """

    def __init__(self, http: HttpTransport) -> None:
        super().__init__(
            http=http,
            endpoint=_SEARCH_ENDPOINT,
            model_cls=Germplasm,
            http_method="POST",
            search_table_endpoint=_SEARCH_TABLE_ENDPOINT,
            to_df_fn=germplasm_to_df,
        )

    # ------------------------------------------------------------------
    # Filter methods — map directly to GermplasmRequest.json parameters
    # ------------------------------------------------------------------

    # --- From CropParameters ---

    def by_crop(self, common_crop_names: List[str]) -> "GermplasmQuery":
        """Filter by common crop names (e.g. ``["Wheat", "Barley"]``)."""
        return self._set_param("commonCropNames", common_crop_names)  # type: ignore[return-value]

    # --- From GermplasmParameters ---

    def by_germplasm_name(self, names: List[str]) -> "GermplasmQuery":
        """Filter by exact germplasm names."""
        return self._set_param("germplasmNames", names)  # type: ignore[return-value]

    def by_germplasm_db_id(self, db_ids: List[str]) -> "GermplasmQuery":
        """Filter by germplasm database IDs."""
        return self._set_param("germplasmDbIds", db_ids)  # type: ignore[return-value]

    def germplasm_puis(self, puis: List[str]) -> "GermplasmQuery":
        """Filter by Permanent Unique Identifiers."""
        return self._set_param("germplasmPUIs", puis)  # type: ignore[return-value]

    def accession_numbers(self, numbers: List[str]) -> "GermplasmQuery":
        """Filter by genebank accession numbers."""
        return self._set_param("accessionNumbers", numbers)  # type: ignore[return-value]

    def collections(self, collection_names: List[str]) -> "GermplasmQuery":
        """Filter by panel/collection names."""
        return self._set_param("collections", collection_names)  # type: ignore[return-value]

    def family_codes(self, codes: List[str]) -> "GermplasmQuery":
        """Filter by family codes."""
        return self._set_param("familyCodes", codes)  # type: ignore[return-value]

    def institute_codes(self, codes: List[str]) -> "GermplasmQuery":
        """Filter by FAO/WIEWS institute codes (e.g. ``["DEU084"]``)."""
        return self._set_param("instituteCodes", codes)  # type: ignore[return-value]

    def binomial_names(self, names: List[str]) -> "GermplasmQuery":
        """Filter by binomial (genus + species) names."""
        return self._set_param("binomialNames", names)  # type: ignore[return-value]

    def genus(self, genera: List[str]) -> "GermplasmQuery":
        """Filter by genus (e.g. ``["Triticum", "Hordeum"]``)."""
        return self._set_param("genus", genera)  # type: ignore[return-value]

    def species(self, species_list: List[str]) -> "GermplasmQuery":
        """Filter by species epithet (e.g. ``["aestivum", "vulgare"]``)."""
        return self._set_param("species", species_list)  # type: ignore[return-value]

    def synonyms(self, synonym_list: List[str]) -> "GermplasmQuery":
        """Filter by synonym names or IDs."""
        return self._set_param("synonyms", synonym_list)  # type: ignore[return-value]

    # --- From ProgramParameters ---

    def by_program(self, program_db_ids: List[str]) -> "GermplasmQuery":
        """Filter by breeding program database IDs."""
        return self._set_param("programDbIds", program_db_ids)  # type: ignore[return-value]

    def by_program_name(self, program_names: List[str]) -> "GermplasmQuery":
        """Filter by breeding program names."""
        return self._set_param("programNames", program_names)  # type: ignore[return-value]

    # --- From StudyParameters ---

    def by_study(self, study_db_ids: List[str]) -> "GermplasmQuery":
        """Filter by study database IDs."""
        return self._set_param("studyDbIds", study_db_ids)  # type: ignore[return-value]

    def by_study_name(self, study_names: List[str]) -> "GermplasmQuery":
        """Filter by study names."""
        return self._set_param("studyNames", study_names)  # type: ignore[return-value]

    # --- From TrialParameters ---

    def by_trial(self, trial_db_ids: List[str]) -> "GermplasmQuery":
        """Filter by trial database IDs."""
        return self._set_param("trialDbIds", trial_db_ids)  # type: ignore[return-value]

    def by_trial_name(self, trial_names: List[str]) -> "GermplasmQuery":
        """Filter by trial names."""
        return self._set_param("trialNames", trial_names)  # type: ignore[return-value]

    # --- Pedigree ---

    def parent_ids(self, parent_db_ids: List[str]) -> "GermplasmQuery":
        """Filter by parent germplasm database IDs."""
        return self._set_param("parentDbIds", parent_db_ids)  # type: ignore[return-value]

    def progeny_ids(self, progeny_db_ids: List[str]) -> "GermplasmQuery":
        """Filter by progeny germplasm database IDs."""
        return self._set_param("progenyDbIds", progeny_db_ids)  # type: ignore[return-value]

    # --- From FilterAndSortParameters ---

    def external_reference_ids(self, ids: List[str]) -> "GermplasmQuery":
        """Filter by external reference IDs."""
        return self._set_param("externalReferenceIds", ids)  # type: ignore[return-value]

    def external_reference_sources(self, sources: List[str]) -> "GermplasmQuery":
        """Filter by external reference source names."""
        return self._set_param("externalReferenceSources", sources)  # type: ignore[return-value]

    # --- From IncludedAttributesParameters ---

    def include_attributes(self) -> "GermplasmQuery":
        """Request inclusion of ``attributeValues`` in the response."""
        return self._set_param("includeAttributeValues", True)  # type: ignore[return-value]

    # --- Bulk convenience ---

    def filter(
        self,
        *,
        common_crop_names: Optional[List[str]] = None,
        germplasm_names: Optional[List[str]] = None,
        germplasm_db_ids: Optional[List[str]] = None,
        germplasm_puis: Optional[List[str]] = None,
        accession_numbers: Optional[List[str]] = None,
        institute_codes: Optional[List[str]] = None,
        genus: Optional[List[str]] = None,
        species: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        synonyms: Optional[List[str]] = None,
        parent_db_ids: Optional[List[str]] = None,
        progeny_db_ids: Optional[List[str]] = None,
        modified_after: Optional[int] = None,
    ) -> "GermplasmQuery":
        """
        Apply multiple filters in one call.  All parameters are optional; only
        non-``None`` values are added to the request.

        Example::

            (
                client.germplasm
                    .filter(
                        common_crop_names=["Wheat"],
                        genus=["Triticum"],
                        species=["aestivum"],
                    )
                    .fetch()
                    .to_df()
            )
        """
        q: GermplasmQuery = self
        if common_crop_names:
            q = q.by_crop(common_crop_names)
        if germplasm_names:
            q = q.by_germplasm_name(germplasm_names)
        if germplasm_db_ids:
            q = q.by_germplasm_db_id(germplasm_db_ids)
        if germplasm_puis:
            q = q.germplasm_puis(germplasm_puis)
        if accession_numbers:
            q = q.accession_numbers(accession_numbers)
        if institute_codes:
            q = q.institute_codes(institute_codes)
        if genus:
            q = q.genus(genus)
        if species:
            q = q.species(species)
        if collections:
            q = q.collections(collections)
        if synonyms:
            q = q.synonyms(synonyms)
        if parent_db_ids:
            q = q.parent_ids(parent_db_ids)
        if progeny_db_ids:
            q = q.progeny_ids(progeny_db_ids)
        if modified_after is not None:
            q = q.modified_after(modified_after)
        return q

    # ------------------------------------------------------------------
    # Search / list — lazy BrapiResult builders
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 30,
    ) -> "BrapiResult[Germplasm]":
        """
        Execute the query by POSTing to ``POST /search/germplasm``.

        Handles both the **synchronous** (HTTP 200, immediate ``result.data``)
        and **asynchronous** (HTTP 202, ``searchResultsDbId`` + polling) BrAPI
        search patterns transparently.

        Build filters with the fluent methods before calling this::

            df = (
                client.germplasm
                    .by_crop(["Wheat"])
                    .genus(["Triticum"])
                    .search()
                    .to_df()
            )

        Args:
            poll_interval: Seconds between polling retries when the server
                returns 202 (default 2).
            max_poll_attempts: Maximum number of polling retries before raising
                ``TimeoutError`` (default 30, i.e. up to 60 s wait).

        Returns:
            Lazy ``BrapiResult[Germplasm]``.
        """
        params = dict(self._params)
        page_size = self._page_size
        max_pages = self._max_pages
        http = self._http
        model_cls = self._model_cls
        to_df_fn = self._to_df_fn

        def _fetcher() -> List[Germplasm]:
            records = http.fetch_all_search_pages(
                endpoint=_SEARCH_ENDPOINT,
                params=params,
                page_size=page_size,
                max_pages=max_pages,
                poll_interval=poll_interval,
                max_poll_attempts=max_poll_attempts,
            )
            return [model_cls(**r) for r in records]  # type: ignore[call-arg]

        return BrapiResult(fetcher=_fetcher, to_df_fn=to_df_fn)  # type: ignore[arg-type]

    def list(
        self,
        *,
        page_size: Optional[int] = None,
    ) -> "BrapiResult[Germplasm]":
        """
        Execute the query by calling ``GET /germplasm``.

        Uses the same filter state built with the fluent methods.  Parameters
        that accept multiple values are passed as repeated query-string keys so
        the server can filter on all supplied values.

        .. note::
            Some filter parameters supported by ``search()``
            (``synonyms``, ``familyCodes``, ``binomialNames``, ``collections``)
            are **not** available on the list endpoint and will be silently
            ignored.

        Example::

            df = (
                client.germplasm
                    .by_crop(["Wheat"])
                    .genus(["Triticum"])
                    .list()
                    .to_df()
            )

        Args:
            page_size: Override the page size for this call only.

        Returns:
            Lazy ``BrapiResult[Germplasm]``.
        """
        _page_size = page_size if page_size is not None else self._page_size
        max_pages = self._max_pages

        # Translate search params (plural body keys) → GET query params (singular)
        get_params: Dict[str, Any] = {}
        for search_key, value in self._params.items():
            get_key = _LIST_PARAM_MAP.get(search_key, search_key)  # default: pass through
            if get_key is None:
                continue  # not supported on GET /germplasm
            # Lists become repeated query-string values; scalars pass through
            get_params[get_key] = value

        http = self._http
        model_cls = self._model_cls
        to_df_fn = self._to_df_fn

        def _fetcher() -> List[Germplasm]:
            records = http.fetch_all_pages(
                endpoint=_CRUD_ENDPOINT,
                method="GET",
                params=get_params,
                page_size=_page_size,
                max_pages=max_pages,
            )
            return [model_cls(**r) for r in records]  # type: ignore[call-arg]

        return BrapiResult(fetcher=_fetcher, to_df_fn=to_df_fn)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # CRUD operations — execute immediately (not lazy BrapiResult)
    # ------------------------------------------------------------------

    def get_by_id(self, germplasm_db_id: str) -> "Germplasm":
        """
        Retrieve a single germplasm by its database ID.

        Calls ``GET /germplasm/{germplasmDbId}``.

        Args:
            germplasm_db_id: The ``germplasmDbId`` to retrieve.

        Returns:
            A single ``Germplasm`` object.
        """
        record = self._http.get_one(f"{_CRUD_ENDPOINT}/{germplasm_db_id}")
        return Germplasm(**record)

    def create(
        self,
        germplasm: Union["Germplasm", Dict[str, Any]],
    ) -> "Germplasm":
        """
        Create a single germplasm record using ``POST /germplasm``.

        The server assigns ``germplasmDbId``; you may omit it from the input.

        Args:
            germplasm: A ``Germplasm`` instance or a plain dict matching the
                ``Germplasm`` schema.

        Returns:
            The created ``Germplasm`` object with the server-assigned
            ``germplasmDbId``.
        """
        body = (
            germplasm.model_dump(mode="json", exclude_none=True)
            if isinstance(germplasm, Germplasm)
            else germplasm
        )
        record = self._http.post_one(_CRUD_ENDPOINT, body)
        return Germplasm(**record)

    def create_many(
        self,
        germplasms: List[Union["Germplasm", Dict[str, Any]]],
    ) -> List["Germplasm"]:
        """
        Create two or more germplasm records in a single ``POST /germplasm`` call.

        Args:
            germplasms: A list of ``Germplasm`` instances or plain dicts.
                Must contain at least **two** items — use :meth:`create` for a
                single germplasm.

        Returns:
            List of created ``Germplasm`` objects with server-assigned IDs.

        Raises:
            ValueError: If fewer than two items are provided.
        """
        if len(germplasms) < 2:
            raise ValueError(
                "create_many() requires at least 2 items. "
                "Use create() for a single germplasm."
            )
        body = [
            g.model_dump(mode="json", exclude_none=True)
            if isinstance(g, Germplasm)
            else g
            for g in germplasms
        ]
        records = self._http.post_many(_CRUD_ENDPOINT, body)
        return [Germplasm(**r) for r in records]

    def update(
        self,
        germplasm_db_id: str,
        germplasm: Union["Germplasm", Dict[str, Any]],
    ) -> "Germplasm":
        """
        Update a germplasm record using ``PUT /germplasm/{germplasmDbId}``.

        Args:
            germplasm_db_id: The ``germplasmDbId`` of the record to update.
            germplasm: A ``Germplasm`` instance or plain dict with updated fields.

        Returns:
            The updated ``Germplasm`` object as returned by the server.
        """
        body = (
            germplasm.model_dump(mode="json", exclude_none=True)
            if isinstance(germplasm, Germplasm)
            else germplasm
        )
        record = self._http.put_one(f"{_CRUD_ENDPOINT}/{germplasm_db_id}", body)
        return Germplasm(**record)

    def delete(self, germplasm_db_id: str) -> bool:
        """
        Delete a germplasm record using ``DELETE /germplasm/{germplasmDbId}``.

        Args:
            germplasm_db_id: The ``germplasmDbId`` of the record to delete.

        Returns:
            ``True`` if the deletion was accepted by the server.

        Raises:
            httpx.HTTPStatusError: If the server returns an error response.
        """
        return self._http.delete_one(f"{_CRUD_ENDPOINT}/{germplasm_db_id}")
