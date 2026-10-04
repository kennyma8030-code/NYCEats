"""rubric_v1, thread mode: one post plus an indented comment tree in, mentions out.

Inputs are production's own thread-mode rendering (chunks of 25 comments with
bracket ids); only the system prompt changes.
"""
import importlib.util, os

_spec = importlib.util.spec_from_file_location(
    "rubric_v1_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric_v1_common.py"))
_c = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_c)

SYSTEM_PROMPT = f"""You extract restaurant mentions from a Reddit thread in a New York City food subreddit.

You are given the post, then its comments as an indented tree. Each comment starts with a number in brackets. Indentation means a reply: a comment indented under another is replying to it.

Output ONLY a JSON object, no prose, no code fences:

{{"mentions": [ {{"id": 3, ...}}, {{"id": 7, ...}} ]}}

Every mention carries the bracket number of the comment it came from. A comment naming three places produces three entries with the same id. NEVER invent an id; only use numbers that appear in brackets. Go through EVERY comment: a short reply is easy to skip and is often the only negative opinion in the thread.

USING THE TREE

A reply is about its parent unless it names something else. "Overrated" indented under a comment praising a place is a mention of that place -- under the REPLY's id, because it is the replier's opinion. "Hard disagree" under "X is overrated" is a positive mention of X.

id                 integer. The bracket number of the comment this came from.
{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

EXAMPLE (invented places)

POST: Best noodles in Queens?

[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob: pepper house is overrated and $28 for noodles is a joke
    [3] u/ann: hard disagree, the cumin lamb is worth it
[4] u/cal: Avoid both. Try Noodle Lab, and skip their dumplings

{{"mentions":[
{{"id":1,"restaurant_raw":"Golden Lotus","neighborhood_hint":null,"dishes":[],"dish_sentiment":[],"descriptors":[],"aspects":{{"food":0.33,"value":null,"service":null,"atmosphere":null,"wait":null}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":false}},
{{"id":1,"restaurant_raw":"Pepper House","neighborhood_hint":null,"dishes":[],"dish_sentiment":[],"descriptors":[],"aspects":{{"food":0.33,"value":null,"service":null,"atmosphere":null,"wait":-0.33}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":false}},
{{"id":2,"restaurant_raw":"pepper house","neighborhood_hint":null,"dishes":["noodles"],"dish_sentiment":[{{"dish":"noodles","level":null,"avoid":false}}],"descriptors":["overrated"],"aspects":{{"food":-0.33,"value":-0.67,"service":null,"atmosphere":null,"wait":null}},"expensiveness":0.33,"value_complaint":true,"is_firsthand":true,"is_negated":false}},
{{"id":3,"restaurant_raw":"pepper house","neighborhood_hint":null,"dishes":["cumin lamb"],"dish_sentiment":[{{"dish":"cumin lamb","level":0.67,"avoid":false}}],"descriptors":[],"aspects":{{"food":0.67,"value":0.33,"service":null,"atmosphere":null,"wait":null}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":false}},
{{"id":4,"restaurant_raw":"Golden Lotus","neighborhood_hint":null,"dishes":[],"dish_sentiment":[],"descriptors":[],"aspects":{{"food":-0.67,"value":null,"service":null,"atmosphere":null,"wait":null}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":true}},
{{"id":4,"restaurant_raw":"Pepper House","neighborhood_hint":null,"dishes":[],"dish_sentiment":[],"descriptors":[],"aspects":{{"food":-0.67,"value":null,"service":null,"atmosphere":null,"wait":null}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":true}},
{{"id":4,"restaurant_raw":"Noodle Lab","neighborhood_hint":null,"dishes":["dumplings"],"dish_sentiment":[{{"dish":"dumplings","level":-0.67,"avoid":true}}],"descriptors":[],"aspects":{{"food":0.33,"value":null,"service":null,"atmosphere":null,"wait":null}},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":false}}]}}

Comment 3 names nothing but disagrees with comment 2, so it is a positive Pepper House mention under id 3. Comment 4's "Avoid both" covers Golden Lotus and Pepper House, emitted under id 4 with is_negated true; its "skip their dumplings" is a dish-level avoid on Noodle Lab, which is still recommended overall."""
