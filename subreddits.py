"""Which subreddits we collect, and which one is the default.

Every city lands in the same threads/comments tables, told apart by their
`subreddit` column, and every reader that treats `comments` as "the
subreddit" filters on it first -- without that, Chicago's chatter would
inflate NYC's activity denominator and LA's "joes pizza" would be scored as
NYC's. Collecting a city is cheap; extracting one is paid for, so a city is
extracted only when a run names it (EXTRACT_SUBREDDITS). Scoring follows
the mentions: every subreddit that has them gets its own board, with a place
keyed by (subreddit, name) (scoring.sql).

HOME is the city everything began with and still the default: what the API
answers for when no subreddit is named, the only one embedded, and the one
whose restaurant list is the `restaurants` table. SQL cannot import this,
so the places view (scoring.sql) and the column defaults in schema.sql
carry their own copy of the name. Change all or none
(tests/test_home_literal.py).

Names are spelled exactly as Arctic Shift returns them in `subreddit`, which
is what ends up in the column -- "austinfood", not "AustinFood".
"""

from collections import namedtuple

HOME = "FoodNYC"

# The seven largest city food subreddits by subscribers, as of 2026-10.
# HOME first: the poller and the boot backfill both walk this in order, and
# the board's own city should never queue behind a six-hour history sweep.
SUBREDDITS = (
    HOME,
    "FoodLosAngeles",
    "FoodSanDiego",
    "austinfood",
    "chicagofood",
    "denverfood",
    "FoodToronto",
)


# What a subreddit's posts and comments are about. The subreddit is the fact
# stored on every row; this is the conclusion drawn from it, in one place, so
# nothing else has to know that r/austinfood means Austin. The extraction
# prompt is written from it (prompt_v6.thread_prompt):
#   name      the city as a sentence names it: "a Chicago food subreddit"
#   short     as a commenter writes it: "my favorite in LA"
#   area      what counts as in the city: a place outside it is not a mention.
#             Each food subreddit covers its metro area, not the city limits
#   district  a part of it, for the prompt's example post ("Best noodles in ...?")
City = namedtuple("City", "name short area district")

CITIES = {
    "FoodNYC": City("New York City", "NYC", "the five boroughs", "Queens"),
    "FoodLosAngeles": City("Los Angeles", "LA", "the Los Angeles area", "the San Gabriel Valley"),
    "FoodSanDiego": City("San Diego", "San Diego", "the San Diego area", "Convoy"),
    "austinfood": City("Austin", "Austin", "the Austin area", "East Austin"),
    "chicagofood": City("Chicago", "Chicago", "the Chicago area", "Pilsen"),
    "denverfood": City("Denver", "Denver", "the Denver area", "Aurora"),
    "FoodToronto": City("Toronto", "Toronto", "the Toronto area", "Scarborough"),
}
assert set(CITIES) == set(SUBREDDITS), "every collected subreddit needs a city, and only those"


def city(subreddit):
    """The city a subreddit is about. An unknown name is an error, not NYC:
    a comment from a city nobody described must not be read as New York's."""
    try:
        return CITIES[subreddit]
    except KeyError:
        raise ValueError(f"no city is defined for r/{subreddit}: add it to subreddits.CITIES") from None


def parse(value, default):
    """Subreddit names from a comma-separated setting, in SUBREDDITS order.

    For POLL_SUBREDDITS and BACKFILL_SUBREDDITS. Unset or blank is
    `default`; "all" is every one. Matched case-insensitively and returned
    in the spelling above, because the stored column and every filter use
    that spelling. An unknown name fails the boot: a typo here would
    otherwise quietly stop collecting a city.
    """
    if value is None or not value.strip():
        return list(default)
    if value.strip().lower() == "all":
        return list(SUBREDDITS)
    known = {s.lower(): s for s in SUBREDDITS}
    wanted = set()
    for part in value.split(","):
        name = part.strip().removeprefix("r/").lower()
        if not name:
            continue
        if name not in known:
            raise SystemExit(f"unknown subreddit {part.strip()!r}: expected 'all' or some of "
                             f"{', '.join(SUBREDDITS)}")
        wanted.add(known[name])
    return [s for s in SUBREDDITS if s in wanted]
