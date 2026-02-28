"""
scripts/explore_germplasm.py
----------------------------
Quick exploration script — not a unit test.
Edit the CONNECTION section, then run:

    # from the brapi-py project root
    pip install -e .
    python scripts/explore_germplasm.py

    # or with specific sections only
    python scripts/explore_germplasm.py --section search
    python scripts/explore_germplasm.py --section list
    python scripts/explore_germplasm.py --section crud
"""
from __future__ import annotations

import argparse
import json
import sys

from brapi import BrapiClient
from brapi.entities.germplasm import Germplasm

# ── CONNECTION ──────────────────────────────────────────────────────────────
BASE_URL       = "https://brapi.example.com"
TOKEN_ENDPOINT = "https://auth.example.com/token"
CLIENT_ID      = "my-client"
CLIENT_SECRET  = "my-secret"
# ────────────────────────────────────────────────────────────────────────────


def section_search(client: BrapiClient) -> None:
    print("\n=== POST /search/germplasm ===")

    df = (
        client.germplasm
        .by_crop(["Wheat"])
        .genus(["Triticum"])
        .search()
        .to_df()
    )
    print(f"Records: {len(df)}")
    print(df[["germplasmDbId", "germplasmName", "genus", "species"]].head(5).to_string(index=False))

    # Fork the same base query
    base = client.germplasm.by_crop(["Wheat"])
    t_count = len(base.genus(["Triticum"]).search().to_list())
    h_count = len(base.genus(["Hordeum"]).search().to_list())
    print(f"\nTriticum: {t_count}  |  Hordeum: {h_count}")


def section_list(client: BrapiClient) -> None:
    print("\n=== GET /germplasm ===")

    df = (
        client.germplasm
        .by_crop(["Wheat"])
        .list()
        .to_df()
    )
    print(f"Records: {len(df)}")
    print(df[["germplasmDbId", "germplasmName"]].head(5).to_string(index=False))


def section_crud(client: BrapiClient) -> None:
    print("\n=== CRUD ===")

    # Create
    new_g = Germplasm(
        germplasmDbId="",
        germplasmName="ScriptTest-001",
        germplasmPUI="http://pui.example/script-001",
        commonCropName="Wheat",
        genus="Triticum",
        species="aestivum",
    )
    created = client.germplasm.create(new_g)
    print(f"Created:  {created.germplasmDbId}  {created.germplasmName}")

    # Get by ID
    fetched = client.germplasm.get_by_id(created.germplasmDbId)
    print(f"Fetched:  {fetched.germplasmDbId}  {fetched.germplasmName}")

    # Update
    created.pedigree = "ParentA / ParentB"
    updated = client.germplasm.update(created.germplasmDbId, created)
    print(f"Updated pedigree: {updated.pedigree}")

    # Delete
    ok = client.germplasm.delete(created.germplasmDbId)
    print(f"Deleted:  {ok}")


def section_pipe(client: BrapiClient) -> None:
    print("\n=== Pipe transforms ===")

    def cultivated_only(items):
        return [g for g in items if g.biologicalStatusOfAccessionCode == "100"]

    items = (
        client.germplasm
        .by_crop(["Wheat"])
        .search()
        .pipe(cultivated_only)
        .to_list()
    )
    print(f"Cultivated records: {len(items)}")
    for g in items[:3]:
        print(f"  {g.germplasmDbId}  {g.germplasmName}")


SECTIONS = {
    "search": section_search,
    "list":   section_list,
    "crud":   section_crud,
    "pipe":   section_pipe,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="brapi-py germplasm exploration script")
    parser.add_argument(
        "--section",
        choices=list(SECTIONS),
        default=None,
        help="Run only one section (default: run all)",
    )
    args = parser.parse_args()

    with BrapiClient(
        base_url=BASE_URL,
        token_endpoint=TOKEN_ENDPOINT,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    ) as client:
        if args.section:
            SECTIONS[args.section](client)
        else:
            for fn in SECTIONS.values():
                fn(client)

    print("\nDone.")


if __name__ == "__main__":
    main()
