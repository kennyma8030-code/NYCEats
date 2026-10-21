"""Exactly what prompts_v6/v6_thread.py adds to the round-4 thread prompt.

The vendored file is extraction-v6:eval/prompts/v6_thread.py with these
replacements applied, in order, and nothing else; tests/test_prompt_v6.py
applies them to the branch's bytes and compares. So this list is the whole
reviewable diff against what the benchmark ran:

  1. a docstring paragraph saying what production added;
  2. constants for the two additions;
  3. render_chunk takes `above` (quoted ancestor chains) and `post_item` (the
     post as item [0]), documented in its docstring;
  4. the rendering of both, between the post and the comments;
  5. [0] in the id map when the post is an item;
  6. the <post_item> section of the system prompt, after <input>. Its
     sentences are post mode's (prompts_v6/v6_comment.py SYSTEM_PROMPT_POST,
     <input>), with "here" made "for item 0". It changes the prompt hash.
"""

ADDITIONS = [
    ('''module defines it.
"""
''', '''module defines it.

Production (prompts_v6/v6_thread.py) is this file plus two additions, each
marked "production addition" below and listed in tests/v6_thread_additions.py:
  * the post can be an item, "[0] POST: ...", extracted under post mode's
    rules (<post_item> in the prompt, which therefore has its own hash);
  * a chunk whose comments hang under comments outside it quotes their whole
    ancestor chains above its comments, as context lines with no number.
"""
'''),
    ('''MAX_INDENT = 6             # indentation is a reading aid now; the marker carries the parent
''', '''MAX_INDENT = 6             # indentation is a reading aid now; the marker carries the parent
# production addition: the post as item [0] gets post mode's body cut, and a
# quoted ancestor the full comment cut, because both are read for what they say.
POST_ITEM_CHARS = 4000
CONTEXT_CHARS = MAX_COMMENT_CHARS
CONTEXT_HEADER = "Earlier comments in this thread, quoted as context (not in this chunk; never extract from them):"
'''),
    ('''def render_chunk(title, selftext, rows, outside=None):
''', '''def render_chunk(title, selftext, rows, outside=None, above=None, post_item=None):
'''),
    ('''      database; "[deleted]" / "[removed]" bodies are said to be deleted.
    """
    outside = outside or {}
    ordered = depth_first(rows)
    num = {r["comment_id"]: n for n, (r, _) in enumerate(ordered, start=1)}
    parts = [f"POST: {_flat(title)}"]
    body = _flat(selftext)
    if body:
        parts.append(_cut(body, SELFTEXT_LIMIT))
    parts.append("")
''', '''      database; "[deleted]" / "[removed]" bodies are said to be deleted.
    above (production addition): context lines quoted between the post and
      the comments, [(depth, author, body, parent)] in thread order, body
      None for a deleted comment, parent what it answers ("[3]", "u/zed",
      "a deleted comment") or None for a top-level one. Unnumbered, so no
      mention can name them.
    post_item (production addition): the thread id when the post is an item
      to extract. It is numbered [0], its body is cut at POST_ITEM_CHARS, and
      the map gets {0: post_item}.
    """
    outside = outside or {}
    ordered = depth_first(rows)
    num = {r["comment_id"]: n for n, (r, _) in enumerate(ordered, start=1)}
    parts = [f"{'[0] ' if post_item else ''}POST: {_flat(title)}"]
    body = _flat(selftext)
    if body:
        parts.append(_cut(body, POST_ITEM_CHARS if post_item else SELFTEXT_LIMIT))
    parts.append("")
    if above:
        parts.append(CONTEXT_HEADER)
        for depth, author, text, parent in above:
            to = f" (reply to {parent})" if parent else ""
            line = (f"u/{author or '?'}{to}: \\"{_cut(_flat(text), CONTEXT_CHARS)}\\"" if text is not None
                    else f"(a deleted comment{', reply to ' + parent if parent else ''})")
            parts.append(f"{'  ' * min(depth, MAX_INDENT)}{line}")
        parts.append("")
'''),
    ('''    return "\\n".join(parts), {n: cid for cid, n in num.items()}
''', '''    ids = {n: cid for cid, n in num.items()}
    if post_item:
        ids[0] = post_item
    return "\\n".join(parts), ids
'''),
    ('''</input>

One object per place per comment.
''', '''</input>

<post_item>
When the post itself is numbered, "[0] POST: ...", it is an item too: extract its title and body, written by the poster, and its mentions carry "id" 0. Extract the places the post names and what the poster says about them, their own visits and verdicts included. A place the post only asks about ("is X worth it?") is a mention with opinion "none". named_in is always "comment" for item 0. A post with no number is context only.
</post_item>

One object per place per comment.
'''),
]


def apply(text):
    for old, new in ADDITIONS:
        if text.count(old) != 1:
            raise ValueError(f"round-4 text not found exactly once: {old[:60]!r}")
        text = text.replace(old, new)
    return text
