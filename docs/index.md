# brapi-py

Fluent Python client for [BrAPI v2](https://brapi.org/) endpoints.

## Design Principles

- **Method chaining** — build queries with a fluent interface; no HTTP is issued until you call a terminal method.
- **Lazy evaluation** — `.search()`, `.list()`, `.to_list()`, `.to_df()` trigger execution; filter methods are pure builders that return a new query.
- **Dual search patterns** — `.search()` posts to `POST /search/{entity}` and handles both synchronous (200) and asynchronous (202 + polling) BrAPI search flows; `.list()` calls `GET /{entity}` using the same filter state.
- **`.pipe()` for transformations** — slot user-defined functions into any result pipeline without breaking the chain.
- **Entity-aware** — models are generated from BrAPI JSON Schema via a Thymeleaf code generator. Non-generated transport and query-builder infrastructure lives in `_http.py`, `_query.py`, and `_result.py`.
- **Dual wire format** — JSON endpoints return `List[EntityModel]`; ZIP/CSV table endpoints are normalised to the same `BrapiResult` surface.

## Architecture

The library is split into two layers.

**Hand-written infrastructure** — never overwritten by the generator:

| File | Responsibility |
|---|---|
| `_base_client.py` | `BaseBrapiClient` — connection, auth, lifecycle |
| `_http.py` | `HttpTransport` — paged JSON, ZIP/CSV download, CRUD verbs |
| `_query.py` | `BaseQuery[T]` — immutable fluent builder, page controls |
| `_result.py` | `BrapiResult[T]` — lazy result container with `.pipe()` |

**Generated entity layer** — one file per BrAPI entity, produced by the
Thymeleaf code generator from BrAPI JSON Schema:

```
BrapiClient(BaseBrapiClient)
│
│   (one @property per generated entity)
├── .germplasm   → GermplasmQuery      ← generated example
├── .trials      → TrialQuery          ← generated
├── .studies     → StudyQuery          ← generated
└── ...                                ← all other BrAPI entities
     │
     │  Every EntityQuery(BaseQuery[Entity]) exposes:
     │
     │  ── Filter builders (immutable, chainable) ──────────────────────
     ├── .by_<criterion>(...)     entity-specific filter methods
     ├── .filter(...)             bulk convenience filter
     ├── .page_size(n)            records per HTTP page (default 1 000)
     ├── .max_pages(n)            cap total pages fetched
     │
     │  ── Lazy result builders ──────────────────────────────────────
     ├── .search()   → BrapiResult[Entity]   POST /search/<entity>
     ├── .list()     → BrapiResult[Entity]   GET  /<entity>
     └── .as_table() → (self, then .fetch()) POST /search/<entity>/table
          └── BrapiResult[Entity]
               ├── .to_list()  → List[Entity]
               ├── .to_df()    → pd.DataFrame
               └── .pipe(fn)   → BrapiResult[T]   (lazy transform)

     │  ── Immediate CRUD (execute on call, no lazy wrapper) ──────────
     ├── .get_by_id(id)     → Entity
     ├── .create(obj)       → Entity
     ├── .create_many(lst)  → List[Entity]
     ├── .update(id, obj)   → Entity
     └── .delete(id)        → bool
```

## Installation

```bash
pip install brapi-py
```

Development install (includes test and docs dependencies):

```bash
git clone https://github.com/your-org/brapi-py
cd brapi-py
pip install -e ".[dev,docs]"
```

## Local Configuration

Credentials are read from environment variables or a `.env` file in the project root.
**Never hard-code secrets in notebooks or source files.**

| Variable | Description |
|---|---|
| `BRAPI_BASE_URL` | Full base URL of the BrAPI server |
| `BRAPI_TOKEN_ENDPOINT` | OAuth2 token endpoint (omit for unauthenticated servers) |
| `BRAPI_CLIENT_ID` | OAuth2 client ID |
| `BRAPI_CLIENT_SECRET` | OAuth2 client secret |
| `BRAPI_USERNAME` | Username (OAuth2 password flow only) |
| `BRAPI_PASSWORD` | Password (OAuth2 password flow only) |

**Setup**

```bash
cp .env.example .env   # then fill in your values
```

`.env` is git-ignored and will never be committed. `.env.example` is the safe-to-commit
template — keep it updated for teammates.

Once `.env` exists, `BrapiClient()` with no arguments picks up all credentials automatically:

```python
from brapi import BrapiClient

client = BrapiClient()   # reads BRAPI_* vars from .env / environment
```

You can also pass credentials explicitly if needed:

```python
client = BrapiClient(
    base_url="https://brapi.example.org",
    token_endpoint="https://brapi.example.org/token",
    client_id="my-client",
    client_secret="my-secret",
)
```

## Quick Start

The pattern below works identically for every generated entity —
just replace `.germplasm` with `.trials`, `.studies`, etc.

```python
from brapi import BrapiClient

with BrapiClient(
    base_url="https://brapi.example.com",
    token_endpoint="https://auth.example.com/token",
    client_id="my-client",
    client_secret="my-secret",
) as client:

    # Search (POST /search/germplasm) — full filter support, handles async 202
    df = (
        client.germplasm
            .by_crop(["Wheat"])
            .search()
            .to_df()
    )

    # List  (GET /germplasm) — same filter state, simpler endpoint
    df = client.germplasm.by_crop(["Wheat"]).list().to_df()

    # Single record by ID
    g = client.germplasm.get_by_id("g-001")

    # Create / update / delete
    created = client.germplasm.create({"germplasmName": "MyLine", ...})
    updated = client.germplasm.update(created.germplasmDbId, created)
    client.germplasm.delete(created.germplasmDbId)
```

See [Working with Entities](usage/entities.md) for a detailed walkthrough — it documents
every feature of the entity pattern using Germplasm as the worked example.
