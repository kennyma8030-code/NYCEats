"""Which subreddits we collect, and which one the board is about.

Every city lands in the same threads/comments tables, told apart by their
`subreddit` column. Collecting a city is cheap and safe; scoring one is not.
Only HOME has a restaurant list to resolve names against (the health
department's), so only HOME is extracted, counted and ranked. Every reader
that treats `comments` as "the subreddit" filters on it first -- without
that, Chicago's chatter would inflate NYC's activity denominator and LA's
"joes pizza" would be scored as NYC's.

scoring.sql cannot import this, so it carries its own copy of HOME in
scoring_params. Change both or neither.

Names are spelled exactly as Arctic Shift returns them in `subreddit`, which
is what ends up in the column -- "austinfood", not "AustinFood".
"""

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
