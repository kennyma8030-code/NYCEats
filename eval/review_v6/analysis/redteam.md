# Red-team: how real r/FoodNYC comments break the v6 comment extractor

The 600-item review measures Haiku on the strata the eval was built around. This
note looks for failure modes the eval did not sample, and measures how common they
are in the real corpus. It was written read-only. No model calls were made and
nothing was written to the database.

## Method

- **Corpus sample.** A deterministic 20% hash sample of production comments
  (`md5(id) % 5 = 0`, body not deleted, longer than 15 chars): 136,990 comments,
  each with its post title, its post body (first 1,200 chars) and its parent.
  "Place-bearing" (**pl**) means the comment has at least one stored mention from
  the deepseek production run (19,343 in the sample). That is a proxy: the stored
  extractor misses places too.
- **Probes.** About 95 regex and structural probes (scratch code, not committed).
  For every mode ranked below I read 8 to 15 real hits to estimate precision. The
  "est." column is the regex share times that precision, so it is rough to about a
  factor of 2.
- **Full-corpus SQL** for structural modes: duplicate bodies, how concentrated an
  author is on one place, reservation-sale threads, generic names and duplicates in
  stored mentions.
- **Coverage.** The same probes were run on the 600 review comments (column
  **R**), and Haiku's round-3 output was checked where review items hit a mode.
- **Not repeated here.** Modes another analysis already covers are only cross-referenced:
  [input.md](input.md) covers quote blocks, deleted parents, post-body truncation,
  OP authorship, the 15-character filter and dates.
  [decisions.md](decisions.md) covers untried impressions, boycotts, hygiene,
  markets, branch closures, timeframe, and brands, chefs and companies.
  [errors.md](errors.md) covers sarcasm in general and closure framing in titles.

## Ranked modes (frequency x harm to per-place counts)

Harm: **H** means it distorts a place's counts by a lot (concentrated, or it flips
polarity). **M** means it flips or invents individual mentions. **L** means junk or
cosmetic. "Handled?" refers to the round-3 prompt.

| # | mode | est. share | harm | in R | handled? | fix |
|---|---|---|---|---:|---|---|
| 1 | **Reservation resale/transfer threads** | 2,872 comments corpus-wide; 838 have stored mentions (**0.9% of all place-bearing comments**). **Atomix: 372 of 569 mentions (65%) come from these threads.** Atera 16/57, Frevo 13/41, EMP 10/110 | H | 1 | Haiku marks a listing as opinion none (t1_padzyzp), but it still counts as a mention. "ISO Atomix for 2" could read as wait negative | code |
| 2 | **Lukewarm and qualified words missing from the scale**: "decent" (0.98% pl, about 4x "fine/ok/not bad" combined), "average/mediocre" (0.9%), "good for what it is", "if you're in the area", "not worth the trip" (0.7%), "solid but..." | ~2% pl | M | 19 | No. "pretty decent" went positive (Q0582), "not even decent" went negative; judges split on "average" | prompt (owner call) |
| 3 | **Shill, affiliated and AI-marketing accounts** | 100 author-place pairs (author has ≥3 threads on a place, and that place is ≥60% of the author's place threads), 380 thread-mentions. Ginger Ristorante 12 of 15 mentions from one account, Boro Brine 6/13, Fry Baby 5/9, Chito Gvrito 6/20. Owner accounts (`Dan_at_Ikigai`, `Crescent_Bakes`). A wanderboat.ai account posts verdicts ("bubby's is overrated... tourist trap"). Self-disclosed staff/owner: 0.24% pl | H for small places | 2 | No | code + prompt |
| 4 | **Places outside NYC, and foreign branches of NYC places**: Philly (Angelo's, Uncle Gus's), Jersey City (Alfalfa), NJ (Hanam), Yonkers/Stamford Pepe's, "DTF in Taiwan", "Dishoom in Edinburgh", "Pret in the UK" | regex 4.3% pl, est. ~1% pl. Threads whose title names another city: 1.2% of comments | M (resolve to NYC namesakes: Angelo's, Pepe's, Joe's) | 19 | Scope says no, but Haiku kept Hanam/NJ (Q0076) | prompt + code |
| 5 | **Comparison edge cases not in rule 5**: implicit benchmark praise ("as good as X", "rivals X", "Katz-level"), hearsay comparisons ("a lot of people tell me A is better than B", "someone on Reddit said it beats Polo Bar"), "A beats B, but they're all very good", the NYC branch vs the original abroad | est. ~0.8% pl (regex 3.5%; "better than/over/as good as" + a famous name 0.14% of all) | M (famous benchmarks pile up negatives) | 17 | Partly | prompt |
| 6 | **Thread title implies closure** ("restaurants I miss", "bring back one closed restaurant"): bare-name answers lose status closed | bare names under closure titles: 0.68% pl. Under negative titles ("worst", "overrated"): 0.44% pl | M (closed places ranked as current) | 12 | No: Q0080 missed closed for 2 places. errors.md already proposes the fix; the numbers here back it | prompt |
| 7 | **"for the price" is read only as a complaint**. Rule 6 lists it, but about half of real uses are praise: "Best joint in the city for the price", "fabulous, especially for the price", "big portion for the price" | 0.26% pl, ~50% praise | M (value flips) | 0 | The rule invites the error | prompt |
| 8 | **People, brands and products read as places**: an Instagram creator ("Love Julian Mu"), a Reddit user ("#teamKenneth"), chefs standing for restaurants (Michael White → Santi), deli-meat brands (Boar's Head stored with "uppity"), D'Artagnan, Wild Fork, "Rao's" jar vs restaurant | chef 0.54% pl, brand 0.36% pl | L-M | 5 | Partly (decisions.md #19) | prompt |
| 9 | **Numeric scores and tiers**: "maybe an 8/10 but not god tier", "no way swirlies gets 10/10", "close to a perfect 10/10", "A tier slightly below would be X" | 0.62% pl | M | **0** | No mapping | prompt (owner) |
| 10 | **Replies about a whole list**: "great list but skip X", "your list is full of tourist traps", "+1 to all", "agree with all except #3" | 0.3-0.5% pl | M (one reply fans out to N mentions, or a knock goes nowhere) | 9 | Partly (Q0309) | prompt |
| 11 | **Awards, critics and review-site scores read as verdicts**: "Michelin 1 star", "4.9 on Google", Portnoy scores, "Pete Wells panned it" | regex 0.94% pl, ~40% real | L-M | 9 | No | prompt |
| 12 | **Initialisms and nicknames**: EMP 146, JG 132 (JG Melon or Jean-Georges), L&B 127, DTF 91, BCD 51, R&D 20, XFF 18, SB 16, RHT 14, S&W 14, PL 13 | ~0.5% of all comments | M for those places (resolution) | 4 | The name is kept as typed; resolution needs aliases | code + one prompt line |
| 13 | **Sarcasm conventions**: "/s" ("Western Beef /s", "Carlos bakery at Port Authority (not sure if /s is needed)"); the Times Square chain joke ("olive garden / planet hollywood / hard rock / applebees, which one you picking hahah", "And Olive Garden!!") | /s 0.06% pl; chain jokes ~0.2% pl | M per item (sign flips) | 2 | Rule 11 is generic; the markers aren't named | prompt |
| 14 | **Renamed, successor, sister and licensed versions**: "Ladybird Bakery (formerly Two Little Red Hens)" gives 2 mentions; "Golden Hof... same owner"; "SriPraPhai by Wonder"; "Bukas Cafe replaced Pata Cafe" | ~0.5% pl | L-M | 7 | No | prompt + code alias |
| 15 | **Pronouns and generic kinds as names** (stored): "it" 116, "this place" 63, "they" 59, "that place" 38, "diner" 32, "coffee shop" 29, "halal cart(s)" 16, "bodega" 10 | 0.35% + 0.25% of stored mentions | L (junk entities) | - | v6 says copy from context; untested at scale | code filter |
| 16 | **Same place twice in one comment**: Katz / Katz's, Claud's / Claude's, "Tompkins square" / "Tompkins Square Bagels", "Unos" / "Unos in Brooklyn" | 1.0% of comments with more than one mention | L (double count) | - | The prompt says one mention; the stored run broke it | code (merge by entity after resolution) |
| 17 | Emoji as the only sentiment ("Bagock on Montrose 💔", "closed by the health dept 🤢", "Portale 🔥🔥🔥") | 0.81% pl | L | 3 | Not named | prompt |
| 18 | Fees: auto-gratuity, card surcharges ("35% surcharge... straight robbing people") | 0.21% pl | L | 1 | Not named | prompt |
| 19 | Place identified only by a link ("This place. yelp.com/biz/financier-patisserie-...", "[The Laksa Shop](instagram)") | 0.1% of all | L | 1 | No | code (expand slugs) |
| 20 | Retractions ("Edit: it was St. Mark's, not Pauls da burger joint") | 0.06% pl | L | 0 | No | prompt |
| 21 | Bots and verbatim duplicates across authors (AutoModerator, grammar bots, sock-puppet promo text posted twice) | bots 0.48% of all (0.04% pl); 56 extra copies corpus-wide | L | 2 | - | code |

### Checked and judged low risk for Haiku

These are listed so they aren't re-investigated. pl share in parentheses.

| mode | share | note |
|---|---|---|
| conditionals "if you like X, Y is great" | 1.9% pl | almost always plain praise for Y |
| slang with mixed polarity ("insane line" vs "insane garlic slice", "stupid good", "criminal") | 3.1% pl regex | the prompt already lists "the line is insane"; the rest reads naturally |
| dietary context ("as a non-vegan", "sesame-free") | 1.9% pl | mostly tags; real complaints ("not vegetarian friendly") ~0.01% |
| delivery and apps | 0.9% pl | delivery-specific complaints ~0.02% (Wonder app "delivered soggy") |
| negated praise ("can't go wrong", "never disappoints", "no complaints", "not bad at all") | 0.34% pl | possible bleed from rule 3 ("not bad" is a knock); a one-line contrast would close it |
| "not the best / not my favorite" | 0.31% pl | lukewarm; covered by rule 3 |
| group opinions ("my husband loved it") | 0.10% pl | secondhand counts the same (owner) |
| street-named places ("Prince St", "2nd Ave", "Grand St skewer cart") | 0.09% of all | the "2nd Ave" example covers it |
| CJK / non-English | 0.08% pl | rare |
| venue, airport and stadium outposts | 0.37% pl | rare and mostly facts |
| pop-ups and supper clubs | 0.45% pl | `status: opened` is misapplied to one-off pop-up events (Q0493) |
| rhetorical questions ("has X gone downhill?") | 0.05% pl | rare |
| meta-commentary ("the amount of l'industrie posts taking over this sub") | 0.31% pl | not a verdict; Haiku mostly agrees |
| very long comments (≥2,000 chars) | 0.10% of all | rare; the long_list stratum covers them |
| "touristy" (not "tourist trap") | 0.5% pl | owner call: atmosphere negative or not |
| multi-visit "hit or miss" | 0.2% pl | neutral is defined |
| untried comparisons ("never been to A but B is better") | 0.01% | rare |
| post-list ordinals past the 400-char cut ("2. on the list", "your #1 pick") | 0.13% of all | input.md proposal 7b covers it. The stored run even made "your #1 pick" a place (t1_peivea3) |
| deleted parent | 0.29% of all | input.md proposal 5. Example: t1_o5f3r42 "Tourist trap / Not a pizzeria / Patsys Pizzerias unrelated" answers a deleted comment, and the context makes it look like a verdict on Patsy's |

## Top 15 additions for the next prompt

All proposed wording uses invented places, per the rule in `v6_common.py`. Items
marked (owner) need a decision before they go in.

1. **(owner) Scale words.** Extend the lukewarm list: "decent", "average", "mediocre",
   "passable", "good for what it is", "fine if you're nearby", "not worth the trip",
   "good, not great" are negative; "pretty decent", "solid" and "worth the trip" are
   positive. "decent" alone is the most common unlisted verdict word on the sub, so
   it is the main call to make.
2. **Fix rule 6's "for the price".** Replace it with: "The word before 'for the price'
   decides: 'great / huge portions for the price' is value positive; 'small /
   not worth it for the price' is value negative."
3. **Reservation listings.** "A reservation offered, wanted or traded ('I have 2 seats
   at Golden Lotus Friday 8pm', 'ISO Pepper House for Saturday') is opinion none:
   no wait level, no endorsement."
4. **Speaking for the place.** "If the commenter speaks for the place ('we', 'our menu',
   'come see us', 'I work there', 'I'm the owner'), its opinion is none and a note
   {about: 'affiliated'} records why; staff praise is not a verdict." (Someone who
   *used to* work there and says so stays a verdict, with the note.)
5. **Outside NYC, and foreign branches.** "Places outside the five boroughs (New Jersey,
   Long Island, Westchester, other cities, abroad) are not mentions, even in a
   comparison. 'Golden Lotus in Tokyo' or 'the original in London' is not the NYC
   Golden Lotus: give the NYC one only what is said about it."
6. **Comparison additions (rule 5).** "'As good as X', 'rivals X' and 'X-level' praise
   X too. A comparison the commenter only reports ('people say A beats B') is
   secondhand. 'A beats B, but they're all great' leaves B positive."
7. **The title as heading (rule 8).** "A title asking about closed places ('which
   closed place would you bring back', 'places I miss') makes each bare name
   status closed, timeframe past, overall positive. A title asking for the worst or
   most overrated makes each bare name negative." This also settles the conflict
   between "endorse is always positive" and rule 11. errors.md has the same fix.
8. **(owner) Scores.** "A score is a level: 9-10/10 or 5/5 positive (very_positive
   only with a superlative); 7-8/10 positive; 5-6/10 negative; 4/10 or lower
   very_negative. 'Top tier' positive, 'mid tier' negative. Disputing someone else's
   high score ('no way it's a 10') is a knock."
9. **Facts, not verdicts.** "Awards, stars, review-site scores and critics' verdicts
   (a Michelin star, '4.8 on Google', a critic's panning) are facts, opinion none,
   unless the commenter adopts them ('deserves its star' is stated; 'the critic was
   right' is secondhand)."
10. **Replies about a whole list.** "A reply about a list as a whole ('great list',
    'all solid') endorses only the places it names. 'Great list, but skip X' gives X
    avoid true. A knock on the whole list that names nothing ('your list is all
    tourist traps') has no mention."
11. **Non-places.** Add to SCOPE: "people (chefs, critics, influencers, other users),
    product brands sold in stores (a jarred sauce, a deli-meat brand) and delivery
    apps. A chef's name is a mention only when it is used for the restaurant
    ('dinner at Chef Marco's'), written as typed."
12. **Sarcasm markers (rule 11).** "'/s' reverses the sentence it ends. Recommending
    tourist-strip chains with 'lol' or 'hahah' is a joke: opinion none."
13. **Renames and versions.** "'Golden Lotus (formerly Lotus House)' or 'Lotus House
    is now Golden Lotus' is one mention named Golden Lotus, with the old name in a
    note. 'Same owners as Pepper House' says nothing about Pepper House. 'Golden Lotus
    by a delivery brand' or 'at the airport' is its own mention, named as typed."
14. **Initials and retractions.** "Initials and nicknames are names: write them as
    typed ('GLN' for Golden Lotus Noodles). A name the commenter takes back ('Edit: I
    meant Pepper House, not Golden Lotus') is not a mention."
15. **Emoji and fees.** "Emoji count as words: a heart, fire or drooling face is
    praise, a vomiting face is a knock, and a broken heart after a name means
    closed and missed. Surprise fees, auto-gratuity and card surcharges are value
    negative."

## Handle outside the model (code)

1. **Thread-genre filter.** Tag reservation sale/transfer/swap threads
   (`title ~* '(reservation|resy|res) (sales|swap|exchange|transfer|trade)'`, 2,872
   comments) and leave their mentions out of every count, or force opinion none and
   drop them from "mentioned by". This is the cheapest fix with the largest
   per-place effect in this note: 65% of Atomix's mentions today.
2. **Author-level shill signal.** Flag an author when one place takes ≥60% of their
   place threads across ≥3 threads, when the username contains a place's key
   (`Dan_at_Ikigai`, `Crescent_Bakes`), or when they post link-spam domains
   (wanderboat.ai and similar). Down-weight or exclude them. Also confirm that
   counting "in people" dedupes by author per place: EmbarrassedMission11 posted
   near-identical Balthazar complaints in 8 threads.
3. **Duplicate bodies.** Collapse identical bodies (≥80 chars) from different
   authors to the earliest (44 groups, 56 extra copies; sock-puppet promo text like
   the "Sesamo" paragraph).
4. **Bot filter** before extraction: AutoModerator, `*bot` authors, RemindMe,
   grammar-correction bodies ("I am a language corrector bot").
5. **Alias table** for initialisms: EMP, DTF, XFF, L&B, R&D, BCD, RHT, S&W, PL, SB,
   LPQ. JG is ambiguous (JG Melon or Jean-Georges) and needs context. alias_overrides
   has 3 rows today.
6. **Name sanity filter** after extraction: reject names that are pronouns or
   generic kinds ("it", "they", "this place", "diner", "coffee shop", "halal cart",
   "bodega", "restaurants") unless `named_in = context`.
7. **Merge duplicates in one comment** after resolution: two mentions that resolve
   to the same entity merge. Don't merge on raw strings: Craft and Craftbar, Misi
   and misipasta, and Jongro BBQ and Jongro Gopchang are different places.
8. **Geography guard.** If the thread title names another city (1.2% of comments) or
   the comment says "in Philly / NJ / Tokyo" next to the name, don't resolve a
   generic name (Angelo's, Pepe's, Joe's) to an NYC entity.
9. **Expand link slugs** into the comment text: `yelp.com/biz/<slug>`,
   `instagram.com/<handle>` and Maps place names become "(link: financier patisserie)".
10. Already proposed in input.md and agreed here: mark quotes, mark a deleted parent,
    mark OP authorship, list the places named in the post.

## Hard-case test set (60 comment ids, none in the 600-item review)

Grouped by mode. All are in the production `comments` table. Quotes are trimmed.

- **Reservation resale**: t1_pc41ju6 (Atomix chef's counter for 2), t1_pd2fxo1
  ("Selling... Atomix Oct 25"), t1_lfqhxcj (Petit Crenn "transferrable at original price")
- **Shill / affiliated / spam**: t1_ot4epji (Ginger Ristorante, one of 12 by one
  account), t1_nisxuul ("we'd love to see you at Ikigai"), t1_ntm8oex (AI-map
  account: "bubby's is overrated... tourist trap"), t1_n3vxgrc ("We just opened a
  brazilian street food kitchen"), t1_pci4chv (the same Balthazar complaint posted in 8 threads)
- **Closure and negative title frames**: t1_nl9cclx ("Spain, Forlini's, Ferdinando's,
  De Maria, Jing Fong's old location"), t1_nldnhap ("NoMad Bar / Best Drinks / Best
  Burger"), t1_nt7bl4a ("Bagock on Montrose 💔"), t1_jrme56w ("One if by land two if
  by sea" under "terrible restaurants with great reviews"), t1_lag6d5q (untried place,
  "decided against it", under "worst food")
- **"for the price" and lukewarm words**: t1_p0041k1 ("decent for the price"), t1_mo5fczz
  ("Best joint in the city for the price"), t1_nhtpca0 ("fabulous, especially for the
  price"), t1_ok8u9i4 ("great for the price, but nothing out of this world"; "not
  worth the price"), t1_o85sm9b ("A tier slightly below would be Let's Meat")
- **Scores**: t1_nrk55ob ("maybe an 8/10 but not the god tier"), t1_nnury2k ("no way
  swirlies gets 10/10, and Win Son and Hani's get 9s")
- **Outside NYC / foreign branch**: t1_p4ugg8u (Philly: Uncle Gus's, Angelo's),
  t1_oiytz4n ("Alfalfa in Jersey City or Hoboken"), t1_o1b7d42 (Pepe's and Sally's
  franchises "trash"), t1_nxigsuj (Dishoom heard bland; New Tayyab's in London),
  t1_k4p2ejz ("Nothing in the states... DTF in Taiwan"), t1_mazwti6 ("In the UK pret
  is legitimately good")
- **Quotes**: t1_jrmks36 (the whole comment quotes someone else's Edinburgh Dishoom
  view), t1_ktbu8m1 (quotes OP's "Day 2: Double Chicken Please... Ci Siamo")
- **Comparisons**: t1_ocbjsfs (Hillstone; "someone on Reddit said it was better than
  the Polo Bar"), t1_p4zv9lf ("A lot of people tell me aces is better than Emmy
  squared or Emily... Do love Emily"), t1_mpm62y8 ("much better than current joes...
  they're all very good"), t1_m7t083y ("almost all of them will be at least as good
  as Halal Guys")
- **Non-places**: t1_o4pfpdz ("Love Julian Mu", an Instagram creator), t1_p82yj2i
  ("#teamKenneth", a user), t1_ostpmfl (Boar's Head), t1_nvh3vnq (chef Michael White
  stands for Santi; "Best pasta in NYC")
- **Initialisms**: t1_m5qrt3y ("Keens over PL, ANYDAY"), t1_o9ygpkb ("cheaper and better
  than S&W")
- **Sarcasm**: t1_ng5zvby (Times Square chain list, "hahah"), t1_nin65d8 ("And Olive
  Garden!!"), t1_peqs11u ("rainbow cake from the port authority Carlos bakery (Not
  sure if /s is needed)"), t1_kxpx76f ("the OG in Times Square has steak and mutton
  now. /s")
- **Renamed / sister / licensed**: t1_nsyph1j ("Ladybird Bakery (formerly known as Two
  Little Red Hens)"), t1_obriz7s ("Golden Hof... Same owner"), t1_oelsyji
  (SriPraPhai and "SriPraPhai by Wonder")
- **Context gaps**: t1_o5f3r42 (deleted parent: "Tourist trap / Not a pizzeria"),
  t1_oo6nogh ("1. Per Se - amazing... 2. on the list"), t1_peivea3 ("your #1 pick...
  Better than most restaurants in Naples"), t1_nkqjqaz (Din Tai Fung named only in the
  title; the stored name was "Corporate facsimile nonsense")
- **Links, retractions, fees, boycotts**: t1_jl3n9pm ("This place." plus a Yelp slug),
  t1_nt64u43 ("Edit: It was St. Mark's... not Pauls da burger joint"), t1_ogwduuc
  ("35% surcharge"), t1_o8m2f63 ("boycotting momofuku since his chili crisp shenanigans")
- **List replies and OP plans**: t1_nrzr2bi ("good list but skip superiority burger"),
  t1_pehs8rp ("your list is full of tourist traps"), t1_p9vhtoc (OP: "I'm gonna go with blue ribbon!")
- **Names**: t1_oa16bxs (Katz and Katz's as 2 mentions), t1_ocldukd ("Halal cart for
  the authentic experience"), t1_ogcb5s6 ("4.9 rating" on Google, an unnamed cart),
  t1_ovd1421 (Portnoy's "mid review" of Totonno's, hearsay)

## Caveats

- The stored mentions that define "place-bearing" and that I counted for names come
  from the old deepseek prompt. Haiku v6 may already avoid some name-level junk
  (modes 15 and 16). Those numbers measure the input risk, not Haiku's error rate.
- Regex shares are upper bounds. Where the mode needs a judgment (sarcasm, shills,
  comparisons), the estimate rests on 8 to 15 hits read by hand.
- Several modes are concentrated. Resale threads and shill accounts matter more per
  place than their corpus share suggests: one account, or one thread genre, can be
  most of a small place's evidence.
