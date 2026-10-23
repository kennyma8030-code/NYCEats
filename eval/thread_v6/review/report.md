# Thread-mode review

Judged 404 of 404 items.

| | items | item_ok_rate | mention_recall | mention_precision | negative_recall |
|---|---:|---:|---:|---:|---:|
| comment mode, fresh-med (round 4) | 300 | 0.791 | 0.935 | 0.972 | 0.884 |
| big-med32k | 139 | 0.85 | 0.975 | 0.992 | 0.96 |
| big-med32k-posts | 2 | 1.0 | 1.0 | 1.0 | None |
| fresh-low | 300 | 0.704 | 0.913 | 0.953 | 0.81 |
| fresh-low-posts | 130 | 0.79 | 0.96 | 0.979 | 0.75 |
| fresh-med32k | 300 | 0.766 | 0.955 | 0.951 | 0.837 |
| fresh-med32k-posts | 130 | 0.811 | 0.99 | 0.995 | 0.706 |
| recent-med32k | 104 | 0.796 | 0.959 | 0.979 | 0.786 |
| recent-med32k-posts | 5 | 1.0 | 1.0 | 1.0 | 1.0 |
| v1-low | 92 | 0.659 | 0.849 | 0.957 | 0.625 |
| v1-med32k | 86 | 0.786 | 0.906 | 0.941 | 0.714 |
| v2half-med32k | 146 | 0.511 | 0.955 | 0.977 | 0.879 |

Misattributed mentions: {'big-med32k': 1, 'v1-med32k': 1, 'fresh-med32k': 1, 'v1-low': 1}
Planted catch: {'drop_dish': {'caught': 3, 'n': 3}, 'drop_mention': {'caught': 12, 'n': 12}, 'flip_overall': {'caught': 8, 'n': 8}, 'foreign_mention': {'caught': 18, 'n': 18}, 'upgrade_negative': {'caught': 1, 'n': 1}, 'wrong_experience': {'caught': 15, 'n': 17}}

## Side by side with round 4's comment mode (same comments, same effort)

Judged 338 of 338 pairs; identical without a judge: {'fresh-med32k': 212, 'fresh-low': 176, 'v1-low': 66, 'v1-med32k': 69, 'v2half-med32k': 63}.

| thread run | comments | thread fully right | comment fully right | thread better | comment better | same |
|---|---:|---:|---:|---:|---:|---:|
| fresh-low | 300 | 0.704 | 0.62 | 82 | 40 | 178 |
| fresh-med32k | 300 | 0.766 | 0.771 | 31 | 44 | 225 |
| v1-low | 92 | 0.659 | 0.659 | 14 | 10 | 68 |
| v1-med32k | 86 | 0.786 | 0.881 | 4 | 11 | 71 |
| v2half-med32k | 146 | 0.511 | 0.529 | 34 | 42 | 70 |

**fresh-low, thread mode better**: {'level': 29, 'missed_place': 24, 'opinion': 19, 'dish': 10, 'experience': 8, 'polarity': 8, 'added_place': 6, 'other': 4, 'attribution': 2}
- t1_jg8llb2: A drops the untried 'Looks good, thanks' reply about Emperor Dumplings; B records it.
- t1_jgutq3r: B raises 'excellent vibe' to superlative atmosphere praise with no city-wide word.
- t1_jofbmf4: A extracts the 'it's good, cheap food' praise for PJ Clarke's with price cheap; B misses the place entirely.
- t1_ju07ovh: A drops Pop Up Bagels, which 'I will try it' refers to; B records it as untried.
- t1_jvqgzq8: B gives the hedged Thai Villa pick its overall praise from 'stunning interior'; A leaves overall null; both miss Semma's hard-to-book wait knock.

**fresh-low, comment mode better**: {'level': 16, 'opinion': 11, 'dish': 11, 'missed_place': 9, 'added_place': 7, 'experience': 6, 'polarity': 4, 'other': 4, 'attribution': 1}
- t1_j7a8w7v: A invents a mention of Fini, which the comment never names, and leaves the knocked slice unrated; B is right.
- t1_jbojutb: A carries the agreed praise for the buns and wings and keeps taste praise with the ramen knock; B calls taste mixed and files a vague 'other dishes' entry instead.
- t1_kgeemqi: B splits Peppercorn Station and its Chinese name 青花椒 into two mentions, double-counting one pick; A keeps one.
- t1_kw6gbym: A misses 7th St. and Halal Guys, mislocates Gotham on 7th St and calls 'good for a burger' a bare endorse; both leave the Korean fried chicken and pizza picks without dish praise.
- t1_lai5yy2: A gives Pata Market the 'best spot' praise for durian (overstated as superlative), while B hands the verdict to Miami Fruit as a stall inside the market and leaves Pata Market opinion none.

**fresh-med32k, thread mode better**: {'missed_place': 17, 'level': 5, 'polarity': 3, 'opinion': 3, 'added_place': 3, 'attribution': 2, 'dish': 2, 'experience': 2, 'other': 2}
- t1_j9f8guo: B gives Nneji a knock though it is one of the commenter's 'favorites'; A's only slip is copying the praise into taste.
- t1_jg8llb2: B drops the untried 'Looks good, thanks' reply about Emperor Dumplings; A records it.
- t1_jgd6jqo: B misses the nameless reply praising Mr. Dips' burgers; A has it with the dish.
- t1_l4cr3cq: A ties 'Get the fries' to Little Pepper from the parent as an endorse with dish praise; B misses it.
- t1_lxxeypt: A keeps The Grill as an endorsed pick with a budget note, while B turns it into an opinion-none mention; both skip the atmosphere praise the question implies.

**fresh-med32k, comment mode better**: {'level': 16, 'missed_place': 11, 'dish': 11, 'opinion': 10, 'added_place': 8, 'other': 5, 'experience': 4, 'attribution': 2}
- t1_io8ayf7: B drops Claro, which 'I'll check it out' refers to; A records it as untried.
- t1_j2c2c8r: B turns a 'love it or hate it' pick into a stated mixed verdict; A keeps it an endorse with praise.
- t1_jzf6uzx: B extracts Mamouns with the lone-exception falafel praise, the taste knock and most dish verdicts; A returns nothing.
- t1_jzr6yez: B turns complaints about the chain's communications team into a service and overall knock; A keeps them as notes with no level.
- t1_ki0159y: A calls the fit remark on Tamarind stated and leaves the endorsed Semma without overall praise; B has Tamarind as no verdict and Semma as endorse with praise.

**v1-low, thread mode better**: {'missed_place': 6, 'level': 5, 'opinion': 4, 'polarity': 2, 'experience': 2, 'dish': 2}
- t1_nlee9b4: A marks the recommender's own 'delicious' pick as experience none and a bare endorse and misses 'super quick' as wait praise; B gets all three.
- t1_o256pyx: A flips Westville to an overall knock though the commenter says 'I like westville and order from them quite a bit'; B keeps overall praise.
- t1_oon6ugv: B drops Taste Good (East Elmhurst) entirely, likely reading the name as a phrase; A extracts it with praise.
- t1_ooni9fm: A marks the pick as experience none with the asked-for dish unrated; B gives it firsthand endorse with mie goreng and taste praise per rule 6.
- t1_p31zbsv: A drops EMP, which the reply refers to with menu facts; B records it as an opinion-none mention.

**v1-low, comment mode better**: {'opinion': 6, 'missed_place': 4, 'dish': 1, 'polarity': 1, 'level': 1}
- t1_nl4zysc: B calls a bare 'gotta go' pick opinion stated; A correctly has endorse.
- t1_nleeujt: B drops the OP's untried thank-you reaction to Zoom Zib, which refers to it as 'this' and 'it'; A records it as an opinion-none mention.
- t1_o25cmbj: B drops the boycott reply about Sweetgreen; A records it as an opinion-none mention with a boycott note.
- t1_ox2u9mb: B turns business news (closures, a visibly dead shop) into an overall knock; A keeps it opinion none.
- t1_o255q7c: B rates the veggie sandwiches as praise and the comment as stated; A leaves the dish unrated and calls it a bare endorse.

**v1-med32k, thread mode better**: {'polarity': 2, 'missed_place': 1, 'opinion': 1, 'experience': 1}
- t1_o3m9fu3: A drops the photo question about Noona's; B records it as an untried opinion-none mention as in the Lucky Fold example.
- t1_p6puvov: B flips Mama's Too's overall to a knock although the comment calls it 'pretty good' and only loses it on price and line.
- t1_p0hwhxl: A treats Emilio's Ballato and Arthur & Sons, named as 'the only real options for a parm', as no-verdict examples; B gives them picks (though neither adds the parm dish or the price complaint).
- t1_p6vw2ux: A knocks Mama's Too's taste as the comparison's loser although the commenter calls it good, while B only leaves taste null.

**v1-med32k, comment mode better**: {'missed_place': 5, 'other': 3, 'added_place': 2, 'polarity': 2, 'opinion': 1, 'dish': 1, 'level': 1}
- t1_o2ekx7n: A treats a recommendation answering the post as a bare fact with no verdict; B correctly has an endorse with praise.
- t1_omg1q43: A misses the dish tip that answers the post about Sofreh; B keeps it as an endorse.
- t1_owmaom5: A misses McDonald's, whose McNuggets the comment calls 'bomb'; B has the praise.
- t1_ozujedh: B drops Mama's Too, named as a landmark ('a couple blocks from mamas'); A keeps it as an opinion-none mention.
- t1_o25j5zj: A turns Rooted's overall into a knock despite it being offered as a healthy pick, while B keeps it praise; B's only slip is a past timeframe for sweetgreen's present decline.

**v2half-med32k, thread mode better**: {'level': 17, 'dish': 8, 'missed_place': 7, 'opinion': 5, 'other': 4, 'added_place': 4, 'polarity': 4, 'experience': 3, 'attribution': 1}
- t1_njccozj: A turns a sympathetic reaction to another user's story into a firsthand service and overall knock; B correctly keeps it an opinion-none mention.
- t1_noo36x6: A turns the 'don't break the bank' price remark into value praise for Amanda's; B keeps it as price and a note.
- t1_ofnmpk3: B lowers Carbone's overall from a remark only about getting a table; A keeps it a wait knock with overall null.
- t1_omzxv6c: B credits the praise to Parm, the restaurant the commenter just panned, instead of Palm, whose parm the parent named.
- t1_oon6ugv: B catches the place (as a truncated 'Taste') with its praise, missing only the asked-about dish; A misses the place, likely mistaking 'Taste good' for a phrase.

**v2half-med32k, comment mode better**: {'dish': 17, 'level': 17, 'missed_place': 11, 'opinion': 10, 'polarity': 4, 'other': 3, 'experience': 3, 'added_place': 1}
- t1_jrqd79z: A gives Parm overall praise despite the only verdict being undercooked meatballs sent back; B gives it the knock.
- t1_nopix7b: B turns Adel's pickup markup, a fee paid as a workaround, into a value knock; A keeps it a note (A's only extra is a 'biryani' dish taken from the name).
- t1_nt72q0q: Both miss the closure and the value point; A also turns the fond 'amazing sub I miss dearly' into an overall mixed verdict, where B keeps praise.
- t1_nx532u2: B gives each bare pick the bread the question asks about (dish and taste praise), as rule 6 says; A leaves Rolos, Diner and Shewolf without the dish.
- t1_o65rrko: A sets overall mixed for a pick answering the question; B gives the pick overall praise as the rules say.
