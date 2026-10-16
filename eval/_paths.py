"""The one place that knows where eval/ lives, and puts its importable code on sys.path.

Every entry point and tool imports this first. Scripts at the top of eval/ can
`import _paths` directly. A script in a subfolder first puts eval/ on the path
with `sys.path.insert(0, dirname(dirname(abspath(__file__))))`, because Python
only adds the script's own folder. After that, `import providers`, `import run`
and `import score` work from anywhere, and the paths below never need to be
rebuilt from `__file__`.
"""

import os
import sys

EVAL = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(EVAL)                # the repo root: extract.py, prompt.py, .env
LIB = os.path.join(EVAL, "lib")             # providers.py, schema_v5.py
DATA = os.path.join(EVAL, "data")           # alias_overrides.json, excluded_entities.json

for _p in (LIB, EVAL):
    if _p not in sys.path:
        sys.path.insert(0, _p)
