"""rubric_v1, comment mode: one Reddit comment in, its restaurant mentions out.

Inputs are production's own comment-mode rendering (title, first 400 chars of the
post, the parent comment, the comment); only the system prompt changes.
"""
import importlib.util, os

_spec = importlib.util.spec_from_file_location(
    "rubric_v1_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric_v1_common.py"))
_c = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_c)

SYSTEM_PROMPT = f"""You extract restaurant mentions from ONE Reddit comment posted in a New York City food subreddit.

You are given the post title, usually the post body, sometimes the parent comment, and then the comment itself. The context exists only to make sense of the comment. Extract from the COMMENT. Never extract a place that is only named in the title, body, or parent -- unless the comment says something about it. A reply that gives an opinion without repeating the name IS a mention of the place it replies about; these replies carry most of the negative opinions, so do not drop them.

Output ONLY a JSON object, no prose, no code fences:

{{"mentions": [ {{...}}, {{...}} ]}}

Use {{"mentions": []}} only when the comment names and refers to no place at all.

{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

{_c.EXAMPLES_COMMENT}"""
