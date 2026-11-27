"""Reading a JSON file that the API can do without.

Shared by the per-city files beside this package (geo.py's locations,
dishes.py's dish groups), so a missing or broken one behaves the same way
everywhere.
"""

import json
import logging

log = logging.getLogger("uvicorn.error")


def load(path, what):
    """The file's parsed contents. A missing or broken file is a warning and
    an empty dict: the lists work without it, and the API should not fail to
    boot over a map or a cleanup file. `what` names the file's contents in the
    warning."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        log.warning("no %s loaded from %s: %s", what, path, e)
        return {}
