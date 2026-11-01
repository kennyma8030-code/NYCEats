"""What the extractor took from one comment or post, for inspection.

A debugging aid for the scoring work: the UI swaps a comment's text for this.
It reads `mentions` directly, not `live_mentions`, on purpose: the point is to
see every extraction that ever ran on the item, including the ones the board
is not counting right now.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from .. import queries
from ..db import fetch_all, fetch_one, get_conn
from ..models import ExtractionGroup, ExtractionView
from .ledger import display_name

router = APIRouter()

# Reddit ids are lowercase base36. The pattern keeps the path to what an item
# id can be; the query binds it as a parameter either way.
ItemId = Annotated[str, Path(pattern=r"^t[13]_[0-9a-z]{1,20}$",
                             description="A comment (t1_...) or post (t3_...) id")]

# The two v6 prompts. Anything else is the legacy extractor, whose label is
# the model_version it wrote.
V6_LABELS = {
    "d92ec8610d8c": "v6 thread mode",
    "979dcd6b9267": "v6 comment mode",
}


def label_for(schema_version, prompt_hash, model_version):
    if prompt_hash in V6_LABELS:
        return V6_LABELS[prompt_hash]
    if schema_version == 6:
        return f"v6 ({prompt_hash})"
    return f"legacy {model_version} ({prompt_hash})"


def group_rows(rows):
    """One group per prompt_hash, v6 first, then the most recently written."""
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = groups.setdefault(r["prompt_hash"], {
            "prompt_hash": r["prompt_hash"],
            "schema_version": r["schema_version"],
            "model_version": r["model_version"],
            "label": label_for(r["schema_version"], r["prompt_hash"], r["model_version"]),
            "created_at": r["created_at"],
            "mentions": [],
        })
        m = {k: v for k, v in r.items() if k != "official_name"}
        m["resolved_name"] = (display_name(r["official_name"], r["resolved_key"])
                              if r["resolved_key"] else None)
        g["mentions"].append(m)
    return sorted(groups.values(),
                  key=lambda g: (g["schema_version"] != 6, -g["created_at"].timestamp()))


@router.get("/api/extractions/{item_id}", response_model=ExtractionView,
            summary="What the extractor took from one comment or post")
def extraction(item_id: ItemId, conn=Depends(get_conn)):
    """Every mention row for the item, grouped by the prompt that wrote it.

    v6 groups come first. `state` is the v6 extraction_state row: null means
    the item was never queued, a row with `extracted_at` and no mentions means
    it was read and nothing was found, and `error` means it failed.
    """
    rows = queries.item_mentions(conn, item_id, fetch_all)
    state = queries.extraction_state(conn, item_id, fetch_one)
    return ExtractionView(item_id=item_id, groups=[ExtractionGroup(**g) for g in group_rows(rows)],
                          state=state)
