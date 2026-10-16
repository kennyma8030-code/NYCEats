# v5 gold: thin cases and how to fill them

`diversity_v5.md` counts how many labeled comments exercise each v5 case. These
cases have fewer than 15 comments across v1 and v2, so a recall on them moves by
more than ten points per item:

| case | comments now | why it matters |
|---|---:|---|
| judgment-carrying question (rule 2) | 1 | the only test of "a bare name inherits the question's judgment" |
| evaluative descriptor ("tourist trap", "overrated", "the OG") | 4 | v1 never labeled evaluative words as descriptors, so recall on them is unmeasured |
| reference: comparison anchor ("like Katz's but cheaper") | 9 | convention 5's yardstick rule |
| avoid list (2+ avoids in one comment) | 10 | "an avoid heading a list applies to every name" |
| price without value | 11 | price as a fact, not a complaint |
| not resolvable in thread mode | 12 | context-gap attribution in thread mode |
| overpriced (price pricey + value negative) | 13 | the owner's value-complaint signal |
| reference: question about a place | 14 | rule 4, "stated, not asked" |

The thread-mode column is thin for most aspect levels too: v1's 17 threads give
0 "awful", 3 "mixed", 6 service and 6 value comments. More whole threads with
negative discussion would fix that faster than single comments.

No `DATABASE_URL` or `EVAL_DB_URL` was available when this was written, so no
new comments were drawn. Each query below finds candidates read-only. Run them
with `PGOPTIONS='-c default_transaction_read_only=on'`, exclude every comment
already in v1, v2 or v4 round 1, draw in `md5(seed || id)` order as
`v2/mine_topups.py` does, and label the drawn comments blind (no stored
mentions shown). Record the query and seed with the items so their weight
stays honest: these are targeted draws, not traffic samples, and belong in a
diagnostic set like v2, not the reweighted headline.

Every item must be a real comment. Never paraphrase or invent one.

```sql
-- exclusions: load the ids from eval/v1/items.jsonl, eval/v2/items.jsonl and
-- eval/v4/items.jsonl into a temp table first
create temp table seen(id text primary key);

-- 1. judgment-carrying questions: short top-level answers in threads whose
--    title carries the judgment. Target 25.
select c.id, t.title, c.body
from comments c join threads t on t.id = c.thread_id
where t.title ~* '\m(overrated|overhyped|over-hyped|worst|letdown|let down|disappoint\w*|tourist trap|nasty|terrible|regret\w*|mid)\M'
  and coalesce(c.depth, 0) = 0 and length(c.body) between 3 and 200
  and c.body ~ '[A-Z][a-z]' and c.body not in ('[deleted]', '[removed]')
  and c.id not in (select id from seen);

-- 2. avoid lists: one avoid word heading two or more names
select c.id, c.body from comments c
where c.body ~* '\m(skip|avoid|stay away from|don''t bother with)\M[^.!?]{0,80}(,| and | or )'
  and length(c.body) < 600 and c.id not in (select id from seen);

-- 3. questions about a named place (rule 4)
select c.id, c.body from comments c
where c.body ~ '\?' and c.body ~* '\m(is|are|does|did|has)\M[^?]{0,60}\m(still|worth|good|open|cash only|byob|any good)\M'
  and length(c.body) < 300 and c.id not in (select id from seen);

-- 4. comparison anchors (convention 5's yardstick)
select c.id, c.body from comments c
where (c.body ~ '\mlike [A-Z][\w''&]+[^.]{0,40}\m(but|except|only)\M'
       or c.body ~ '\m(better|worse|cheaper|pricier) than [A-Z]')
  and length(c.body) < 500 and c.id not in (select id from seen);

-- 5. price stated in words, with and without a value complaint
select c.id, c.body,
       c.body ~* '\m(worth|value|deal|rip ?off|robbery)\M' as has_value
from comments c
where c.body ~* '\m(overpriced|pricey|pricy|expensive|cheap|affordable|inexpensive|reasonably priced)\M'
  and length(c.body) < 500 and c.id not in (select id from seen);

-- 6. evaluative descriptors
select c.id, c.body from comments c
where c.body ~* '\m(tourist trap|hidden gem|institution|staple|overhyped|underrated|the og|old school|classic)\M'
  and length(c.body) < 500 and c.id not in (select id from seen);

-- 7. thread-mode context gaps: replies whose parent sits more than 25
--    eligible comments earlier, so a 25-comment chunk cannot show it
select c.id, c.thread_id from comments c join comments p on p.id = c.parent_comment_id
where (select count(*) from comments x where x.thread_id = c.thread_id
         and x.created_utc between p.created_utc and c.created_utc) > 25
  and length(c.body) < 200 and c.id not in (select id from seen);

-- 8. whole threads with negative discussion, for the thread-mode column
select t.id, t.title, t.num_comments from threads t
where t.title ~* '\m(worst|disappoint\w*|overrated|review|regret\w*|avoid)\M'
  and t.num_comments between 20 and 60;
```

The unlabeled v4 round 1 items already contain some of these: 36 comments sit
in threads with a judgment-carrying title, 64 contain a question, 26 state a
price in words and 22 use "ok/fine/mid" (see `diversity_v5.md`). Labeling v4
under the v5 contract would close several gaps at once, but its protocol labels
with the candidate prompt, so it waits for the v5 prompt.
