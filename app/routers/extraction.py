"""What the extractor took from one comment or post, for inspection.

A debugging aid for the scoring work: the UI swaps a comment's text for this.
Only the v6 thread-mode prompt is shown, the extraction the scoring work is
built on; comment-mode and legacy rows are left out so they don't clutter the
view. It reads `mentions` directly, not `live_mentions`, so the rows show
whether or not the board counts them right now.

Each city's items are read with that city's own thread prompt, under its own
hash (prompt_v6.prompt_for), so the route takes `?subreddit=` like every
other (app/city.py) and shows the rows of that city's prompt.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

import prompt_v6

from .. import queries
from ..city import Sub
from ..db import fetch_all, fetch_one, get_conn
from ..models import ExtractionGroup, ExtractionView
from .ledger import display_name

router = APIRouter()

# Reddit ids are lowercase base36. The pattern keeps the path to what an item
# id can be; the query binds it as a parameter either way.
ItemId = Annotated[str, Path(pattern=r"^t[13]_[0-9a-z]{1,20}$",
                             description="A comment (t1_...) or post (t3_...) id")]

# Every v6 prompt in use, each city's under its own hash. Anything else is
# the legacy extractor, whose label is the model_version it wrote.
V6_LABELS = {ph: f"v6 {mode} mode" for ph, (mode, _) in prompt_v6.all_hashes().items()}


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
def extraction(item_id: ItemId, sub: Sub, conn=Depends(get_conn)):
    """The item's v6 thread-mode mention rows, as one group.

    `state` is the v6 extraction_state row: null means
    the item was never queued, a row with `extracted_at` and no mentions means
    it was read and nothing was found, and `error` means it failed. An item
    of another city than the one asked for has neither.
    """
    # The prompt whose rows the view shows: the city's own v6 thread mode.
    _, thread_hash = prompt_v6.thread_prompt(sub)
    rows = queries.item_mentions(conn, sub, item_id, fetch_all, thread_hash)
    state = queries.extraction_state(conn, sub, item_id, fetch_one)
    return ExtractionView(item_id=item_id, groups=[ExtractionGroup(**g) for g in group_rows(rows)],
                          state=state)
