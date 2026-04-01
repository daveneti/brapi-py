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

## Local Configuration

Credentials are read from environment variables (or a `.env` file in the project root).
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
# Copy the template and fill in your values
cp .env.example .env
```

`.env` is listed in `.gitignore` and will never be committed.
`.env.example` is the safe-to-commit template — keep it up to date for teammates.

Once `.env` exists, `BrapiClient()` with no arguments picks up all credentials automatically:

```python
from brapi import BrapiClient

client = BrapiClient()   # reads BRAPI_* from .env / environment
```

## Installation (development)

```bash
pip install -e ".[dev]"
```

---

## Development Workflow

```
          ┌─────────────────────────────┐
          │  feature/my-feature branch  │  ← you work here
          └─────────────┬───────────────┘
                        │  PR / merge
                        ▼
          ┌─────────────────────────────┐
          │         develop             │  ← non-generated source
          └─────────────┬───────────────┘
                        │  GitHub Actions (auto)
                        ▼
          ┌─────────────────────────────┐
          │          master             │  ← generated code + releases
          └─────────────────────────────┘
```

### Branches at a glance

| Branch | Purpose | Who pushes |
|--------|---------|-----------|
| `master` | Full generated codebase, always releasable. Every merge is tagged and released. | GitHub Actions only |
| `develop` | Hand-written source code (no generated files). Start all work here. | Developers + Actions (version bump) |
| `feature/*`, `fix/*`, `chore/*` | Short-lived branches for individual changes. | Developers |

### Starting a new feature or updating the generator

```bash
# 1. Always branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# 2. Make your changes, commit, push
git add .
git commit -m "feat: describe your change"
git push origin feature/my-feature

# 3. Open a Pull Request into develop and merge it
```

Once the PR is merged into `develop`, GitHub Actions takes over automatically:

1. **Generate** — runs the BrAPI Schema Tools code generator with the version pinned in `generator/build.gradle`
2. **Verify** — imports the package to catch any generation errors early
3. **Version** — computes the next release version (see below) and writes it to `__version__.py` and `pyproject.toml`
4. **Publish to master** — force-adds all generated files and merges develop into `master`
5. **Release** — creates a Git tag (`v1.2.3`) and a GitHub Release with auto-generated notes

### Version numbering

The minor version is **automatically incremented** unless you change it yourself.

| Scenario | What to do | Result |
|----------|-----------|--------|
| Routine change (new feature, dependency update, generator bump) | Nothing — leave `__version__` as-is | `0.1.0` → `0.2.0` (minor bump) |
| Breaking API change | Edit `src/brapi/__version__.py` and `pyproject.toml` on your feature branch to the new major version | `0.2.0` → `1.0.0` (honoured as-is) |
| Targeted patch release | Set a specific version on your feature branch | `0.2.0` → `0.2.1` (honoured as-is) |

The rule: if `__version__` in `develop` equals the latest release tag, the minor version is bumped automatically. If the versions differ, your manually set value is used.

The version bump commit is pushed back to `develop` with `[skip ci]` so it doesn't re-trigger the workflow.

### Updating the generator schema version

The BrAPI Schema Tools generator version is set in `generator/build.gradle`:

```groovy
ext {
    brapiSchemaToolsVersion = '0.58.0'   // ← change this
}
```

Update this value on a feature branch, open a PR into `develop`, and the rest is automatic.

### Required GitHub repository secrets

| Secret | Purpose |
|--------|---------|
| `DEPLOY_KEY` | SSH deploy key with **write** access, used to push generated commits back to `master` and `develop`. Generate with `ssh-keygen -t ed25519`, add the public key as a Deploy Key (with write access) in *Settings → Deploy keys*, and store the private key as this secret. |

The `GITHUB_TOKEN` (automatically provided by Actions) is used only to create the GitHub Release.

