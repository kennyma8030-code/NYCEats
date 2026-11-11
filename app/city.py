"""Which city a request is about.

Every city collected lands in the same tables and is scored in the same views
(subreddits.py, scoring.sql), told apart by subreddit. So every route takes
`?subreddit=`, and a route that leaves it out means r/FoodNYC, which is what
every link and client from before there was a second city means.
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Query

import subreddits


def subreddit_param(
    subreddit: Annotated[Optional[str], Query(max_length=40, description=(
        "The city's subreddit: one of " + ", ".join(subreddits.SUBREDDITS)
        + ". Defaults to " + subreddits.HOME + ". /api/cities lists the ones "
        "that have a board"))] = None,
) -> str:
    """The subreddit a request names, in the spelling the tables store.

    Matched case-insensitively, like the poller's settings (subreddits.parse),
    because the stored column and every filter use one spelling. An unknown
    name is a 422, not r/FoodNYC: answering a typo with New York's numbers
    would be a wrong answer that looks right.
    """
    if subreddit is None or not subreddit.strip():
        return subreddits.HOME
    known = {s.lower(): s for s in subreddits.SUBREDDITS}
    name = subreddit.strip().removeprefix("r/").lower()
    if name not in known:
        raise HTTPException(status_code=422,
                            detail=f"unknown subreddit {subreddit.strip()!r}: expected one of "
                                   f"{', '.join(subreddits.SUBREDDITS)}")
    return known[name]


Sub = Annotated[str, Depends(subreddit_param)]
