"""How each thread's question frames a bare name (contract rule 2).

Most threads ask for places to go, so a bare name there is an endorsement and
needs no entry. This file lists the threads whose post carries a judgment
(a bare name inherits it) and the threads that ask for neither (a bare name is
reference_only). The per-mention results live in overrides.py with
judgment_question=True or reference_only=True; this table is what the review
classified, and the diversity audit counts from it.

The levels are what the question's own words carry on the scale ("worst"
is awful, "terrible" and "nasty" are bad, "overrated" is meh).

kind:
    judgment  the question carries a negative or aspect-specific judgment
    mixed     it asks for both a judgment and a recommendation ("overhyped,
              and where to go instead"): each name is read for its role
    neither   the post asks for no places (news, a review, a discussion)
"""

THREADS = {
    "t3_1pitzh7": ("judgment", "If you could close one NYC restaurant for good...", {"food": "bad"}),
    "t3_14xbgpd": ("judgment", "List of terrible restaurants in NYC with great customer reviews", {"food": "bad"}),
    "t3_1huk7w4": ("judgment", "Name a place to eat thats nasty af but people hype tf out of it", {"food": "bad"}),
    "t3_1p0y1bv": ("judgment", "Poor quality yet expensive restaurant recommendation to give to an enemy", {"food": "bad", "value": "bad"}),
    "t3_1ta2nri": ("judgment", "What is the most overrated or overpriced piece of pizza you've had?", {"food": "meh"}),
    "t3_1dpao5m": ("judgment", "What's the worst food you've had in NYC?", {"food": "awful"}),
    "t3_1t2rzp7": ("judgment", "Take two: trying to design the worst date possible for irony", {"atmosphere": "awful"}),
    "t3_1o5qhq9": ("judgment", "The best food with the worst vibes", {"food": "rave", "atmosphere": "awful"}),
    "t3_1rxlujb": ("mixed", "Places You Think Are Over-hyped & Where You Would Recommend Going Instead", {"food": "meh"}),
    "t3_1oebqm6": ("mixed", "Restaurant regrets... I've had a few", {}),
}

