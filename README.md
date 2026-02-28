# brapi-py

Fluent Python client for [BrAPI v2](https://brapi.org/) endpoints.

## Design Principles

- **Method chaining** — build queries with a fluent interface; no HTTP is issued until you call a terminal method.
- **Lazy evaluation** — `.fetch()` / `.to_list()` / `.to_df()` trigger execution; `.filter()`, `.modified_after()`, `.by_program()` etc. are pure builders.
- **`.pipe()` for transformations** — slot user-defined functions into any result pipeline without breaking the chain.
- **Entity-aware** — models are generated from BrAPI JSON Schema (via a Thymeleaf code generator).  Non-generated transport and query-builder infrastructure lives in `_http.py`, `_query.py`, and `_result.py`.
- **Dual output** — JSON endpoints return `List[EntityModel]`; ZIP/CSV table endpoints are normalised into the same `BrapiResult` surface so callers get a `pd.DataFrame` regardless of wire format.

## Architecture

```
BrapiClient
│
├── .germplasm              → GermplasmQuery  (generated stub + hand-written transport wiring)
│    ├── .filter(...)
│    ├── .modified_after(ts)
│    ├── .by_program(puids)
│    ├── .by_crop(crops)
│    ├── .include_attributes()
│    └── .fetch()           → BrapiResult[Germplasm]
│         ├── .to_list()    → List[Germplasm]
│         ├── .to_df()      → pd.DataFrame
│         └── .pipe(fn)     → BrapiResult[T]
│
├── HTTP transport  (_http.py)   — paged JSON + ZIP/CSV download
├── Auth            (_auth.py)   — OAuth2 client-credentials / password
└── Base query      (_query.py)  — shared fluent builder logic
```

## Quick Start

```python
from brapi import BrapiClient

client = BrapiClient(
    base_url="https://phenomeone-qa.basf.net",
    token_endpoint="https://auth.example.com/token",
    client_id="my-client-id",
    client_secret="my-secret",
)

# Fluent JSON fetch
germplasm = (
    client.germplasm
    .filter(commonCropNames=["Soybean"])
    .by_program(["urn:example:prog1"])
    .include_attributes()
    .fetch()
    .to_df()
)

# Pipe transformations
from brapi.entities.germplasm import filter_wild

result = (
    client.germplasm
    .filter(genus=["Glycine"])
    .fetch()
    .pipe(filter_wild)          # user-defined transform
    .to_df()
)

# CSV/table endpoint (large datasets)
df = (
    client.germplasm
    .filter(programPUIs=["urn:..."])
    .as_table()     # switches to ZIP/CSV endpoint
    .to_df()
)
```

## Code Generation

Entity models (`src/brapi/entities/`) are intended to be generated from BrAPI JSON Schema files
using your Thymeleaf-based generator. The base infrastructure (`_http.py`, `_query.py`,
`_result.py`, `client.py`) is **not** generated.

Each generated entity file must:
1. Define a `Pydantic v2` model class.
2. Define a `*Query` class that extends `BaseQuery`.
3. Register any entity-specific normalisation logic (e.g. flattening nested objects to DataFrame columns).

## Installation (development)

```bash
pip install -e ".[dev]"
```
