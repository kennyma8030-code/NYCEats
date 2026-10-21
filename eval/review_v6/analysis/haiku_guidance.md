# Getting accurate structured extraction out of Claude Haiku 5.5: an audit of the v6 comment prompt

Scope: `eval/prompts/v6_common.py`, `eval/prompts/v6_comment.py` and
`eval/prompts/v6_schema.json` (prompt hash `6b046d8ed65d`, the round-3 prompt),
used with the request settings in `eval/anthropic_backend.py`. Target model:
`claude-haiku-5-5`. No model calls were made. The numbers below come from
existing run files in `eval/runs/` and from the Opus review in
`eval/review_v6/judgments/`.

Doc shorthand used in the citations:

- **[mig]** bundled skill `claude-api/shared/model-migration.md` §Migrating to Claude Haiku 5.5
- **[audit]** bundled skill `claude-api/shared/prompt-audit.md`
- **[cache]** bundled skill `claude-api/shared/prompt-caching.md`
- **[so-skill]** bundled skill `claude-api/shared/tool-use-concepts.md` §Structured Outputs
- **[haiku]** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5
- **[new]** https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5
- **[bp]** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- **[so]** https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- **[effort]** https://platform.claude.com/docs/en/build-with-claude/effort
- **[steer]** https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost
- **[sonnet]** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 (§Reasoning tasks with JSON output; measured on Sonnet 5.5, not Haiku)
- **[batch]** https://platform.claude.com/docs/en/build-with-claude/batch-processing

The skill's base directory is
`/private/tmp/claude-501/bundled-skills/2.1.296/d4200b863526381927ee9c05743f789a/claude-api/`.

---

## 1. Summary

1. **Part of the error rate comes from the prompt disagreeing with the gold
   rubric, not from Haiku.** The prompt's `SCALE` lists "never again" and
   "regretted going" as very_negative, but `review_v6/RUBRIC.md` makes them
   negative and calls its calibration "stricter than Haiku's prompt". The
   prompt's `overall` definition has no "bottom line, else strongest point"
   rule, and its own example says a line tip has no overall. Over-scaling
   (68 errors) and a null overall despite a verdict (60 errors) are the two
   biggest level-error classes, and both trace to these gaps. Align the
   prompt with the rubric first. This needs owner decisions on four open
   questions (§5).
2. **At effort low, Haiku skips thinking on about half the comments.** On the
   round-3 run, 52% of calls had zero thinking tokens (median 0); at medium
   it was 13%. Structured outputs leave only the JSON in the response, so a
   call with no thinking has nowhere to work things out [sonnet]. 21 of the
   23 "own pick marked secondhand" errors and 40 of the 68 over-scalings
   came from zero-thinking calls. The documented levers are a short
   "think it through, then check" instruction [steer][bp], effort, and
   schema field order (§3, items 3 and 6).
3. **Teach judgment with examples, not format.** The schema already fixes
   the output shape. The single full-JSON example spends about 330 tokens
   pinning a format the grammar enforces anyway, and it shows only one
   negative case. 4–5 short contrastive examples that each give the
   method behind the answer target the observed errors directly [bp][audit].
4. **Cost is not the constraint.** The system prompt is cached (98% hit rate
   in round 3) and Haiku 5.5 reads cache at $0.01/MTok, so 100 extra prompt
   tokens cost about $0.005 per 10k comments in batch. Output tokens matter
   about 50 times more: +100 output tokens per comment is about $0.25 per
   10k comments in batch. All the changes below together cost under $1 per
   10k comments.

---

## 2. Haiku 5.5 facts that matter for this workload

| Fact | Consequence here | Source |
|---|---|---|
| Adaptive thinking is on by default. Effort runs `low` to `max`, default `medium`. `budget_tokens` returns a 400. | `anthropic_backend.params` already sends `thinking: adaptive` and `effort`. Good. | [mig] [effort] |
| At lower effort the model "can skip thinking entirely for simpler problems". | Measured: 52% zero-thinking at low, 13% at medium (round-3 and round-1 runs). | [effort] [steer] |
| Telling Haiku 5.5 to answer directly didn't stop it thinking. Effort is the reliable control, and prompt text can also *encourage* thinking: "This task involves multistep reasoning. Think carefully before responding." | Use prompt text to push thinking up at low effort. Don't try to push it down with prose. | [haiku] [steer] |
| With structured outputs the response holds only JSON, so the model "can work the problem out only in its thinking. When it skips thinking, it can be less accurate." Adding "Think the problem through before you answer." raised accuracy at low/medium. | Measured on Sonnet 5.5, but the mechanism is the same on Haiku. Test it (item 3). | [sonnet] |
| With structured outputs at low/medium effort, the model occasionally thinks until `max_tokens`. Treat any `stop_reason: "max_tokens"` as failed, even if the JSON parses. | Round 1 medium truncated 6 calls at 6,000 tokens. Use ≥16k for comment mode. | [sonnet] [mig] |
| `temperature`, `top_p` and `top_k` return a 400. Assistant prefill returns a 400. | Neither is sent by `anthropic_backend`. Consistency has to come from the prompt and schema, since there is no temperature 0. | [mig] |
| Thinking text is omitted by default. `display: "summarized"` returns summaries at no extra charge. | Run a diagnostic sample with `summarized` to see what Haiku reasons about on the error classes. Billing is unchanged. | [mig] [steer] |
| The new tokenizer counts about 30% more tokens than Haiku 4.5. | Measured: about 2.9 chars per token. The v6 system prompt is about **3.05k tokens**, not 2.2k. The full cached prefix is **4,805 tokens**: about 1.5k is the structured-output format prompt with the schema, and about 0.2k is the thinking system prompt. | [new] [mig]; derived from `usage_details` in `eval/runs/*r3_schema.jsonl` vs `*r1*` and `prompt.py` runs |
| The minimum cacheable prefix is 512 tokens. Cache reads are 0.1x input. Changing `output_config.format` invalidates the prompt cache. Effort is rendered into the prompt, so changing it starts a new cache entry. | Keep the schema byte-stable within a run. A medium-effort route gets its own cache entry. | [mig] [cache] [so] [steer] |
| Batches: caching is best-effort (30–98% hits). Use identical `cache_control` blocks, and consider the 1-hour TTL. | Round 3 already got 98%. No change needed. | [batch] |
| Safety classifiers can return `stop_reason: "refusal"`, with no server-side fallback. Output then may not match the schema. | No refusals in any run so far. Branch on `stop_reason` before parsing, because food-poisoning or health-code comments could trip `general_harms`. | [mig] [haiku] [so] |
| Structured outputs aren't available for Haiku 5.5 on Amazon Bedrock. | Only matters if production ever moves to Bedrock. | [new] |

---

## 3. Ranked changes

Token costs are system-prompt tokens at about 2.9 chars/token (cached, so
dollars are negligible), plus expected output tokens where the change
affects thinking. "Fixes" uses the round-3 review counts. A judge-row
breakdown is reproducible from `review_v6/judgments/*.jsonl`.

Round-3 counts the items refer to: over-scaling to very_* **68**;
overall null despite a verdict **60** (about 15 of them endorsements);
experience none→firsthand **53**, secondhand→firsthand **23**; dish
missing **38**, other dish errors **47**; mention adds/drops **112** (part
of that is planted round-1 truncation substitutes). Notes: missing 49,
wrong 23.

### 1. Align the level scale with the rubric (highest impact, needs owner calls)

**Problem.** The prompt's `SCALE` and the rubric disagree:

- The prompt lists "never again" and "regretted going" as very_negative.
  The rubric puts them, and "disappointing", under negative.
- The prompt has no guidance on strong-but-unranked words. Haiku turned
  "so so cozy", "top notch", "beautiful", "terrible service" and "awful"
  into very_*.

**Replace the very_positive and very_negative lines in `SCALE` with:**

```
  very_positive  only a superlative that ranks THIS place above a broad class: "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life", "god tier", "life-changing". Strong praise that ranks nothing stays positive: "amazing", "incredible", "to die for", "top notch", "so so good", "beautiful".
  ...
  very_negative  only an extreme: "worst I've had", "inedible", "disgusting", "got sick", "avoid at all costs". A strong complaint that names no extreme stays negative: "terrible", "awful", "never again", "regretted going", "disappointing".
```

Add "disappointing" to the negative examples. Add one line under the scale:
`Intensity ("so", "really", caps, "!!") never raises a level on its own.`

- **Fixes:** over-scaling to very_* (68). Also shifts a few `overall`
  errors, since very_* overall values count there too.
- **Cost:** about +55 tokens. No output change.
- **Blocked on:** whether "terrible" and "awful" are very_negative (rubric
  questions Q0113, Q0374, Q0445) and whether hyperbole like "to die for"
  is positive (Q0127). The wording above assumes negative and positive.
- **Sources:** [bp] §Be clear and direct ("Be specific about the desired
  output"). [audit] Group 2: two instruction sources that rule differently
  on the same point have to be reconciled, and here the rubric is the newer
  and owner-approved one.

### 2. State the overall rule the gold uses, and stop the endorse conflict

**Problem.** The `overall` definition gives no rule for comments without a
bottom line, and its example "'go early to beat the line' has no overall
(null)" teaches null. Rule 4 opens with "Never default to positive", which
pulls against `FIELDS`' "Always 'positive' for 'endorse'". The review shows
about 15 endorsements left with a null overall.

**Replace the `overall` line in `FIELDS` with** (option A follows the
rubric as written):

```
overall     LEVEL. The commenter's bottom line on the place ("worth it", "never going back", "skip it"); without one, their strongest point, usually the food. A place the comment judges in any way, through an aspect or a dish included, has an overall. null only when there is no verdict at all: a tip, a fact, a question. A bare endorsement is "positive".
```

If the owner decides that a single-aspect remark such as "the line is
brutal" does *not* set overall (option B), replace the middle sentence
with: `A remark about one aspect alone ("the line is brutal", "$12 is a lot") sets that aspect and leaves overall null.`

Whichever option is chosen, make the worked example agree with it.

**Replace rule 4 with:**

```
4. Level each place by what the comment says about it. "endorse" is a bare name or "try X" with no judgment, and its overall is "positive". A place with any judging remark is "stated"; one only asked about or named in passing is "none". A complaint replying to a rave is still a complaint.
```

**In code, not prose:** in the normalizer that reads extraction output
(not in the stored raw output), set `overall = "positive"` when
`opinion == "endorse"` and `overall` is null. This is a deterministic
rule, and [audit] Group 1d says to enforce in code what code can enforce.

- **Fixes:** overall null despite a verdict (60).
- **Cost:** about +35 tokens net.
- **Blocked on:** whether a verdict on one aspect alone sets overall
  (Q0020, Q0132, Q0178, Q0223, Q0392). Judges answered both ways.
- **Sources:** [audit] 1c and 1e (positive statement of intent instead of
  prohibition clusters; conflicting instructions). [bp] §Control the
  format of responses ("Tell Claude what to do instead of what not to
  do").

### 3. Point the thinking at the known failure points (a short self-check)

**Problem.** At low effort 52% of calls don't think, and with structured
outputs the JSON is written straight away.

**Append as the last block of the system prompt:**

```
<before_answering>
Each place takes a few steps of judgment, so think it through before you answer. Then check every place: the COMMENT itself refers to it, and it is a restaurant, cafe, bar, bakery, deli or food stall in NYC; experience is "firsthand" unless the comment credits someone else; every complaint and every named dish sits in an aspect, overall or a dish entry, not only in a note; overall is set whenever the comment judges the place; every very_ level rests on its own superlative or extreme word.
</before_answering>
```

- **Fixes:** a little of every class, especially the zero-thinking-heavy
  ones: secondhand on own picks (21 of 23 at zero thinking), over-scaling
  (40 of 68), experience none→firsthand (30 of 53).
- **Cost:** about +115 prompt tokens. Expect more thinking: if low moves
  partway toward medium's profile, that is +150 to 250 output tokens per
  call, about $0.40–0.60 per 10k comments in batch.
- **Test:** compare zero-thinking share and accuracy at low with and
  without the block. If accuracy rises but stays below medium, the doc'd
  Sonnet result predicts exactly that, and §4's routing applies.
- **Sources:** [steer] §System prompt guidance ("This task involves
  multistep reasoning. Think carefully before responding."). [bp]
  §Leverage thinking ("Ask Claude to self-check... verify your answer
  against [test criteria]"; "Prefer general instructions over prescriptive
  steps"). That is why this is a checklist of outcomes, not a step plan.
  [sonnet] §Reasoning tasks with JSON output.

### 4. Make "experience" a test of whose voice it is

**Problem.** Haiku reads "firsthand" with its everyday meaning, "I visited",
and marks plain picks and list items as none (53) or secondhand (23). The
prompt says firsthand is the default, but the enum name pulls the other
way.

**Replace the `experience` line with:**

```
experience  Whose opinion is it? "firsthand": the commenter's own, which is any visit, pick, list item, tip or verdict in their own voice, even when no visit is described ("Keens, Gallagher's", "get the pastrami there", "I think Matto is better"). "secondhand": the comment credits another source for the opinion ("my friend swears by it", "heard great things", "people say"). "none": a question, a place they say they haven't tried, or a bare fact.
```

- **Fixes:** experience accuracy (0.864): 53 none→firsthand, 23
  secondhand→firsthand.
- **Cost:** about +45 tokens net.
- **Schema option (lower confidence, needs an A/B and scorer changes):**
  rename the enum to voice terms (`own` / `credited` / `none`), and/or
  rename experience's `none` (for example `untried`) so it no longer
  shares a value with `opinion: "none"`. [audit] Group 3: "well-named
  enums carry intent".
- **Sources:** [bp] §Add context to improve performance. [bp] §Be clear
  and direct.

### 5. Tighten what counts: grocery stores, and places that only the post names

**Problem.** Haiku extracted H Mart, Pomegranate, Market Basket and Tan
Ting Hung, and credited places named only in the post body (Oases,
Sweetgreen) to the comment. The comment-mode intro says "A place named only
in the context counts when the comment says anything about it", which is
looser than meant.

**In `SCOPE`, change the not-places clause to:**

```
supermarkets and grocery stores (H Mart, Trader Joe's, Whole Foods, Key Food)
```

**In `v6_comment.py`, replace the "A place named only in the context counts..." sentence with:**

```
A place named only in the context is a mention only when the COMMENT refers to it: by name, as "it", "they" or "this place", or by replying to a verdict on it ("v mid", "the line is brutal", "hard disagree"). Places the post or parent lists that the comment doesn't refer to belong to those authors, not to this comment. Most negative opinions are in these replies.
```

- **Fixes:** extra mentions (part of the 112 mention-level errors) and
  notes or levels credited from the post (several "notes wrong" grades).
- **Cost:** about +45 tokens.
- **Blocked on:** gourmet stores with deli counters such as Zabar's
  (Q0031, Q0048, Q0272, Q0400, Q0416, Q0468), food halls and markets
  (Q0084, Q0491), and clubs that serve drinks (Q0243, Q0354, Q0500). Add
  them to the named list once decided.
- **Optional, medium confidence:** wrap the user message's parts in tags
  (`<post_title>`, `<post_body>`, `<parent_comment>`, `<comment>`) by
  adding `build_user_message` to `v6_comment.py`. `run.py` already
  re-renders with it. This makes the comment/context boundary explicit.
  It costs about 15 uncached input tokens per call and requires the
  production renderer in `prompt.py` to match. Source: [bp] §Structure
  prompts with XML tags ("especially when your prompt mixes instructions,
  context, examples, and variable inputs").

### 6. Put evidence fields before verdict fields in the schema (test)

**Problem.** Structured outputs emit properties in schema order, and all
v6 properties are required, so the order is exact [so]. Haiku currently
commits to `opinion` and `overall` before it writes `dishes` and `notes`.
On a call with no thinking, the JSON *is* the reasoning, so writing the
verdict first and the detail last works against rules 2 and 7 and against
the strongest-point rule.

**Proposed mention order:**

`name, named_in, location, dishes, notes, experience, opinion, aspects, overall, avoid, price, timeframe, trend, status, tags`

Thread mode keeps `id` first.

- **Fixes:** complaints kept only in notes, dish entries missing while the
  dish appears in a note (several of the 38: "chalupa", "reg slice",
  "spread", "side kimchi"), overall null after a judged dish.
- **Cost:** 0 tokens. One cache rewrite and a grammar recompile.
- **Risk:** more notes. Run an A/B on the 600 items, since this is a
  schema change and the strongest model should review it per `CLAUDE.md`.
- **Do not** add a free-text "reasoning" property. [so] warns such a
  property may draw a `reasoning_extraction` refusal on models that have
  that category. Haiku's documented categories don't include it, but
  thinking is the supported channel anyway.
- **Sources:** [so] (property ordering; "Ask for a short explanation
  instead" of reasoning). [sonnet] (JSON-only responses can only reason in
  thinking).

### 7. Replace the single full-JSON example with 4–5 short contrastive examples

**Problem.** One example, all-negative, in full JSON. [bp] recommends 3–5
relevant, diverse examples in `<example>` tags, and says worked examples
shape the model's thinking when each gives "a problem, the method to
apply, and the expected answer". [audit] 1c names the single gold output as
an over-indexing risk. With a strict schema, the examples no longer need to
show the format, so write them compactly and spend the tokens on the
judgment calls Haiku gets wrong. All places are invented, per the
`v6_common` rule.

**Replace `EXAMPLE` with:**

```
<examples>
Illustrative only; your output always follows the schema.

<example>
Post title: Best steakhouse for a birthday?
Comment: Brindle House or Copperline. Get the creamed spinach at Brindle.
Brindle House: experience firsthand (their own pick; nobody else credited), opinion endorse, overall positive; dish creamed spinach positive ("get the X").
Copperline: firsthand, endorse, overall positive.
</example>

<example>
Comment: Saffron Table has the best biryani in the city. The room is so so cozy and the staff are top notch, but skip the lamb, it was dry.
Saffron Table: stated; overall and taste very_positive ("best ... in the city" ranks it above a broad class); atmosphere positive and service positive (strong praise that ranks nothing); dishes biryani very_positive, lamb negative with avoid true; place avoid false.
</example>

<example>
Post title: Trip report: Pearl Alley, Noodle Barn, Kettle & Crumb
Comment: Noodle Barn was mid, not worth that line. Grabbed snacks at H Mart after.
Noodle Barn: firsthand, stated, overall negative and taste negative ("mid" is lukewarm), wait negative.
No mention for Pearl Alley or Kettle & Crumb (only the post names them) or H Mart (a grocery store).
</example>

<example>
Comment: Never been to Lucky Fold but my cousin swears by it. Twin Lantern was fine, though their scallion pancake is great.
Lucky Fold: secondhand (credited to the cousin), stated, overall positive.
Twin Lantern: firsthand, stated, overall negative ("fine" is lukewarm); dish scallion pancake positive.
</example>

<example>
Parent comment: Golden Lotus has the best hand-pulled noodles in Queens
Comment: lol no. noodles were gummy and $24 a bowl is a joke. go early if you do go, line by noon
Golden Lotus (named in context): firsthand, stated, overall negative; taste negative, value negative, wait negative; dish noodles negative; notes "$24 a bowl" (price, negative, dish noodles) and "go early, line by noon" (best time to go).
</example>
</examples>
```

- **Fixes:** over-scaling (example 2), endorse→positive and own picks as
  firsthand (example 1), post-only places and grocery stores (example 3),
  secondhand vs firsthand and lukewarm (example 4), dishes and notes
  alongside levels (example 5).
- **Cost:** about +130 tokens net (about 460 new minus about 330 removed).
  No output change expected.
- **Before shipping:** each example must agree with the owner decisions
  in §5. Example 2's "best ... in the city" setting taste very_positive
  matches the prompt's existing "best slice in the city" line. If the
  owner picks option B in item 2, example 3's overall still holds, because
  "mid" is a taste verdict.
- **Sources:** [bp] §Use examples effectively ("Include 3–5 examples";
  "Relevant / Diverse / Structured", wrapped in `<example>` tags). [bp]
  §Leverage thinking ("Multishot examples work with thinking... problem,
  the method to apply, and the expected answer"). [audit] 1c (example
  over-indexing) and keep-list item 7.

### 8. XML section tags around the existing blocks

Wrap `WHAT COUNTS`, `FIELDS`, `LEVELS`, `RULES` and the examples in
`<what_counts>`, `<fields>`, `<levels>`, `<rules>` and `<examples>`, and
keep the plain-text bodies.

- **Fixes:** nothing specific. The sections are already clearly headed, so
  the expected gain is small. It helps the self-check and the examples
  refer back to sections unambiguously.
- **Cost:** about +30 tokens.
- **Source:** [bp] §Structure prompts with XML tags.

### 9. Phrasing cleanups (low priority)

- **Rule 4's "Never default to positive":** replaced in item 2.
- **"Output only JSON, {"mentions": [...]}... every field present":**
  structured outputs already guarantee this. Keep only `{"mentions": []}
  when the comment refers to no place.` and `one object per place`. This
  saves about 15 tokens. [audit] 1b lists "output ONLY valid JSON" as a
  scaffold that structured outputs replace. Keep it if the same prompt
  still runs on providers without strict schemas.
- **Capitals:**
  - Keep `COMMENT` and `ORIGINAL POST`. They match the input labels.
  - `ONLY` (rule 1), `NOW` (rule 10) and `THIS` (very_positive) are each
    scoped fixes for a failure the docstring documents. Keep them. [audit]
    1a: "Emphasis is not banned; it is a tested, scoped fix".
- **Rules 3, 6 and 12** state constraints with their reason, which is the
  recommended form. Keep them ([audit] keep-list item 5; [bp] §Add
  context).
- **Cost:** about −15 tokens.

### 10. Request settings (no prompt tokens)

- **`max_tokens`:** ≥16,000 for comment mode, ≥32,000 for thread mode.
  Round 1 truncated at 6k (comment) and 16k (thread). Treat
  `stop_reason == "max_tokens"` as a failed record and retry. Today
  `run.py` treats a truncated record as done (bench_v6/DIAGNOSIS.md).
  Sources: [sonnet], [haiku] §Use effort.
- **Refusals:** branch on `stop_reason == "refusal"` before parsing, and
  log `stop_details.category`. Source: [mig] §Safeguards.
- **Diagnostics:** on a 50–100-comment sample of the error classes, send
  `thinking: {"type": "adaptive", "display": "summarized"}`. It costs
  nothing extra and shows whether Haiku considered the rule it broke.
  Source: [steer] §Pricing.
- **Cache and grammar stability:** keep the system prompt and schema
  byte-identical within a run. Effort is part of the cache key, so pin one
  effort per batch route. Sources: [cache] §Invalidation hierarchy; [so].

---

## 4. Effort: low, medium, or routed

**What the runs show:**

| run | zero-thinking calls | median thinking | mean output | mean cost/call |
|---|---:|---:|---:|---:|
| v6 r3, low | 52% | 0 | 505 | $0.00025 |
| v6r1, low | 47% | 110 | 552 | $0.00017 |
| v6r1, medium (6k cap) | 13% | 475 | 766 | $0.00023 |

The earlier "low beat medium" in comment mode was mostly truncation at the
6k cap plus medium dropping landmark references (DIAGNOSIS.md §3). So
medium has never been measured fairly on the current prompt.

**Recommendation:**

1. **Measure first.** Run the round-3 prompt (plus items 1–3) at **medium
   with `max_tokens` 16k** on the same 600 comments. At about $0.0003 per
   call that is under $0.25. The docs say to try two or three levels on
   your own evals and set effort explicitly [mig] [effort].
2. **If medium wins only on hard comments, route** rather than raising
   everything. Per-message effort [effort] doesn't apply, because each
   comment is a separate one-turn request. Routing means two batch routes,
   each with its own cache entry, which is fine at this volume. Escalate a
   comment to medium when any of these cheap, deterministic triggers hold:
   - **Before the call:**
     - the comment is longer than about 600 characters, or has 3 or more
       list lines or capitalized names (long lists were where thinking and
       truncation concentrated);
     - it is a reply with no place name of its own, so it refers to an
       unnamed context place;
     - it has comparison wording ("better than", "over", "instead",
       "prefer").
   - **After a low call (validators on its output):**
     - `endorse` with a null overall;
     - a very_* level where the comment has no superlative or extreme
       token ("best", "worst", "favorite in", "of my life", "inedible",
       "disgusting", "sick", ...);
     - `secondhand` with no credit word ("friend", "heard", "people",
       "say", "apparently", "my ...");
     - a note with a negative level whose mention has no negative aspect,
       dish or overall;
     - zero mentions when the comment contains capitalized proper nouns.
     These validators are also useful as lint on every run, whatever the
     routing.
3. **The money is small:** medium adds about $0.5–1 per 10k comments in
   batch, so this choice is about accuracy and truncation risk, not cost.
   `xhigh` and `max` are only worth it if evals show a gain, and the docs
   say to compare them with Sonnet 5.5 at that point [haiku].

---

## 5. Schema notes

- **Do property `description` strings reach the model?** The docs say
  `description` is "sent in the schema" and that Claude "automatically
  receives an additional system prompt explaining the expected output
  format" [so]. The measured overhead fits that: about 1.5k tokens of
  injected prompt appear with the schema and not without it. So the schema
  text is in the model's context. The docs don't say how much descriptions
  steer generation, and the general rule for tools is "Claude relies
  heavily on descriptions" [so-skill]. **Recommendation:** don't copy
  `FIELDS` into descriptions. Duplicated rules make the model reconcile
  two wordings ([audit] 1c Padding). If you test descriptions at all, put
  only the one-line decision tests there (experience, opinion) and remove
  them from the prompt in the same change. Changing only descriptions
  doesn't recompile the grammar [so], but it does rewrite the prompt cache
  once.
- **Enums:**
  - Lowercase snake_case is fine. The docs warn that capitalization of
    enum values isn't guaranteed, so compare case-insensitively [so].
  - `experience` and `opinion` both use `"none"` with different meanings.
    Rename one if the schema changes anyway (item 4).
  - The level enum's order (very_positive first) is not known to bias
    choice. No source says it does, so leave it.
- **Union-type limit:** strict schemas allow 16 parameters with `anyOf` or
  type arrays, and these "create exponential compilation cost" [so]. v6
  has about 13: overall, 5 aspects, dish.level, note.level, note.dish,
  location, price, trend and status. `strict_schema` turns them into
  `anyOf`. Don't add new nullable fields. Prefer non-null strings or
  arrays (for example `""` or `[]`) for anything new.
- **Property order is generation order** (all required): see item 6.
- **Keep everything required,** as now. Each optional parameter "roughly
  doubles a portion of the grammar's state space" [so].

---

## 6. Owner decisions that block prompt edits

These came up repeatedly as rule questions in the round-3 review, and the
prompt can't be calibrated until they are settled:

1. Are "terrible" and "awful" very_negative or negative? (Q0113, Q0374,
   Q0445) Is "to die for" or "unreal" positive or very_positive? (Q0127)
2. Does a verdict on one aspect alone set overall? (Q0020, Q0132, Q0178,
   Q0223, Q0392)
3. Grocery and gourmet stores with deli counters (Zabar's), food halls and
   markets, and drink-serving clubs: places or not? (Q0031, Q0084, Q0243,
   Q0272, Q0468, Q0491)
4. Impressions of untried places ("looks so good", "can't wait to try"):
   stated with experience none, endorse, or opinion none? (Q0004, Q0025,
   Q0114, Q0200, Q0438)

---

## 7. Suggested order of work

1. Settle §6. Apply items 1, 2 and 4, plus the endorse normalizer in code.
   One A/B at low against round 3.
2. Add item 3 (self-check) as its own A/B, and record the zero-thinking
   share.
3. Add item 7 (examples) and item 5 (scope). One A/B.
4. Run the medium effort sweep with 16k max_tokens (§4), then decide on
   routing.
5. Schema reorder (item 6) last, on its own, since it touches the schema
   shared by production.

All runs write production-irrelevant eval files only. Extraction runs
against production data still go through the orchestrator, per
`CLAUDE.md`.
