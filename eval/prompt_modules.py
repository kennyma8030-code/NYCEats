"""Load the prompt modules in eval/prompts/ by file path, once each.

The prompt files are not a package (eval/run.py loads them as
--prompt file:...), so every tool that needs one, packets.py for the v6
renderer and labels.py for the schemas and drift hashes, loads it the same
way here rather than each keeping its own importlib copy.
"""

import importlib.util
import os

PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
_cache = {}


def path_of(name):
    return os.path.join(PROMPTS, name + ".py")


def load(name):
    """eval/prompts/<name>.py as a module, cached by name."""
    if name not in _cache:
        spec = importlib.util.spec_from_file_location(name, path_of(name))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cache[name] = mod
    return _cache[name]
