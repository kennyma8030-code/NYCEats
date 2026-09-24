"""Request and response shapes.

Aspect fields are Optional[float] everywhere and must stay that way. A missing
aspect is ABSENT, not 0.0 -- "nobody mentioned the service" and "the service
was mixed" are different answers, and collapsing them is the one thing
SPEC.md says must never happen. Pydantic will happily coerce None to 0.0 if
you let it, so the annotations are load-bearing.
"""

from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

ASPECTS = ("food", "value", "service", "atmosphere", "wait")

# Whitelisted because they are interpolated into ORDER BY, where a bound
# parameter is not allowed. Nothing the caller types reaches the SQL.
SORTS = {
    "volume":     "l.decayed_volume desc nulls last",
    "share":      "l.volume_share desc nulls last",
    "momentum":   "l.momentum_sigma desc nulls last",
    "mentions":   "l.raw_mentions desc nulls last",
    "authors":    "l.distinct_authors desc nulls last",
    "longevity":  "l.months_active desc nulls last",
    "first_seen": "l.first_seen asc nulls last",
    "recent":     "l.last_seen desc nulls last",
    "food":       "l.food desc nulls last",
    "value":      "l.value desc nulls last",
    "service":    "l.service desc nulls last",
    "atmosphere": "l.atmosphere desc nulls last",
    "wait":       "l.wait desc nulls last",
}
SortKey = Literal[
    "volume", "share", "momentum", "mentions", "authors", "longevity",
    "first_seen", "recent", "food", "value", "service", "atmosphere", "wait",
]
AspectKey = Literal["food", "value", "service", "atmosphere", "wait"]
MentionSort = Literal["recent", "oldest", "score"]

T = TypeVar("T")


class LeaderboardQuery(BaseModel):
    """Validated leaderboard filters.

    There is no default ranking here beyond the sort key. A leaderboard is
    (sort x filters), not a fixed list, so the caller always says which one
    they want and the defaults only pick the least surprising starting point.
    """
    search: Optional[str] = Field(default=None, max_length=100)
    cuisine: Optional[str] = Field(default=None, max_length=100)
    borough: Optional[str] = Field(default=None, max_length=40)
    status: Optional[Literal["exact", "fuzzy", "unlisted", "unverified"]] = None
    descriptor: Optional[str] = Field(default=None, max_length=80)

    hide_chains: bool = True
    include_closed: bool = False
    rising: bool = False

    min_mentions: Optional[int] = Field(default=None, ge=0, le=100_000)
    min_authors: Optional[int] = Field(default=None, ge=0, le=100_000)

    min_food: Optional[float] = Field(default=None, ge=-1, le=1)
    min_value: Optional[float] = Field(default=None, ge=-1, le=1)
    min_service: Optional[float] = Field(default=None, ge=-1, le=1)
    min_atmosphere: Optional[float] = Field(default=None, ge=-1, le=1)
    min_wait: Optional[float] = Field(default=None, ge=-1, le=1)

    sort: SortKey = "volume"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MentionQuery(BaseModel):
    aspect: Optional[AspectKey] = None
    negated: Optional[bool] = None
    firsthand: Optional[bool] = None
    include_deleted: bool = True
    sort: MentionSort = "recent"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    """Envelope for every list endpoint.

    `total` is the count BEFORE limit/offset, so a client can page without
    guessing. There is deliberately no `rank` field: position is a property of
    a query, not of a restaurant, so it is computed per response by whoever
    renders it.
    """
    items: list[T]
    total: int
    limit: int
    offset: int


class AspectDetail(BaseModel):
    """One (entity, aspect) pair, with the workings shown.

    raw_mean is what the mentions actually said; aspect_score is that shrunk
    toward city_mean by the pseudo-count. Exposing all three lets the UI
    explain a number instead of asserting it.
    """
    aspect: str
    n_obs: int
    aspect_weight: Optional[float] = None
    raw_mean: Optional[float] = None
    city_mean: Optional[float] = None
    aspect_score: Optional[float] = None


class MomentumWindow(BaseModel):
    window_days: int
    sigma: Optional[float] = None
    recent_volume: Optional[float] = None
    baseline_volume: Optional[float] = None
    expected: Optional[float] = None
    fired: bool = False


class LeaderboardRow(BaseModel):
    entity_key: str

    # volume
    raw_mentions: Optional[int] = None
    decayed_volume: Optional[float] = None
    volume_share: Optional[float] = None

    # confidence
    distinct_authors: Optional[int] = None
    firsthand_mentions: Optional[int] = None
    negated_mentions: Optional[int] = None

    # momentum
    momentum_sigma: Optional[float] = None
    momentum_window_days: Optional[int] = None
    momentum_fired: Optional[bool] = None

    # longevity
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    months_active: Optional[int] = None
    longest_gap_months: Optional[int] = None

    # aspects -- Optional is deliberate, see module docstring
    food: Optional[float] = None
    value: Optional[float] = None
    service: Optional[float] = None
    atmosphere: Optional[float] = None
    wait: Optional[float] = None

    # the official record, when the name matched one
    official_name: Optional[str] = None
    cuisine: Optional[str] = None
    boroughs: Optional[list[str]] = None
    is_chain: Optional[bool] = None
    closed: Optional[bool] = None
    location_count: Optional[int] = None

    # how confident we are that this name IS that restaurant
    status: Optional[str] = None
    fuzzy_match: Optional[str] = None
    fuzzy_score: Optional[float] = None


class SearchHit(BaseModel):
    entity_key: str
    display_name: Optional[str] = None
    raw_mentions: Optional[int] = None
    cuisine: Optional[str] = None


class Spelling(BaseModel):
    """A typed name that resolved into this entity, and how it got there."""
    entity_key: str
    method: str
    score: Optional[float] = None
    mentions: Optional[int] = None


class RestaurantDetail(BaseModel):
    entity_key: str
    summary: LeaderboardRow
    aspects: list[AspectDetail]
    momentum: list[MomentumWindow]
    spellings: list[Spelling]
    addresses: Optional[list[dict[str, Any]]] = None
    top_dishes: list[dict[str, Any]] = Field(default_factory=list)
    top_descriptors: list[dict[str, Any]] = Field(default_factory=list)
    neighborhoods: list[dict[str, Any]] = Field(default_factory=list)


class Mention(BaseModel):
    """One piece of evidence. `permalink` is None when the comment was deleted
    from Reddit -- the UI must never link something that 404s (SPEC.md,
    Non-negotiable)."""
    mention_id: int
    comment_id: str
    restaurant_raw: str
    typed_key: str
    aspects: Optional[dict[str, Optional[float]]] = None
    dishes: Optional[list[Any]] = None
    descriptors: Optional[list[Any]] = None
    expensiveness: Optional[float] = None
    is_firsthand: Optional[bool] = None
    is_negated: bool = False
    neighborhood_hint: Optional[str] = None
    author: Optional[str] = None
    score: Optional[int] = None
    controversiality: Optional[int] = None
    created_utc: Optional[datetime] = None
    body: Optional[str] = None
    permalink: Optional[str] = None
    was_deleted_later: bool = False
    thread_id: Optional[str] = None
    thread_title: Optional[str] = None


class FacetValue(BaseModel):
    name: str
    n: int


class Facets(BaseModel):
    cuisines: list[FacetValue]
    boroughs: list[FacetValue]
    statuses: list[FacetValue]
    descriptors: list[FacetValue]


class Stats(BaseModel):
    mentions: int
    entities: int
    comments: int
    extracted: int
    threads: int
    models: Optional[str] = None
    newest_comment: Optional[datetime] = None


class Health(BaseModel):
    status: str
    database: bool
    views_populated: dict[str, bool]
    leaderboard_rows: Optional[int] = None
    detail: Optional[str] = None


class ImageOut(BaseModel):
    entity_key: str
    status: str                      # found | none
    url: Optional[str] = None
    source: Optional[str] = None
    # The upstream id behind the match (a Wikidata QID), so a wrong picture is
    # traceable to the entity that produced it rather than merely replaced.
    source_ref: Optional[str] = None
    attribution: Optional[str] = None
    license: Optional[str] = None
    source_url: Optional[str] = None
    fetched_at: Optional[datetime] = None


class AliasIn(BaseModel):
    """A human decision about identity.

    Set resolved_key == entity_key to mean "never merge this one" -- the
    cote / cote wine bar case word_similarity scores at a confident 1.00 and
    is simply wrong about (schema.sql, alias_overrides).
    """
    entity_key: str = Field(min_length=1, max_length=200)
    resolved_key: str = Field(min_length=1, max_length=200)
    note: Optional[str] = Field(default=None, max_length=500)


class AliasOut(BaseModel):
    entity_key: str
    resolved_key: str
    note: Optional[str] = None
    created_at: Optional[datetime] = None


class UnresolvedRow(BaseModel):
    entity_key: str
    mentions: int
    distinct_authors: Optional[int] = None
    threads: Optional[int] = None
    status: Optional[str] = None
    fuzzy_match: Optional[str] = None
    fuzzy_score: Optional[float] = None


class JobAccepted(BaseModel):
    job: str
    started: bool
    detail: Optional[str] = None
