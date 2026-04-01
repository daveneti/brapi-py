# Working with Entities

Every BrAPI entity in brapi-py exposes the same query interface. This guide uses
**Germplasm** as the worked example throughout — swap `client.germplasm` /
`GermplasmQuery` for any other entity (`.trials`, `.studies`, `.locations`, etc.)
and the patterns are identical.

> **Available entities:** `germplasm`, `trial`, `study`, `location`, `person`,
> `program`, `season`, `list`, `observation`, `observation_unit`,
> `observation_variable`, `scale`, `method`, `trait`, `ontology`,
> `breeding_method`, `cross`, `crossing_project`, `planned_cross`,
> `pedigree_node`, `seed_lot`, `germplasm_attribute`,
> `germplasm_attribute_value`, `call`, `call_set`, `allele_matrix`,
> `variant`, `variant_set`, `genome_map`, `marker_position`,
> `reference`, `reference_set`, `sample`, `plate`, `image`, `event`

---

## Prerequisites

Set up your local credentials once (see [Local Configuration](../index.md#local-configuration)):

```bash
cp .env.example .env   # fill in BRAPI_BASE_URL, BRAPI_CLIENT_ID, etc.
```

Then open a client:

```python
from brapi import BrapiClient

client = BrapiClient()   # reads BRAPI_* vars from .env / environment
```

---

## Search — `POST /search/{entity}`

The preferred endpoint. Handles both synchronous (HTTP 200) and asynchronous
(HTTP 202 + polling) BrAPI search flows transparently.

```python
# Germplasm example — replace .germplasm with any other entity
df = (
    client.germplasm
    .common_crop_names(['Wheat'])
    .search()
    .to_df()
)

# Trials example
df = client.trial.program_db_ids(['prog-001']).search().to_df()

# Studies example
df = client.study.season_db_ids(['season-2024']).search().to_df()
```

### Chaining filters

Every filter method returns a **new** query object — the original is unchanged.
You can safely fork a base query:

```python
base = client.germplasm.common_crop_names(['Wheat'])

all_wheat    = base.search().to_df()
by_id        = base.germplasm_db_ids(['abc123']).search().to_df()
by_name      = base.germplasm_names(['MyLine']).search().to_df()
```

### `.filter()` — bulk convenience

Apply multiple criteria in a single call:

```python
df = (
    client.germplasm
    .filter(
        common_crop_names=['Wheat'],
        germplasm_db_ids=['abc123'],
        germplasm_names=['MyLine'],
    )
    .search()
    .to_df()
)
```

---

## List — `GET /{entity}`

Simpler GET endpoint mapped to query-string params. Use this when the server
does not support the search endpoint, or for quick lookups.

```python
# same filter state, just call .list() instead of .search()
df = (
    client.germplasm
    .common_crop_names(['Wheat'])
    .list()
    .to_df()
)
```

---

## Single-record CRUD

All entities share the same four CRUD methods. Results are returned immediately
(no lazy wrapper).

### Get by ID

```python
record = client.germplasm.get_by_id('abc123')
print(record.germplasmName)

# Works the same for any entity
trial = client.trial.get_by_id('trial-001')
```

### Create

```python
from brapi.entities.generated_germplasm import Germplasm

new = Germplasm(
    commonCropName='Wheat',
    germplasmName='MyNewLine',
    germplasmPUI='http://pui.example/my-line',
)
created = client.germplasm.create(new)
print('Created:', created.germplasmDbId)
```

### Update

```python
created.accessionNumber = 'ACC-001'
updated = client.germplasm.update(created.germplasmDbId, created)
```

### Delete

```python
client.germplasm.delete(created.germplasmDbId)
```

---

## Pipe transforms

`.pipe()` applies a pure function lazily — only one HTTP call is made
regardless of how many transform stages are chained.

```python
def only_with_pui(items):
    """Keep only records that have a PUI."""
    return [r for r in items if r.germplasmPUI]

def add_label(items):
    """Attach a display label to each record."""
    for r in items:
        r.label = f'{r.germplasmName} ({r.germplasmDbId})'
    return items

df = (
    client.germplasm
    .common_crop_names(['Wheat'])
    .search()
    .pipe(only_with_pui)
    .pipe(add_label)
    .to_df()
)
```

The same pattern applies to any entity:

```python
def active_trials(items):
    return [t for t in items if t.active]

df = client.trial.search().pipe(active_trials).to_df()
```

---

## DataFrame exploration

```python
df = client.germplasm.common_crop_names(['Wheat']).search().to_df()

print('Columns:', df.columns.tolist())
print('Shape:  ', df.shape)
df['accessionNumber'].value_counts().head(10)
```

Expand a nested/JSON column (e.g. `donors`):

```python
import json

exploded = (
    df[['germplasmDbId', 'donors']]
    .dropna(subset=['donors'])
    .assign(donors=lambda d: d['donors'].apply(json.loads))
    .explode('donors')
)
```

---

## Error handling

```python
import httpx

# 404
try:
    client.germplasm.get_by_id('does-not-exist')
except httpx.HTTPStatusError as e:
    print(f'HTTP {e.response.status_code}: {e.request.url}')

# Async search poll timeout
try:
    client.germplasm.search(max_poll_attempts=1).to_list()
except TimeoutError as e:
    print('TimeoutError:', e)
```

---

## Interactive notebook

The [germplasm_exploration notebook](../../notebooks/germplasm_exploration.ipynb) covers
all of the above interactively with runnable cells for each section.
