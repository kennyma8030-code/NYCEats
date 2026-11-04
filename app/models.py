"""Request and response shapes.

Aspect fields are Optional[float] everywhere and must stay that way. A missing
aspect is ABSENT, not 0.0 -- "nobody mentioned the service" and "the service
was mixed" are different answers, and collapsing them is the one thing
SPEC.md says must never happen. Pydantic will happily coerce None to 0.0 if
you let it, so the annotations are load-bearing.
"""

from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypeVar, get_args

from pydantic import BaseModel, Field, field_validator

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
    # v2 only: these columns exist on entity_leaderboard_v2 alone.
    "rank":          "l.rank_score desc nulls last",
    "recent_people": "l.recent_people desc nulls last",
    "sentiment":     "l.sentiment desc nulls last",
    "trend":         "l.trend_pct desc nulls last",
}
V2_SORTS = {"rank", "recent_people", "sentiment", "trend"}
# What each algorithm ranks by when the caller does not say.
DEFAULT_SORT = {"v1": "volume", "v2": "rank"}
SortKey = Literal[
    "volume", "share", "momentum", "mentions", "authors", "longevity",
    "first_seen", "recent", "food", "value", "service", "atmosphere", "wait",
    "rank", "recent_people", "sentiment", "trend",
]
# v1 is scoring.sql (decayed attention, symmetric sentiment); v2 is
# scoring_v2.sql (recent people, negatives 2x, standout-negative flag).
Algo = Literal["v1", "v2"]
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
    # A category, not a name: "omakase", "tasting menu", "french". Matched
    # against thread titles, the commenters' descriptors and dishes, and the
    # city's cuisine label.
    topic: Optional[str] = Field(default=None, max_length=80)
    algo: Algo = "v1"

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

    # None means the algorithm's own default (DEFAULT_SORT).
    sort: Optional[SortKey] = None
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

    # v2 only; None under algo=v1
    recent_people: Optional[int] = None
    recent_reach: Optional[float] = None
    opinion_people: Optional[int] = None
    strong_neg_people: Optional[int] = None
    strong_neg_share: Optional[float] = None
    top_neg_score: Optional[int] = None
    flagged: Optional[bool] = None
    sentiment: Optional[float] = None
    trend_pct: Optional[int] = None
    rank_score: Optional[float] = None
    # people in the last two years who mentioned it under the searched topic
    topic_people: Optional[int] = None


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


# The rating (scoring.sql, section 8). v6's categories, which are not the
# legacy aspects: "taste" is the food.
# The tuples are read off the Literals (get_args flattens nested ones), so a
# value added to a Literal reaches the whitelists without a second list.
RatingCategory = Literal["taste", "value", "service", "atmosphere", "wait"]
RATING_CATEGORIES = get_args(RatingCategory)
# Each board ranks by one value and filters on the rest; no composite score.
# top, popular and gems rank on the overall rating; the rest on a category's.
OverallBoard = Literal["top", "popular", "gems"]
OVERALL_BOARDS = get_args(OverallBoard)
RatingBoard = Literal[OverallBoard, RatingCategory]
Badge = Literal["consensus", "overhyped_mixed", "hidden_gem"]
# Which voices to list behind a rating (/voices).
#   pos, neg, neutral   latest stated opinions; opinions = pos and neg together
#   superlative         pos at level 2
#   endorse             people whose latest word is a bare endorse
#   recommenders        people whose latest word is an endorse or a stated pos
#   all                 every person, by their latest word
# With a category only the stated ones and all apply: a category has no bare
# endorsements.
CategoryVoiceFilter = Literal["pos", "neg", "neutral", "opinions", "all"]
CATEGORY_VOICE_FILTERS = get_args(CategoryVoiceFilter)
VoiceFilter = Literal[CategoryVoiceFilter, Literal["superlative", "endorse", "recommenders"]]
VOICE_FILTERS = get_args(VoiceFilter)


class CategoryRating(BaseModel):
    """One category's rating: each person's latest stated level, by sign."""
    pos: int
    neg: int
    neutral: int
    pct_pos: Optional[float] = None   # None when nobody was positive or negative
    lb: Optional[float] = None        # Wilson lower bound of pct_pos
    rankable: bool                    # pos + neg >= min_category_rated


class Rating(BaseModel):
    """How much the sub likes a place, apart from how many bring it up.

    Counts are people over the window. pos, neg, neutral and superlative
    count each person's latest STATED opinion and make the rating; a bare
    endorse never changes it. endorse and recommenders count each person's
    latest word, stated or endorse: the volume axis. So recommenders is not
    pos + endorse -- someone who praised a place and later only named it is
    one pos and one recommender.
    """
    window_days: int
    pos: int
    neg: int
    neutral: int
    endorse: int                      # latest word a bare endorse
    superlative: int                  # latest stated level 2: called it the best
    recommenders: int                 # latest word an endorse or a stated pos
    pct_pos: Optional[float] = None   # pos / (pos + neg)
    lb: Optional[float] = None        # Wilson lower bound of pct_pos
    neg_share: Optional[float] = None  # neg / (pos + neg + neutral)
    rankable: bool                    # pos + neg >= min_rated
    busy: bool
    badge: Optional[Badge] = None
    last_voice: Optional[datetime] = None
    categories: dict[str, CategoryRating] = Field(default_factory=dict)


class RatingLines(BaseModel):
    """The settings and the percentile cut-offs the badges were made with,
    so a client can say what "busy" or "hidden gem" meant at this rebuild."""
    window_days: int
    z: float
    min_rated: int
    min_category_rated: int
    busy_pct: float
    share_pct: float
    gem_pct: float
    busy_line: Optional[int] = None    # recommenders at or above this are busy
    share_line: Optional[float] = None  # median lb
    gem_line: Optional[float] = None   # lb a non-busy place needs to be a gem


class RestaurantDetail(BaseModel):
    entity_key: str
    summary: LeaderboardRow
    # None when nobody voiced an opinion or recommendation in the window.
    rating: Optional[Rating] = None
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
    # Set only by /voices: what this mention counted as (pos, neg, neutral,
    # endorse) and the level it carried (overall, or the category's).
    voice: Optional[str] = None
    level: Optional[int] = None

    # The SQL already nulls a jsonb column of the wrong shape
    # (queries.MENTION_COLUMNS). These hold the same line for any query that
    # does not go through it, because one malformed row 500ing a whole page
    # of evidence is worse than that row showing no tags.
    @field_validator("dishes", "descriptors", mode="before")
    @classmethod
    def _list_or_none(cls, v):
        return v if isinstance(v, list) else None

    @field_validator("aspects", mode="before")
    @classmethod
    def _aspects_or_none(cls, v):
        if not isinstance(v, dict):
            return None
        # A non-numeric score is unmeasured, never 0.0 (module docstring).
        return {k: (float(x) if isinstance(x, (int, float)) and not isinstance(x, bool)
                    else None)
                for k, x in v.items()}


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


LedgerCategory = Literal["trending", "top", "gems"]
LedgerWindow = Literal[7, 14, 30, 90, 180, 365]
LedgerNeed = Literal["value", "atmosphere", "service", "wait"]
# The aspect a place does badly on. Food is included here though not in
# LedgerNeed: "known for good food" says nothing on a food board, but
# "people complain about the food" does.
LedgerFlaw = Literal["food", "value", "service", "atmosphere", "wait"]
# v1 is scoring.sql; v2 is scoring_v2.sql (recent people, negatives 2x,
# standout-negative flag). Both are built by refresh.py.
Algo = Literal["v1", "v2"]


class LedgerAspects(BaseModel):
    # Optional for the same reason as everywhere else: absent is not 0.0.
    food: Optional[float] = None
    value: Optional[float] = None
    service: Optional[float] = None
    atmosphere: Optional[float] = None
    wait: Optional[float] = None


class LedgerItem(BaseModel):
    """One ranked row. `series` and `previous_series` are the same length,
    oldest bucket first, so a client can draw both on one x axis."""
    entity_key: str
    name: str
    cuisine: Optional[str] = None
    borough: Optional[str] = None
    boroughs: Optional[list[str]] = None
    neighborhood: Optional[str] = None
    current: int
    previous: int
    change_pct: Optional[int] = None
    series: list[int]
    previous_series: list[int]
    total_mentions: int
    distinct_authors: Optional[int] = None
    aspects: LedgerAspects
    sentiment: Optional[float] = None
    # v2 only; None under v1
    people: Optional[int] = None              # distinct commenters in the window
    flagged: Optional[bool] = None
    strong_neg_people: Optional[int] = None   # last two years
    strong_neg_share: Optional[float] = None  # of recent, upvote-weighted opinion
    # The rating over its own fixed window (rating_params.window_days), the
    # same under every algo and ledger window. None when nobody voiced an
    # opinion or recommendation in that window.
    rating: Optional[Rating] = None


class FeedPlace(BaseModel):
    key: str
    name: str


class FeedItem(BaseModel):
    """One post or comment in the stream. `cursor` is opaque: pass it back as
    before= for older items or after= for newer ones. `title` is the post's
    own title for a post, and the thread it is in for a comment."""
    kind: Literal["post", "comment"]
    id: str
    cursor: str
    author: Optional[str] = None
    score: Optional[int] = None
    created_utc: datetime
    body: str
    permalink: Optional[str] = None
    was_deleted_later: bool = False
    title: Optional[str] = None
    num_comments: Optional[int] = None        # posts only
    places: list[FeedPlace]


class Feed(BaseModel):
    items: list[FeedItem]


class Ledger(BaseModel):
    category: LedgerCategory
    window_days: int
    bucket_days: int
    # Every filter these rows were ranked under, echoed back, so a client can
    # tell a stale list from a current one and never show one under the
    # other's heading.
    algo: Algo = "v1"
    topic: Optional[str] = None
    cuisine: Optional[str] = None
    borough: Optional[str] = None
    needs: list[str] = Field(default_factory=list)
    flaws: list[str] = Field(default_factory=list)
    total: int
    items: list[LedgerItem]


class Board(BaseModel):
    """A board ranked by the rating (/api/boards). Items are ledger rows with
    `rating` always set; `window_days` is only the window their counts and
    series cover, never what they were ranked on (that is lines.window_days)."""
    board: RatingBoard
    window_days: int
    bucket_days: int
    cuisine: Optional[str] = None
    borough: Optional[str] = None
    lines: RatingLines
    total: int
    limit: int
    offset: int
    items: list[LedgerItem]
