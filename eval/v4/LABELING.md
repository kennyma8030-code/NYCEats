# Labeling brief: v4 round 1 under the v5 schema

You are labeling one batch of Reddit comments from r/FoodNYC. Your labels
become the reference that candidate extraction models are scored against, so
they must be careful, consistent and blind. Read this whole brief before you
start, then follow the batch file you were given.

## What you get, and what you never look at

You get this brief and **one batch file**: `eval/v4/batches/<pass>/bNNN.txt`.
The batch file contains:
- the pass and mode;
- the full v5 **EXTRACTION PROMPT** for that mode;
- the packets to label.

**Never open anything else in the eval folder.** That includes:
- other batches, or the other pass;
- `items.jsonl`, `packets.jsonl` or `keys/`;
- `eval/runs/`, `eval/results/`, `eval/baseline/` or `production/`;
- the v1/v2 gold, `gold_v5/` or `prompts/`.

Opening any of them is what makes a label stop being blind. Never use a model
or any tool to label for you. Packets are independent: never carry anything
from one packet to another.

There are two passes, done by different labelers:

- **same_input:** the packet is exactly the input the model gets. Judge from
  what is shown and nothing else.
- **full_context:** the packet shows the whole conversation around the unit.
  Read all of it before deciding what a comment means. Label only the comment
  marked `>>> COMMENT TO LABEL`, or, in a thread packet, only the comments
  with a bracket number `[n]`. Everything else is context.

## How to label

For every packet, produce exactly the JSON object the EXTRACTION PROMPT asks
for. The prompt is the rulebook: kinds of mention, fields, levels, aspects,
price, experience, avoids, dishes, descriptors and rules. **Everything in it
applies to you as written.** Then add the label metadata below to every
mention.

The prompt's rules come with the settled conventions and precedents below.
Where this brief is more specific than the prompt, the brief decides.

### Settled conventions

- **c1, dishes set food.** When the comment gives no verdict on the food
  overall, food takes the level of the dishes it judges, whatever it says
  about value, service, the room or the wait.
  - Liked dishes give their level.
  - A disliked dish counts as at most "meh".
  - Liked and disliked dishes together give "mixed".
  - An overall verdict wins: "great, but skip the dumplings" is food "good".
  - "Get the X" alone gives dishes_liked [X] and food "good".
- **c2, avoids.** An avoid (is_negated true) has one of two shapes:
  - **It judges the place.** At least one aspect is meh, bad or awful. With
    no reason given at all ("skip it", "forget about X"), food is "bad".
  - **Its reason is unrelated to the place's quality.** Examples: politics or
    who owns it, a mismatch with what the asker wants ("it's all seafood" when
    they want steak), where it is or how far it is to travel. Here every
    aspect stays null and no dish goes in dishes_liked or dishes_disliked.
    Experience is "unclear" unless they say they went.
  - **Crowds, lines and getting a table are about the place.** They are wait,
    so "avoid it, the line is two hours" is wait "bad" with is_negated true.
- **c3, a verdict means a visit.** A verdict in the commenter's own voice
  ("it's mid", "so good", "skip it") is experience "ate_there" unless they say
  they haven't been. "Haven't been" is "secondhand". Bare names, questions and
  facts are "unclear".
- **c4, "not worth it."**
  - Bare "not worth it" or "not worth going", given as advice, is an avoid.
  - "Not worth the price" or "not worth $40" is value "bad", not an avoid.
  - "Not worth the line" or "not worth the wait" is wait "bad", not an avoid.
  - "Not worth the hype" is food "meh", not an avoid.
  - "Just not worth it to me" is their own verdict, not advice, so it is not
    an avoid.
- **Judgment-carrying requests.**
  - When the post (or the comment being answered) asks for places with a
    judgment ("most overrated?", "worst service you've had?", "biggest
    letdown?", "where would you send an enemy?"), a bare name answering it
    takes that judgment. It is scored by the LEVELS entry for the request's
    own words: "overrated" is food "meh", "worst" is "awful", "letdown" is food
    "bad".
  - Put the judgment word in descriptors, and set `judgment_question: true`.
  - A reply that says more than the bare name is scored on its own words.

### Precedents from the earlier gold

These are rules settled while labeling v1 and v2. Apply them the same way.

**Levels**
- **"Rave" needs a broad superlative.** "Best in the city" and "my favorite in
  the city" are "rave". "My favorite" and "one of the best meals we've had
  lately" are "good" (with "rave" as an alternative).
- **"Awful" needs harm, a refusal, a superlative negative or extreme words.**
  "Worst", "got sick", "never again", "inedible" and "regretted going" are
  "awful". "Awful" alone is "bad".
- **"Fine", "ok", "alright" and "mid" are "meh"**, even when softened ("fine
  and I'd go again"). Accept "mixed" as an alternative there.
- **"Mixed" is for one aspect weighed both ways** ("hit or miss", "good apps,
  bad mains"). Opinions that differ across aspects are separate scores.
- **A list header applies to every item under it.** "Personal favs:" makes
  each name "good". An avoid header makes each name an avoid.
- **Sarcasm and thread framing decide the sign.** "Second this" under "where
  would you send an enemy" is negative.

**Specific aspects**
- **Reservations and walk-ins are wait.** "They seat walk-ins at 4pm" is wait
  "decent". "Never able to get a reservation" is wait "meh". A logistics tip
  that judges nothing ("order ahead to skip the line") leaves wait null.
- **Secondhand reactions are mild praise.** "Looks so good" or "sounds
  amazing", from someone who hasn't been, is food "decent" with experience
  "secondhand". It is not a bare endorsement or a reference.

**Avoids**
- **A self-skip is not advice.** "I'd rather skip it" or "I wouldn't go back"
  puts the negative in the aspect, with is_negated false. Add "is_negated" to
  uncertain_fields, because "avoid" is a defensible reading.

**References and endorsements**
- **A closed place is a reference** even when remembered badly ("worst ribs,
  good riddance"): every aspect null, "closed" in descriptors.
- **A factual answer inside a request for places** ("they sell gift cards",
  "pretty sure they have it") is a bare endorsement. Add "reference_only" to
  uncertain_fields.
- **Relaying what other people suggested** is a reference. Add
  "reference_only" to uncertain_fields.
- **Saying what they ordered, with no judgment,** is a reference, with the
  dishes in dishes_mentioned and "reference_only" in uncertain_fields. If
  it answers a request for places, it is an endorsement instead.

**Dishes and price**
- **A dish judged "just ok" goes in dishes_disliked**, because ok is meh. A
  dish judged both ways goes in dishes_mentioned.
- **Price is only set when it is stated in words.** A bare dollar figure
  ("$150") leaves price null.

## The label line

Write one JSON line per packet, in any order, to
`eval/v4/labels/<pass>/bNNN.jsonl`, the batch's own name:

```json
{"packet_id": "3f9a2c1b", "output": {"mentions": [ ... ]}}
```

Use `{"mentions": []}` when nothing qualifies. Every packet in the batch gets
exactly one line, including the empty ones.

Each mention has the prompt's keys, in the prompt's order. In a thread
packet, `"id"` comes first and is the bracket number of the comment the
mention belongs to. A comment packet's mentions have no `id`. After the
prompt's keys come:

| key | required | what |
|---|---|---|
| `canonical_name` | yes | the place's usual full name as you would look it up ("L'Industrie Pizzeria" for "lindustrie"). If you don't know it, repeat `restaurant_raw`. This is what other spellings are matched against. |
| `rationale` | yes | one short sentence on the reading, e.g. "reply judges the parent's place; 'mid' is meh". |
| `accept_names` | no | other names a correct model might type for it ("Luger" for "Peter Luger Steak House"). |
| `entity_type` | no | `restaurant` (default), `chain`, `bar`, `cafe_bakery_dessert`, `food_hall`, `food_truck`, `stall_vendor`, `grocery_market`, `other`. |
| `out_of_scope` | no | `true` for retail grocery stores, supermarkets and markets used as shops (Whole Foods, Trader Joe's, Costco), and for places outside NYC. Still emit the mention. |
| `ambiguous` | no | `true` only for a genuine two-reading case, e.g. a nameless reply that may be about the parent's place or only about the cuisine. Such a mention is neither required nor penalised. Don't use it to avoid a hard call. |
| `confidence` | no | `high` (default), `medium` or `low`. |
| `named_in` | no | where the name was typed: `comment` (default), `parent`, `ancestor`, `title`, `selftext`. |
| `aspect_alternatives` | no | `{"food": ["rave"], "price": [null]}`: other values that are also defensible for an aspect or for price, null allowed. Use one when a neighbor level is a fair reading, or when it is unclear whether the aspect is addressed at all (list `null`). Most mentions need none. Never list the value you chose. |
| `judgment_question` | no | `true` when a bare name took the request's judgment (see above). |
| `uncertain_fields` | no | any of `"reference_only"`, `"is_negated"`, `"experience"` that have two defensible readings. Those fields are not scored for this mention. |
| `value_complaint` | no | defaults to "value is meh or below". Set it only to override that. |
| `needs_context` | no, full_context only | `true` when the mention, or its sign, cannot be read from the model's own input. Examples: the place is named only in a grandparent, or a reply's parent is not in the chunk. The mention is still required; this records that the model lacked the context. |

**Mention fields**
- **What counts.** A mention is a food or drink business the comment names or
  unambiguously points at, including chains and carts. Cuisines, dishes,
  neighborhoods, generic categories ("any banh mi shop"), brands, apps and
  unnamed places ("the place next door") are not mentions.
- **`restaurant_raw`** is the name exactly as typed. For a nameless reply, it
  is the name as typed where the conversation names it, and `named_in` says
  where.
- **One mention per place per comment.** The same place twice in one comment
  is ONE mention. The checker rejects duplicates.

## Check your file before you finish

From the repo root run:

```
python eval/v4/labels.py check --pass <pass> --batch bNNN
```

It must print `OK`. It rejects, among other things:
- unknown or missing keys;
- a value outside the allowed levels or enums;
- a dish in two lists;
- a reference with an opinion;
- a liked or disliked dish with food null (c1);
- an avoid with neither a negative aspect nor the non-quality shape;
- a closed place that is not a reference;
- an `id` that is not a bracket number;
- the same place twice in one comment;
- a packet left unlabeled.

Fix every error and re-run until it passes. Your batch is done when:
- the check prints `OK`;
- every packet has a line;
- every mention has a canonical name and a rationale.

Report the batch id and anything you found genuinely ambiguous.
