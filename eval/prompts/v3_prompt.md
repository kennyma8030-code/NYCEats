# Extraction prompt v3

The extraction side of scoring v3. Scoring v3 ranks places by **how many people
praise them and how many complain**, so this prompt asks for a person's *stance*
toward each place, how strong and what kind any complaint is, and verdicts on
individual dishes. Numeric aspect scores are kept so v1 and v2 keep working on
the same rows.

Written for **thread mode** (one call per post with up to 25 comments), which
was both cheaper and more accurate in the benchmark. The comment-mode variant
swaps the first two sections; see the end of this file.

What changed from production's prompts:

| Field | Old prompts | v3 |
|---|---|---|
| `stance` | inferred from aspect numbers (0.3 meant "named") | explicit: praise, endorse, criticize, mixed, info |
| `complaint_strength` | squeezed into -0.3 / -0.6 / -1 | explicit: mild, clear, severe |
| `complaint_types` | none | quality, value, service, wait, atmosphere, hype, hygiene, consistency |
| `dish_verdicts` | dish names only | order / skip / mixed per dish |
| `timeframe` | rule text only | current or past, so "used to be great" is not a current opinion |
| `closed` | a descriptor | a boolean |
| `aspects`, `expensiveness` | free floats | the seven values -1, -0.67, -0.33, 0, 0.33, 0.67, 1 |

Every example below uses invented places and comments. None come from the
evaluation set, and none may ever be added from it.

---

## SYSTEM PROMPT (thread mode)

You extract restaurant mentions from a Reddit thread in a New York City food subreddit. The output is used to count how many different people praise a place and how many complain about it, so the most important things are: never skip a comment that refers to a place, and never soften or drop a complaint.

You are given the post, then its comments as an indented tree. Each comment starts with a number in brackets. Indentation means a reply: a comment indented under another is replying to it.

Output ONLY a JSON object, no prose, no code fences:

{"mentions": [ {"id": 3, ...}, {"id": 7, ...} ]}

Every mention carries the bracket number of the comment it came from. A comment that refers to three places produces three entries with the same id. NEVER invent an id; only use numbers that appear in brackets. Go through EVERY comment, including one-word replies: a short reply is the easiest thing to skip and is often the only complaint in the thread.

### What counts as a mention

Every restaurant, cafe, bakery, bar, food hall stall, food truck, or chain that the comment names or clearly refers to, including:

- a bare name in a list (the most common case);
- a reply that judges a place without naming it ("overrated", "v mid", "hard disagree", "their service is terrible"): it refers to the place in the comment it replies to;
- a question about a place ("is Golden Lotus still good?");
- a place the commenter has not been to ("on my list", "heard it's great");
- a closed place;
- a place used as a comparison ("like Ray's but better").

Not mentions: cuisines, dishes on their own, neighborhoods, streets, grocery stores and supermarkets, delivery apps, and places outside New York City.

The same place referred to twice in one comment is ONE mention.

### Fields (every key required on every mention, no extra keys)

| Key | Type | Meaning |
|---|---|---|
| `id` | integer | Bracket number of the comment this came from. |
| `restaurant_raw` | string | The name VERBATIM as typed. Never fix spelling or capitalization, never expand an abbreviation, never add a borough. For a reply that does not repeat the name, copy the name from the comment it replies to. |
| `stance` | string | One of `praise`, `endorse`, `criticize`, `mixed`, `info`. See STANCE. |
| `complaint_strength` | string or null | For `criticize` and `mixed`: `mild`, `clear`, or `severe`. Otherwise null. |
| `complaint_types` | array of strings | For `criticize` and `mixed`: every kind of complaint made, from `quality`, `value`, `service`, `wait`, `atmosphere`, `hype`, `hygiene`, `consistency`. Otherwise []. |
| `is_negated` | boolean | True only when the comment tells OTHER people to avoid the place: "skip it", "don't bother", "avoid". |
| `is_firsthand` | boolean | Did this person actually go? False for "heard", "my friend says", "on my list". |
| `timeframe` | string | `current`, or `past` when the opinion is explicitly about how it used to be ("used to be my favorite", "years ago it was great"). |
| `closed` | boolean | The comment says the place has closed. |
| `aspects` | object | Keys `food`, `value`, `service`, `atmosphere`, `wait`, each a LEVEL or null. |
| `expensiveness` | LEVEL or null | Price level, not a judgement: -1 very cheap … 1 very pricey. |
| `dishes` | array of strings | Dishes or drinks named. [] if none. |
| `dish_verdicts` | array | One `{"dish": string, "verdict": "order" \| "skip" \| "mixed"}` per dish the comment recommends or warns against. A dish only named gets no entry. |
| `descriptors` | array of strings | The commenter's own words someone would search to find the place: cuisine ("Sichuan", "omakase"), format ("slice shop", "BYOB", "food truck"), occasion ("date night", "birthday"), price feel ("cheap eats"). Never invent words. |
| `neighborhood_hint` | string or null | Only when the comment places this restaurant somewhere ("the LES one"). |

### STANCE — the field everything else depends on

| Stance | When | Examples |
|---|---|---|
| `praise` | A clear positive opinion of the place or its food. | "so good", "my go-to", "best in the city", "get the dumplings there" |
| `endorse` | Named as an answer or a suggestion with nothing said about it. Choosing to name it is a weak yes. | "Lucali" under "best pizza in Brooklyn?"; "try Golden Lotus" |
| `criticize` | Any negative opinion, however mild. On this subreddit "fine", "ok", "mid", "overrated", "not worth the hype" are complaints, not neutral. | "mid", "overrated", "bland", "rude staff", "got sick" |
| `mixed` | Real praise AND a real complaint about the same place. | "food's great but way overpriced", "amazing pasta, terrible service" |
| `info` | No opinion at all. | questions, "haven't been", "it's on 23rd st", "they closed", "the chef moved to X" |

Rules:

1. A list under a heading inherits the heading. "My favorites:" makes every name `praise`. "Avoid:" makes every name `criticize` with `is_negated` true.
2. "Avoid these: A, B, C" applies to EVERY name in the list.
3. Losing a comparison ("I prefer X over Y") is `criticize` mild for Y, not an instruction to avoid it.
4. Opinions are about NOW. "Used to be great, went downhill" is `criticize` with `complaint_types` ["consistency"] and `timeframe` "current". "Used to be my favorite before it closed" is `info` with `closed` true and `timeframe` "past".
5. A closed place is always a mention, with `closed` true and stance `info` unless the comment complains about something current.
6. Single-word names are the ones most often missed: Tong, Luger, Keens, Angel, Emily. Catch them.
7. A reply belongs to its parent's place unless it names something else. "Hard disagree" under "X is overrated" is `praise` for X. The mention takes the REPLY's id.

### COMPLAINT STRENGTH

| Strength | When | Examples |
|---|---|---|
| `mild` | A knock, a shrug, "not worth it" | "mid", "fine", "overrated", "not worth the hype", "meh" |
| `clear` | A real complaint | "bad", "bland", "overpriced", "rude", "disappointing", "wouldn't go back" |
| `severe` | A bad experience stated strongly, or a health or safety problem | "worst I've had", "got sick", "food poisoning", "never again", "inedible", "roach", "regretted going" |

Do not soften a complaint because the thread likes the place or the commenter is polite. When unsure between two strengths, choose the stronger one.

### COMPLAINT TYPES

| Type | Means | Examples |
|---|---|---|
| `quality` | the food itself | "bland", "dry", "mid", "worst slice" |
| `value` | not worth the money | "overpriced", "rip-off", "$28 for noodles is a joke" |
| `service` | the staff | "rude", "ignored us", "rushed us out" |
| `wait` | the line, booking, slowness | "two-hour wait", "impossible reservation" |
| `atmosphere` | the room | "too loud", "cramped", "dirty room" |
| `hype` | reputation outruns the food | "overrated", "tourist trap", "only good for Instagram" |
| `hygiene` | cleanliness and health | "got sick", "roach", "dirty kitchen" |
| `consistency` | declined or varies | "went downhill", "hit or miss", "not what it used to be" |

### LEVELS for `aspects` and `expensiveness`

Use exactly these seven numbers, or null:

| Level | Meaning |
|---|---|
| 1 | superlative: "best in the city", "life-changing" |
| 0.67 | clear praise: "excellent", "so good", "my go-to" |
| 0.33 | mild positive, or named as an answer with nothing said |
| 0 | explicitly mixed: "hit or miss" |
| -0.33 | mild knock: "mid", "fine", "overrated" |
| -0.67 | clear complaint: "bad", "overpriced", "rude" |
| -1 | severe: "worst I've had", "got sick", "never again" |

null means NOT MENTIONED; 0 means explicitly mixed. Never infer one aspect from another: great food says nothing about service, price, the room, or the wait. "Overpriced" is value -0.67. "Cheap" alone is expensiveness, not value. Easy walk-ins are wait 0.33; an impossible reservation is wait -0.67. Keep the aspects consistent with the stance: a `criticize` mention has at least one negative aspect, unless its only complaint is `hype`, which goes in food.

### EXAMPLE (invented places)

POST: Best noodles in Queens?

```
[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob: pepper house is overrated and $28 for noodles is a joke
    [3] u/ann: hard disagree, the cumin lamb is worth it
[4] u/cal: Avoid both. Noodle Lab is the move, just skip their dumplings
  [5] u/dee: got sick after Noodle Lab last month, never again
[6] u/eve: has anyone tried Okiku since it reopened?
```

{"mentions":[
{"id":1,"restaurant_raw":"Golden Lotus","stance":"endorse","complaint_strength":null,"complaint_types":[],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":0.33,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null},
{"id":1,"restaurant_raw":"Pepper House","stance":"mixed","complaint_strength":"mild","complaint_types":["wait"],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":0.33,"value":null,"service":null,"atmosphere":null,"wait":-0.33},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null},
{"id":2,"restaurant_raw":"pepper house","stance":"criticize","complaint_strength":"clear","complaint_types":["hype","value"],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":-0.33,"value":-0.67,"service":null,"atmosphere":null,"wait":null},"expensiveness":0.33,"dishes":["noodles"],"dish_verdicts":[],"descriptors":["overrated"],"neighborhood_hint":null},
{"id":3,"restaurant_raw":"pepper house","stance":"praise","complaint_strength":null,"complaint_types":[],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":0.67,"value":0.33,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":["cumin lamb"],"dish_verdicts":[{"dish":"cumin lamb","verdict":"order"}],"descriptors":[],"neighborhood_hint":null},
{"id":4,"restaurant_raw":"Golden Lotus","stance":"criticize","complaint_strength":"clear","complaint_types":["quality"],"is_negated":true,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":-0.67,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null},
{"id":4,"restaurant_raw":"Pepper House","stance":"criticize","complaint_strength":"clear","complaint_types":["quality"],"is_negated":true,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":-0.67,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null},
{"id":4,"restaurant_raw":"Noodle Lab","stance":"mixed","complaint_strength":"clear","complaint_types":["quality"],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":0.67,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":["dumplings"],"dish_verdicts":[{"dish":"dumplings","verdict":"skip"}],"descriptors":[],"neighborhood_hint":null},
{"id":5,"restaurant_raw":"Noodle Lab","stance":"criticize","complaint_strength":"severe","complaint_types":["hygiene"],"is_negated":false,"is_firsthand":true,"timeframe":"current","closed":false,"aspects":{"food":-1,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null},
{"id":6,"restaurant_raw":"Okiku","stance":"info","complaint_strength":null,"complaint_types":[],"is_negated":false,"is_firsthand":false,"timeframe":"current","closed":false,"aspects":{"food":null,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"dishes":[],"dish_verdicts":[],"descriptors":[],"neighborhood_hint":null}]}

Why: comment 1 names Golden Lotus as an answer (`endorse`) and puts up with Pepper House's line (`mixed`, mild `wait`). Comment 3 names nothing but disagrees with comment 2, so it is `praise` for Pepper House under id 3. Comment 4's "Avoid both" covers both places from comment 1, emitted under id 4 with `is_negated` true; "skip their dumplings" is a dish verdict on Noodle Lab, which is still recommended, so Noodle Lab is `mixed`. Comment 5 never types a name; it replies to the Noodle Lab recommendation, and "got sick … never again" is `severe` `hygiene`, a bad experience rather than an instruction, so `is_negated` stays false. Comment 6 is a question: `info`.

---

## Comment-mode variant

Replace everything above "What counts as a mention" with:

> You extract restaurant mentions from ONE Reddit comment posted in a New York City food subreddit. The output is used to count how many different people praise a place and how many complain about it, so the most important things are: never miss a place the comment refers to, and never soften or drop a complaint.
>
> You are given the post title, usually the post body, sometimes the parent comment, and then the comment itself. The context exists only to make sense of the comment. Extract from the COMMENT. Never extract a place that is only named in the title, body, or parent unless the comment says something about it. A reply that gives an opinion without repeating the name IS a mention of the place it replies about.
>
> Output ONLY a JSON object, no prose, no code fences: {"mentions": [ {...} ]}. Use {"mentions": []} only when the comment refers to no place at all.

Then drop the `id` field from the field table and adapt the example to a single comment with its parent.

---

## Using it

- **Benchmark first.** The eval labels can be converted to `stance` (level +1 with nothing else said is `endorse`), `complaint_strength` (levels -1 / -2 / -3), value complaints and dish verdicts. They do not record `complaint_types` or `timeframe`; adding those to the 769 labels is a short labeling pass. Wrap this text as `eval/prompts/v3_thread.py` (`SYSTEM_PROMPT = …`) and run `eval/run.py --mode thread --prompt file:eval/prompts/v3_thread.py` on the 17 threads and the 395 single comments before any backfill.
- **Storage.** The new fields need columns on `mentions` (or one `extra jsonb`): `stance`, `complaint_strength`, `complaint_types`, `timeframe`, `closed`, `dish_verdicts`. The prompt hash stamped on each row tells scoring which fields a row can be trusted for.
- **Model.** GPT-6 Luna in thread mode was the benchmark's best value; its batch endpoint halves the price for a backfill.
