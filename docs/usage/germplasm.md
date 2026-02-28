# Germplasm — worked example

!!! note "This page documents the generated entity pattern"
    `Germplasm` is one of many BrAPI entities whose code is **generated**
    from BrAPI JSON Schema by the Thymeleaf code generator.  Every generated
    entity exposes the same query interface — filter builders, `.search()`,
    `.list()`, `.get_by_id()`, `.create()`, `.update()`, `.delete()` — with
    entity-specific filter methods and a Pydantic model for the payload.
    Use this page as the reference for the pattern that applies to all entities.

The `GermplasmQuery` class provides a fluent interface over the BrAPI
Germplasm endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `.search()` | `POST /search/germplasm` | Full-featured server-side search |
| `.list()` | `GET /germplasm` | Simple list with query-string filters |
| `.get_by_id(id)` | `GET /germplasm/{id}` | Single record by primary key |
| `.create(g)` | `POST /germplasm` | Create one record |
| `.create_many(gs)` | `POST /germplasm` | Batch create two or more records |
| `.update(id, g)` | `PUT /germplasm/{id}` | Replace one record |
| `.delete(id)` | `DELETE /germplasm/{id}` | Delete one record |

---

## Connection

```python
from brapi import BrapiClient

# OAuth2 client-credentials
client = BrapiClient(
    base_url="https://brapi.example.com",
    token_endpoint="https://auth.example.com/token",
    client_id="my-client",
    client_secret="my-secret",
)

# OAuth2 resource-owner password
client = BrapiClient(
    base_url="https://brapi.example.com",
    token_endpoint="https://auth.example.com/token",
    client_id="my-client",
    client_secret="my-secret",
    username="alice",
    password="hunter2",
)

# No auth (open server)
client = BrapiClient(base_url="https://brapi.example.com")
```

Use as a context manager to guarantee the HTTP connection is closed:

```python
with BrapiClient(base_url="...", ...) as client:
    df = client.germplasm.by_crop(["Wheat"]).search().to_df()
```

---

## Searching with `POST /search/germplasm`

`.search()` is the most powerful endpoint.  It accepts a rich filter body and
handles both the **synchronous** (HTTP 200) and **asynchronous** (HTTP 202 +
polling) BrAPI search patterns transparently.

### Basic search

```python
# All germplasm for a crop
df = client.germplasm.by_crop(["Wheat"]).search().to_df()
```

### Chaining filters

Every filter method returns a **new** query — the original is not mutated, so
you can safely fork a base query:

```python
base = client.germplasm.by_crop(["Wheat"])

triticum = base.genus(["Triticum"]).search().to_df()
hordeum  = base.genus(["Hordeum"]).search().to_df()  # base unchanged
```

### Common filter methods

```python
(
    client.germplasm
    # Crop / species
    .by_crop(["Wheat", "Barley"])
    .genus(["Triticum"])
    .species(["aestivum"])
    .binomial_names(["Triticum aestivum"])
    # Identifiers
    .by_germplasm_db_id(["g-001", "g-002"])
    .by_germplasm_name(["Chinese Spring"])
    .germplasm_puis(["http://pui.example/g-001"])
    .accession_numbers(["CWI36251"])
    # Institute / programme
    .institute_codes(["DEU084"])
    .by_program(["prog-001"])
    .by_study(["study-xyz"])
    # Pedigree
    .parent_ids(["g-100"])
    .progeny_ids(["g-200"])
    # External references
    .external_reference_ids(["ref-abc"])
    .external_reference_sources(["GRIN"])
    # Misc
    .synonyms(["Capelle-Desprez"])
    .include_attributes()           # include attributeValues in response
    .modified_after(1700000000)     # Unix timestamp
    .search()
    .to_df()
)
```

### Apply many filters at once with `.filter()`

```python
df = (
    client.germplasm
    .filter(
        common_crop_names=["Wheat"],
        genus=["Triticum"],
        species=["aestivum"],
        germplasm_db_ids=["g-001", "g-002"],
        institute_codes=["DEU084"],
        parent_db_ids=["g-100"],
        modified_after=1700000000,
    )
    .search()
    .to_df()
)
```

### Async search (202 polling)

Some BrAPI servers return HTTP 202 with a `searchResultsDbId` when the query
takes time.  `search()` polls automatically — no change to calling code required.

Configure polling timeouts if needed:

```python
result = (
    client.germplasm
    .by_crop(["Wheat"])
    .search(
        poll_interval=5.0,        # seconds between retries (default 2)
        max_poll_attempts=60,     # give up after 60 × 5 s = 5 min (default 30)
    )
)
items = result.to_list()
```

---

## Listing with `GET /germplasm`

`.list()` uses the same filter state as `.search()` but calls
`GET /germplasm` instead.  Parameters that only exist on the search body
(`synonyms`, `familyCodes`, `binomialNames`, `collections`) are silently
ignored because the list endpoint does not support them.

```python
df = (
    client.germplasm
    .by_crop(["Wheat"])
    .genus(["Triticum"])
    .list()          # GET /germplasm?commonCropName=Wheat&genus=Triticum
    .to_df()
)
```

`.list()` accepts an optional `page_size` override:

```python
df = client.germplasm.by_crop(["Wheat"]).list(page_size=500).to_df()
```

---

## Materialising results

Both `.search()` and `.list()` return a lazy `BrapiResult[Germplasm]`.  No
HTTP call is made until you call a **terminal method**:

```python
result = client.germplasm.by_crop(["Wheat"]).search()  # no HTTP yet

items: list[Germplasm] = result.to_list()   # triggers HTTP
df: pd.DataFrame       = result.to_df()    # same data, as DataFrame
for g in result:                           # iterate directly
    print(g.germplasmName)
```

### Controlling page size / page count

```python
# Change page size (default 1 000)
q = client.germplasm.by_crop(["Wheat"]).page_size(500)

# Limit pages fetched (useful during development)
df = client.germplasm.by_crop(["Wheat"]).max_pages(2).search().to_df()
```

---

## Large exports — ZIP/CSV table endpoint

For bulk exports `as_table()` switches to the `POST /search/germplasm/table`
endpoint, which returns a ZIP archive containing a CSV.  The same
`BrapiResult` surface is used:

```python
df = (
    client.germplasm
    .by_crop(["Wheat"])
    .as_table()
    .fetch()
    .to_df()
)
```

!!! note
    `as_table()` uses `.fetch()` as the terminal method (not `.search()` or
    `.list()`), because the table endpoint uses its own transport path.

---

## Working with DataFrames

The `to_df()` method uses `germplasm_to_df()` to produce a flat DataFrame:

- **One-to-one relationship objects** (`breedingMethod`, `cultivar`, `crop`) are
  expanded — any `*DbId`, `*Name`, or `*PUI` fields are hoisted to top-level
  columns (`breedingMethod_breedingMethodDbId`, etc.).
- **One-to-many lists** (`donors`, `synonyms`, `taxonIds`, etc.) are
  serialised to JSON strings so each germplasm remains **one row**.

```python
df = client.germplasm.by_crop(["Wheat"]).search().to_df()

print(df.columns.tolist())
# ['germplasmDbId', 'germplasmName', 'genus', 'species',
#  'breedingMethod_breedingMethodDbId', 'donors', ...]

# Explode synonyms post-hoc if needed
import pandas as pd, json

df["synonyms_list"] = df["synonyms"].dropna().apply(json.loads)
exploded = df.explode("synonyms_list")
```

---

## Pipelining with `.pipe()`

`.pipe()` attaches a lazy transform that runs when the result is materialised:

```python
def keep_cultivated(items):
    return [g for g in items if g.biologicalStatusOfAccessionCode == "100"]

def add_short_name(items):
    for g in items:
        g.shortName = g.germplasmName.split("-")[0]
    return items

df = (
    client.germplasm
    .by_crop(["Wheat"])
    .search()
    .pipe(keep_cultivated)
    .pipe(add_short_name)
    .to_df()
)
```

Only **one** HTTP call is made, regardless of how many `.pipe()` stages are
chained.

---

## Single-record operations

### Get by ID

```python
g: Germplasm = client.germplasm.get_by_id("g-001")
print(g.germplasmName, g.genus, g.species)
```

### Create

```python
from brapi.entities.germplasm import Germplasm

# From a Pydantic model
new_g = Germplasm(
    germplasmDbId="",          # server will assign
    germplasmName="MyLine-42",
    germplasmPUI="http://pui.example/my-42",
    commonCropName="Wheat",
    genus="Triticum",
    species="aestivum",
)
created: Germplasm = client.germplasm.create(new_g)
print(created.germplasmDbId)   # server-assigned ID

# From a plain dict
created = client.germplasm.create({
    "germplasmName": "MyLine-42",
    "germplasmPUI": "http://pui.example/my-42",
    "commonCropName": "Wheat",
})
```

### Create many (batch)

Use `create_many()` for two or more records in a single request:

```python
items = client.germplasm.create_many([new_g1, new_g2, new_g3])
for g in items:
    print(g.germplasmDbId, g.germplasmName)
```

!!! warning
    `create_many()` raises `ValueError` if fewer than two items are provided.
    Use `create()` for a single record.

### Update

```python
g = client.germplasm.get_by_id("g-001")
g.pedigree = "ParentA / ParentB"

updated: Germplasm = client.germplasm.update("g-001", g)
```

### Delete

```python
ok: bool = client.germplasm.delete("g-001")
assert ok  # True on success; raises httpx.HTTPStatusError on failure
```

---

## The Germplasm model

Key fields on a `Germplasm` object:

| Field | Type | Notes |
|---|---|---|
| `germplasmDbId` | `str` | Primary key |
| `germplasmName` | `str` | Display name |
| `germplasmPUI` | `str` | Permanent Unique Identifier |
| `commonCropName` | `str` | Crop name |
| `genus` | `str` \| `None` | |
| `species` | `str` \| `None` | |
| `accessionNumber` | `str` \| `None` | Genebank accession number |
| `collection` | `str` \| `None` | Panel / collection name |
| `pedigree` | `str` \| `None` | Pedigree string |
| `donors` | `List[Donor]` \| `None` | Donor information |
| `synonyms` | `List[Synonym]` \| `None` | Alternative names/IDs |
| `taxonIds` | `List[TaxonId]` \| `None` | External taxonomic IDs |
| `externalReferences` | `List[ExternalReference]` \| `None` | Cross-references |
| `breedingMethod` | `Any` \| `None` | Related breeding method (any extra fields kept) |

All fields are optional except `germplasmDbId`, `germplasmName`, `germplasmPUI`,
and `commonCropName`.  Unknown extra fields from the server are preserved
(`extra="allow"`).

---

## Error handling

```python
import httpx

try:
    g = client.germplasm.get_by_id("does-not-exist")
except httpx.HTTPStatusError as e:
    print(e.response.status_code)   # 404

try:
    items = client.germplasm.by_crop(["Wheat"]).search().to_list()
except TimeoutError:
    print("Async search timed out — increase max_poll_attempts")
```
