# Judging thread mode: what is added to the round-4 rubric

Read `eval/review_v6r4/RUBRIC.md` first. Everything in it applies: the
blind-first procedure, the owner's level names, the judgment line, the
fields, and the rules, which are the prompt's own. This page says only what
is different when Haiku read a **chunk of a thread** instead of one comment.

## Files you may open

This file, `eval/review_v6r4/RUBRIC.md`, and your one packet
(`eval/thread_v6/review/packets/tNNN.md` or `.json`, or a side-by-side
packet `eval/thread_v6/review/pairs/aNNN.md` or `.json`). Write only its
judgment file (`judgments/tNNN.jsonl`, or `pair_judgments/aNNN.jsonl`, under
`eval/thread_v6/review/`). Do not open `eval/runs/`, any
`.sealed/` directory, gold or label files, `eval/review_v6r4/packets/` or
`judgments/`, other packets or other judges' judgments.

## What you get

Each packet holds one or more chunks. For each chunk:

1. **What the model saw**: the chunk exactly as sent. The post, then
   numbered comments `[1]`, `[2]`, ... in thread order, each reply naming the
   comment it answers. Two things round 4's comment packets never had:
   - **The post can be item `[0]`** (`[0] POST: ...`, body up to 4,000
     characters). Then it is extracted like a comment, under the post rules
     below. A post with no number is context only.
   - **Quoted context lines**, under "Earlier comments in this thread, quoted
     as context (not in this chunk; never extract from them)": the comments
     the chunk's first comments hang under (already extracted elsewhere, or
     deleted), at full text, with no number. They are context: nothing is
     extracted from them, but a numbered reply that judges a quoted place is
     a mention of that place (named_in "context").
2. **The items to judge**: some or all of the chunk's numbered items, each
   with its wider context (every ancestor, the replies; for the post, its
   full body). Haiku did not see the wider context.
3. A divider, then **Haiku's output for each judged item**, already split by
   item: the mentions Haiku filed under that bracket number.

Write your `own_read` for **every** item of the chunk listed above the
divider before you read anything below it.

## How to judge an item

Judge each item on its own, exactly as round 4 judged one comment: which
places that comment (or the post) mentions, and every field, from what it
says plus what it agrees with. The chunk is the context the model had, so
"needs wider context" means needing something that is neither in the chunk
nor in the item's own text.

**Attribution.** A mention belongs to the comment that says it. If Haiku
filed a place under this item that only another comment of the chunk talks
about (a neighbour's rec, the parent's verdict copied down), it is a false
mention for this item: a `_mention` compare with `final` null and the reason
"belongs to [k]". If this item talks about a place and Haiku filed it under
another number, it is a miss here (put it in `missed`). Judge the item in
front of you; the other item is judged where it appears.

**The post `[0]`.** Judge it under the post rules: the places the post names
and what the poster says about them, their own visits and verdicts included;
a place the poster only asks about is a mention with opinion "none";
named_in is always "comment". A place that only a comment names is not the
post's.

## Two answers for one comment (side-by-side packets, `pairs/aNNN`)

Some packets show one comment with **two answers, A and B**, from two
different setups; which is which is not said and must not be guessed at.
There is no "What the model saw" here: judge from the comment, its thread
and the rules, as if the model had seen what you see.

1. Write your `own_read` once, before the divider, as usual.
2. Grade **A** and **B** each exactly as you would one answer: a `compare`
   entry for every place or field where it differs from your own read, its
   `missed` places, its `notes_grade`, its `overall_item_ok`.
3. Then say which is better: `"A"`, `"B"`, or `"same"` when they are equally
   right or equally wrong in the same way. In one sentence, say how they
   differ (`difference`), and tag it (`difference_types`, any of
   `missed_place`, `added_place`, `polarity`, `level`, `opinion`,
   `experience`, `attribution`, `dish`, `other`). Set `"clear": true` when
   the difference is a clear-cut case worth quoting.

One line per comment in `eval/thread_v6/review/pair_judgments/aNNN.jsonl`:

```json
{"item_id": "P0001", "comment_id": "t1_...", "own_read": [...],
 "a": {"compare": [...], "missed": [...], "notes_grade": [...], "overall_item_ok": true},
 "b": {"compare": [...], "missed": [...], "notes_grade": [...], "overall_item_ok": false},
 "rule_questions": [], "better": "A", "difference": "B misses the knock on Keens in the reply.",
 "difference_types": ["missed_place"], "clear": true}
```

Either answer may carry a planted change, as in every packet.

## The thread prompt's own words

The model got the round-4 rules (in `RUBRIC.md`) with this input section,
this post section and this example in place of comment mode's. Copied from
`prompts_v6/v6_thread.py`; `eval/thread_v6/selftest.py` fails when they
drift.

<!-- thread prompt sections: begin -->
```text
<input>
You get the post, then a chunk of its comments, each starting with a number in brackets. Extract from the comments only; the post, and the comment a reply answers, are its context. Every mention carries "id", the bracket number of the comment it came from; never use a number that is not in brackets. Go through EVERY comment, one-word replies included: they are easy to skip and often hold the only complaint.
Each reply follows the comment it answers and says which one: "(reply to [3])". Trust that marker over position or indentation. A reply to a comment outside this chunk quotes it: (reply to u/zed, not in this chunk: "..."). The quote is context only; never extract from it, but a reply that judges the quoted place is a mention of that place.
A reply is about the place in the comment it answers unless it names another, and the mention takes the REPLY's id, with named_in "context": "overrated" under a rec is a knock on that place; "hard disagree" under "X is overrated" is praise for X. Each comment's levels come only from what that comment says, plus a claim it agrees with ("+1", "exactly"); a commenter's earlier comment is counted on its own, with its own id. If the place still cannot be told (a reply to a deleted comment), skip it rather than guess. Most comments name no place and need no deliberation.
</input>

<post_item>
When the post itself is numbered, "[0] POST: ...", it is an item too: extract its title and body, written by the poster, and its mentions carry "id" 0. Extract the places the post names and what the poster says about them, their own visits and verdicts included. A place the post only asks about ("is X worth it?") is a mention with opinion "none". named_in is always "comment" for item 0. A post with no number is context only.
</post_item>

<thread_example>
POST: Best noodles in Queens?

[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob (reply to [1]): pepper house is overrated and $28 for noodles is a joke
    [3] u/ann (reply to [2]): hard disagree, the cumin lamb is worth it
  [4] u/eve (reply to [1]): golden lotus was mid last time
[5] u/cal (reply to u/zed, not in this chunk: "Noodle Lab for knife-cut, skip the dumplings"): meh, wouldn't cross town for it
[6] u/dee: is Noodle Lab still cash only?

1: Golden Lotus endorse, overall praise, dish noodles praise and taste praise (a bare answer takes the dish the question asks about). Pepper House stated: dish noodles praise, taste praise, wait knock, overall praise (a pick; the wait never lowers overall).
2: pepper house: overall knock ("overrated"), value knock, dish noodles (level null), note "$28 for noodles".
3: pepper house (named_in "context"): stated, overall praise, taste praise, dish cumin lamb praise.
4: golden lotus (named_in "context"): overall and taste knock ("mid").
5: Noodle Lab (named_in "context", from the quote): overall knock ("meh" is lukewarm, and they wouldn't make the trip).
6: Noodle Lab: opinion none, experience none, every level null.
</thread_example>
```
<!-- thread prompt sections: end -->

The example's labels are the prompt's (praise, knock); you write the owner's
names, as `RUBRIC.md` says (positive, negative, ...).
