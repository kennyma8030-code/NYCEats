"""Cut a round's packets into blind labeling batches. No database, no model.

    python eval/v4/batches.py                      # both passes, round 1
    python eval/v4/batches.py --pass same_input
    python eval/v4/batches.py --dir eval/v4/round2

Two passes, labeled separately and never shown to the same labeler at once:

  same_input     the packet is exactly the model's input
  full_context   the packet is the full thread around the same unit

Batches hold up to 12 single comments, or exactly one thread chunk, in
hashed (shuffled) order: few enough that one labeling agent can give every
packet a careful read, the metadata and a rationale in one sitting. A
self-consistency subset of about 10% of items is added a second time under a
different packet id, always in a different batch from its original, so
Claude's agreement with itself can be measured.

Every batch holds one mode only, and carries the v5 extraction prompt of that
mode verbatim (eval/prompts/v5_comment.py or v5_thread.py), so a labeler
needs only eval/v4/LABELING.md and its batch file. The prompt each pass was
cut with is recorded in keys/<pass>.prompt.json, and labels.py export stamps
its hash on the exported run.

Writes, per pass:
  batches/<pass>/bNNN.txt        what a labeler reads: instructions, the
                                 prompt, then each packet between delimiter
                                 lines, verbatim
  batches/<pass>/packets.jsonl   the same packets as JSON, for API-driven labeling
  keys/<pass>.json               packet id -> item, copy, batch. NOT for labelers.
  keys/<pass>.prompt.json        mode -> the v5 prompt hash the batches carry

Nothing in batches/ names an item, a stratum, a weight, a prompt hash or
production output. Production's output is not even exported until both
passes are labeled (export_production.py), and it never enters the repo.
Labels go to labels/<pass>/bNNN.jsonl; see labels.py and LABELING.md.
"""

import argparse
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from design import h  # noqa: E402  (one md5 ordering for every v4 draw)
SEED = "nyceats-eval-v4-batches"
BATCH_SIZE = 12
DUP_SHARE = 0.10
PASSES = ("same_input", "full_context")
PROMPT_FILES = {"comment": os.path.join(EVAL, "prompts", "v5_comment.py"),
                "thread": os.path.join(EVAL, "prompts", "v5_thread.py")}


def load_prompts():
    """mode -> (SYSTEM_PROMPT, PROMPT_HASH) of the v5 prompts."""
    out = {}
    for mode, path in PROMPT_FILES.items():
        spec = importlib.util.spec_from_file_location(f"v5_{mode}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out[mode] = (mod.SYSTEM_PROMPT, mod.PROMPT_HASH)
    return out


COMMON = """\
How to label is in LABELING.md; read it first. In short: label every packet
exactly as the EXTRACTION PROMPT below asks, then add the label metadata
(canonical_name and rationale always; the optional fields when they apply).
Packets are independent: never carry anything from one packet to another, and
never look at other batches, other passes, model runs or results.

Write one JSON line per packet, in any order, to labels/{pass_name}/{batch}.jsonl:
  {{"packet_id": "<id>", "output": {{"mentions": [ ... ]}}}}
Use {{"mentions": []}} when nothing qualifies. {id_rule}
Check the file before you finish:
  python eval/v4/labels.py check --pass {pass_name} --batch {batch}
"""

ID_RULE = {"comment": "A comment packet's mentions carry no \"id\".",
           "thread": "Every mention starts with \"id\", the bracket number of the comment it comes from."}

HEADER = {
    "same_input": """\
NYCEats extraction labeling -- batch {batch} -- pass: same_input -- {mode} mode -- {n} packet(s)

Each packet is exactly the input the extraction model receives. Judge it from
what is shown and nothing else.
""",
    "full_context": """\
NYCEats extraction labeling -- batch {batch} -- pass: full_context -- {mode} mode -- {n} packet(s)

Each packet shows the whole conversation around the unit the model sees. Read
all of it before deciding what a comment means, but label ONLY the comment
marked ">>> COMMENT TO LABEL", or in a thread packet ONLY the comments with a
bracket number [n]; everything else is context. The layout differs from the
model's input; the prompt's rules apply all the same. Set needs_context true
on a mention that the model's own input could not support.
""",
}


def duplicates(packets):
    """About 10% of items, per mode, chosen by hash. The same items are
    duplicated in both passes so the two consistency rates are comparable."""
    out = set()
    for mode in ("comment", "thread"):
        ids = sorted((p["item_id"] for p in packets if p["mode"] == mode), key=lambda i: h(SEED, "dup", i))
        out.update(ids[:math.ceil(len(ids) * DUP_SHARE)])
    return out


def cut(packets, pass_name):
    """[(batch_id, [(packet_id, packet, copy)])] in shuffled order."""
    dups = duplicates(packets)
    units = []
    for p in packets:
        for copy in ((0, 1) if p["item_id"] in dups else (0,)):
            units.append((h(SEED, pass_name, "pid", p["item_id"], copy)[:8], p, copy))
    units.sort(key=lambda u: h(SEED, pass_name, "order", u[0]))
    singles = [u for u in units if u[1]["mode"] == "comment"]
    threads = [[u] for u in units if u[1]["mode"] == "thread"]
    # Fill batches in shuffled order. A packet whose twin is already in the
    # current batch waits for the next one, so the two copies never meet.
    groups, cur, waiting = [], [], []
    def has_twin(batch, u):
        return any(x[1]["item_id"] == u[1]["item_id"] for x in batch)
    for u in singles:
        queue, waiting = waiting + [u], []
        for x in queue:
            (waiting if has_twin(cur, x) else cur).append(x)
            if len(cur) == BATCH_SIZE:
                groups.append(cur)
                cur = []
    if cur:
        groups.append(cur)
    # Packets still waiting at the end go into a batch of their own. Their
    # twins are all in earlier batches, and no two of them share an item.
    if waiting:
        groups.append(waiting)
    allg = groups + threads
    allg.sort(key=lambda g: h(SEED, pass_name, "batch", g[0][0]))
    return [(f"b{n:03d}", g) for n, g in enumerate(allg, start=1)]


def render_batch(batch_id, units, pass_name, prompts):
    modes = {p["mode"] for _, p, _ in units}
    assert len(modes) == 1, f"batch {batch_id} mixes modes {modes}"
    mode = modes.pop()
    out = [HEADER[pass_name].format(batch=batch_id, n=len(units), mode=mode),
           COMMON.format(pass_name=pass_name, batch=batch_id, id_rule=ID_RULE[mode]),
           f"=== EXTRACTION PROMPT ({mode} mode) ===",
           prompts[mode][0],
           "=== END EXTRACTION PROMPT ===",
           ""]
    for pid, p, _ in units:
        kind = "comment packet" if p["mode"] == "comment" else "thread packet"
        out.append(f"=== PACKET {pid} ({kind}) ===")
        out.append(p[pass_name])
        out.append(f"=== END PACKET {pid} ===")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--pass", dest="passes", choices=PASSES, action="append")
    args = ap.parse_args()
    with open(os.path.join(args.dir, "packets.jsonl"), encoding="utf-8") as f:
        packets = [json.loads(l) for l in f]
    prompts = load_prompts()
    for pass_name in args.passes or PASSES:
        bdir = os.path.join(args.dir, "batches", pass_name)
        os.makedirs(bdir, exist_ok=True)
        for old in os.listdir(bdir):
            if old.endswith(".txt") or old == "packets.jsonl":
                os.remove(os.path.join(bdir, old))
        os.makedirs(os.path.join(args.dir, "keys"), exist_ok=True)
        os.makedirs(os.path.join(args.dir, "labels", pass_name), exist_ok=True)
        batches = cut(packets, pass_name)
        key = {}
        with open(os.path.join(bdir, "packets.jsonl"), "w", encoding="utf-8") as pj:
            for batch_id, units in batches:
                with open(os.path.join(bdir, batch_id + ".txt"), "w", encoding="utf-8") as f:
                    f.write(render_batch(batch_id, units, pass_name, prompts))
                for pid, p, copy in units:
                    pj.write(json.dumps({"packet_id": pid, "batch": batch_id, "mode": p["mode"],
                                         "input": p[pass_name]}, ensure_ascii=False) + "\n")
                    key[pid] = {"item_id": p["item_id"], "mode": p["mode"], "copy": copy, "batch": batch_id,
                                **({"short_ids": p["short_ids"]} if p["mode"] == "thread" else {})}
        with open(os.path.join(args.dir, "keys", pass_name + ".json"), "w", encoding="utf-8") as f:
            json.dump(key, f, indent=1)
        with open(os.path.join(args.dir, "keys", pass_name + ".prompt.json"), "w", encoding="utf-8") as f:
            json.dump({mode: ph for mode, (_, ph) in prompts.items()}, f, indent=1)
        n_dup = sum(1 for v in key.values() if v["copy"])
        by_mode = {m: sum(1 for _, u in batches if u[0][1]["mode"] == m) for m in ("comment", "thread")}
        print(f"{pass_name}: {len(batches)} batches ({by_mode['comment']} comment, {by_mode['thread']} thread), "
              f"{len(key)} packets ({n_dup} duplicates) -> {bdir}")


if __name__ == "__main__":
    main()
