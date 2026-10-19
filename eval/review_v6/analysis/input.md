# What Haiku is shown: an audit of the comment-mode input

Scope: the user message production builds for one comment (`prompt.build_user_message`,
also what the v6 round-3 run used: `v6_comment.py` has no `build_user_message` of its own,
so `eval/run.py` sends production's stored rendering), checked against the Opus review
(`eval/review_v6/judgments`, 542 real items; the 58 planted or round-1 items in
`.sealed/key.json` are left out) and read-only queries on production (685,115 eligible
comments, i.e. not deleted and longer than 15 characters; 43,723 threads).

The message today is four plain-text sections: `POST TITLE:`, `POST BODY:` (first 400
characters, original whitespace, `" ..."`), `PARENT COMMENT:` (immediate parent only,
untruncated, omitted when deleted or missing), `COMMENT:`. No authors, no grandparent,
no dates, no sign that the post is a photo.

Measured cost baseline (round-3 run, 600 calls): 5,042 input tokens per call on average,
of which about 4,830 are the fixed system prompt and schema and about 210 are the user
message. The tokenizer ran at 2.9 characters per token on these inputs; every token
estimate below uses that.

## 1. Review errors that come from the input

262 of 542 items were not fully right; 39 mentions were missed and 25 extracted that
should not have been. Three input-related groups account for 40 failing items (15%) and,
more tellingly, **28 of the 39 missed mentions (72%)**.

| group | items | failing | what went wrong |
|---|---:|---:|---|
| A. needed context Haiku never saw | 20 | 19 | the place is named above the parent or past the 400-character cut; 18 missed mentions |
| B. context bled into the comment | 13 | 12 | a place or a claim from the title, body or parent was filed as this comment's; 8 of the 25 false-positive mentions |
| C. visible referent not attached | 10 | 10 | the parent or title named the place, the reply judged it, Haiku dropped it; 10 missed mentions |

**A, needs wider context** (judge marked `neither`, "needs wider context"): Q0071 Q0074
Q0095 Q0096 Q0112 Q0125 Q0150 Q0152 Q0193 Q0196 Q0270 Q0292 Q0359 Q0360 Q0397 Q0494
Q0535 Q0545 Q0549 Q0556 (Q0320 is the same kind but is a round-1 substitute, so it is
excluded). Where the referent sits:

- grandparent: 13 of 20 (Q0071 Q0096 Q0112 Q0125 Q0193 Q0196 Q0270 Q0397 Q0494 Q0535
  Q0545 Q0549 Q0556);
- 3 to 5 levels up only: 6 (Q0074 Q0095 Q0152 Q0292 Q0359 Q0360);
- post body past 400 characters: 2 (Q0150 only; Q0397 also has it in the grandparent);
- **the commenter's own earlier comment in the chain: 11 of 20** (Q0096 Q0112 Q0125
  Q0196 Q0292 Q0359 Q0397 Q0494 Q0535 and two where it is one of several sources). The
  typical shape is A names a place, B pushes back, A replies "it's still better than
  that" with no name.
- deleted parent: 0 (the sample happens to contain none; see section 2).
- `>` quotes from another user: 3 items carried a quote, all judged right. No errors.
- edited text, removed text, non-English: no errors found.

**B, context bleed** (judge's reasons quoted where useful):

- post-body places attached to a reply that never mentions them: Q0357 (Oases, Sweet
  Greens; the poster's fried-tofu complaint became the commenter's note), Q0560 (Oases);
- title subject attached to a general remark: Q0206 (restaurant economics, El Califa de
  Leon), Q0232 (grade-card rules, Semma), Q0473 (vegan naming, Pressed Juicery), Q0544
  (Los Tacos from the title instead of the parent's Tacos El Bronco);
- title or parent claims recorded as the comment's: Q0224 (roaches and refused refund
  from the title, service very_negative), Q0516 (parent's "allegedly reopening" became
  status opened), Q0367 (the asker's "best" became very_positive), Q0542 (a reaction to
  the OP's story marked firsthand), Q0175 and Q0465 (note, location from context);
- wrong referent between parent and post: Q0550 (praise went to the parent's Fedoroffs,
  belongs to the post's Mama's Too).

Six of the eight false positives are opinion "none" mentions of the post's subject. The
prompt invites this ("A place named only in the context counts when the comment says
anything about it, a question included"), so labels alone will not remove them.

**C, visible but missed**: Q0054 Q0087 Q0116 Q0134 Q0238 Q0308 Q0352 Q0364 Q0491 Q0550.
Four of the ten referents are named only in the title (Q0134 Q0352 Q0364, and Q0550's
Mama's Too in the post).

**Who wrote what.** Ten more failing items hinge on knowing the commenter is the post's
author (52 of 542 items are OP comments): Q0004 Q0007 Q0063 Q0313 (the asker thanking or
planning, read as endorse or secondhand), Q0116 Q0364 (the asker's follow-up question or
plan, missed), Q0150 (OP referring to "it" in their own post past the cut), Q0143 (OP
who "loves this place"), Q0224 ("I did" file a 311 complaint: if the commenter is the
OP, the roach claims in the title *are* theirs, so the judge's own ruling may be wrong).
Comment mode never says who wrote anything, though `threads.author` and
`comments.author` are stored.

**Photo posts.** Q0025 Q0033 Q0542 (and Q0583, judged right) react to the OP's photo
("looks tasty", "Lovely!"). The model cannot tell a photo post from a text post, and the
recurring rule question on untried "looks good" reactions comes from the same gap.

## 2. How often these situations occur in production

Shares are of the 685,115 eligible comments unless stated.

| situation | share | comments |
|---|---:|---:|
| top-level | 49.5% | |
| reply to a top-level comment (depth 1) | 25.7% | |
| depth 2 or more (grandparent exists) | 24.8% | |
| **depth 2+ and the grandparent is the commenter's own comment** | **13.0%** (52% of depth-2+) | ~89k |
| depth 2+, no place in comment or parent, one in grandparent or great-grandparent (v4 `deep_chain_context_gap`) | 4.5% | 31,152 |
| stored mentions on depth-2+ comments whose name occurs only in the grandparent | 1,206 of 5,307 mentions not named in the comment (23%) | |
| parent `[deleted]`/`[removed]` (section silently omitted) | 0.57% | ~3,900 |
| grandparent deleted | 0.17% | |
| parent missing from DB | 0.04% | |
| parent ≤ 40 chars / ≤ 15 chars | 17.7% / 4.4% | |
| commenter is the post's author | 9.4% | |
| parent is the post's author | 5.4% | |
| post body empty (photo, link or title-only post) | 11.2% | |
| post body > 400 chars (cut) / > 800 | 34.4% / 14.4% | 10,036 / 3,245 threads |
| post body past 400 names a known place not in title or first 400 (gazetteer, upper bound) | 17.5% of comments, 10.9% of threads | |
| title names a known place (gazetteer, upper bound) | 37% | |
| `>` quote block in the comment | 0.57% | 3,899 |
| ... where the quoted text is found in the parent / in the post / in neither (first quote line, 25-char match; the rest too short to test) | 56% / 15% / 16% | |
| ... quote blocks in top-level comments (so quoting the post or an outside source) | 24% | 932 |
| comment > 700 / > 1,500 chars | 1.7% / 0.23% | |
| URL in comment / markdown link | 3.0% / 2.2% | |
| bullet or numbered list | 0.8% | |
| "edit:" line | 0.10% (any "edit" word 0.17%) | |
| CJK characters / mostly non-ASCII | 0.07% / 0.01% | |
| HTML entities (`&amp;`, `&gt;`) | 0.03% | |

**The 15-character filter** (`next_batch`, also thread mode) drops 67,223 comments
before any model sees them:

- 38,779 top-level. 17,995 of them are *exactly* a known place name (gazetteer of
  entity keys with 8+ mentions): "keens" 109, "balthazar" 81, "gramercy tavern" 80,
  "minetta tavern" 70, "rubirosa" 62... These are the bare-name answers the prompt calls
  the majority case, and none is ever extracted.
- 28,444 replies. 2,642 are agreement replies ("this", "agreed", "second this", "+1",
  "100%"), which v6 rule 9 tells the model how to score, and ~1,160 more carry an
  opinion word ("so good", "mid", "overrated", "rip"). 1,432 are a bare place name.

For scale, production holds 149,307 stored mentions over the 205,452 comments extracted
so far.

Two stale claims: `prompt.py` and `extract.next_batch` say 70% of comments are
top-level; it is 49.5% of eligible comments. And no stored parent carries
`was_deleted_later`, so that flag never affects the input.

## 3. Input-format proposals, cost and expected yield

Token costs are averages per eligible comment, from production lengths at 2.9 chars per
token. A call is ~5,040 input tokens, so +25 tokens is +0.5% of input (or about +12% of
the uncached part, if the system prompt is cached). "Fixes" counts review items out of
542 and is an upper bound until a re-run confirms it.

| # | proposal | tokens per comment | review items it addresses |
|---|---|---:|---|
| 1 | Labelled sections: `<post_title>`, `<post_body>`, `<parent_comment>`, `<earlier_comments>`, `<comment_to_extract>`, with one sentence: "Only `<comment_to_extract>` is extracted; everything else was written by other people (or earlier by this commenter) and is context." | +15 to 20 | B (13 items, 8 false positives): perhaps a third to a half; the "none"-mention bleed also needs a rule change (below) |
| 2 | Always send the grandparent, cut at 300 chars | +14 (34 chars avg; 0 for the 75% with no grandparent) | 13 of 20 A items, ~11 of 39 missed mentions |
| 2b | Grandparent only when the parent is ≤ 100 chars | +5 | 7 of those 13. Parent length is a weak signal (Q0112 Q0125 Q0196 Q0270 Q0397 Q0556 had parents of 150 to 260 chars), so prefer 2 |
| 3 | Full ancestor chain up to 5 levels, each cut at 300, oldest first | +28 (68 chars avg incl. labels ~+5) | 19 of 20 A items, ~17 of 39 missed mentions |
| 4 | Authorship markers, no usernames: `(OP)` on the post and on any OP comment, `(you, earlier)` on ancestors by the same commenter, and "the commenter wrote the post" when true | +3 to 6 | the 9 OP-identity items, and makes 3 usable for the 11 same-author chains |
| 5 | Say a deleted parent is deleted: `<parent_comment>[deleted]</parent_comment>` instead of omitting it | ~+5 on 0.57% of comments | 0 in the sample; stops a reply to a deleted comment from looking top-level, where "this place" gets pinned on the title |
| 6 | Mark `>` quote lines as `<quote from="parent">...</quote>` (or "post"/"other") | ~0 (+10 on 0.57%) | 0 in the sample; protects against quoted praise being filed as the commenter's, and keeps the useful signal that a quote names which list item the reply judges |
| 7 | Post body limit 400 → 800 | +31 | 1 (Q0150; Q0397 is also fixed by 2). Low yield per token |
| 7b | Instead of a longer body: a "places named in the post" line, from one post-mode call per thread (`SYSTEM_PROMPT_POST` already exists) or the gazetteer | +8 to 12, plus one call per thread | the same 2 items, and covers the 17.5% of comments whose thread names a place past the cut |
| 8 | Per-place grounding: list the places found in the context with their source, "Context names: Keens (parent), Peter Luger (title)" | +10 to 15 | C (10 items) by making the referent a lookup; may also raise B unless paired with the rule below |
| 9 | Photo-post flag: "(post is a photo)" | +3 | 3 items; needs ingestion to store the post URL / `post_hint`, which `threads` does not have |

Recommended bundle: 1 + 3 + 4 + 5 + 6, about +45 tokens per comment (+0.9% of input),
addressing roughly 19 of the 20 A items, the 9 OP items and part of B; it would close
about 17 of the 39 misses on its own. Item 3 should replace 2 rather than add to it.

B needs a prompt rule as well as labels: a reply about a general topic (prices in
general, health codes, veganism, the poster's own problem) is not a mention of the
post's place; and a claim made in the title or parent is the commenter's only when they
are its author or restate it.

## 4. Things that look unconsidered

1. **The 15-character filter discards more evidence than any context gap.** 18k
   top-level bare-name answers and 2.6k "this / second this / +1" replies are never
   extracted, though the prompt's rule 1 and rule 9 are written for exactly these. They
   need no model: a top-level body that exactly matches a resolved name is an endorse
   mention; an agreement reply inherits its parent's mentions and verdict. Run as a
   deterministic pass, the cost is zero tokens. Short opinion replies ("mid",
   "overrated", ~1,160) need the model and the parent; at ~5k tokens a call that is
   about 6M input tokens.
2. **Half of deep replies are the commenter's own back-and-forth** (13% of all eligible
   comments). The grandparent is often the commenter's *own* earlier comment, so the
   referent is "what I said before". Showing it as `(you, earlier)` is cheaper and more
   precise than the generic grandparent.
3. **Authorship is stored but never shown.** 9.4% of comments are by the post's author.
   For them the title and body are the commenter's own words, which flips how B-type
   claims should be read (Q0224), and "thanks, will try" from the asker is a plan, not
   an endorsement.
4. **An omitted section is ambiguous.** No `PARENT COMMENT` means top-level *or* deleted
   parent *or* missing; no `POST BODY` means a photo post, a link post or a title-only
   post. Saying which costs a few tokens.
5. **Replies are never shown**, though they correct the comment ("that closed",
   "that's in Jersey", "you mean X?"). Rare in the review (planted Q0115), so low
   priority, but it is the only source for some status facts.
6. **No dates.** The comment date and the post date are not in the input, so "new",
   "just opened", "used to" and `status` are read without knowing the comment is from
   2022 in a 2026 corpus.
7. The review sample had no deleted parents (expected about 3 of 542), so proposal 5 is
   untested by this review.
