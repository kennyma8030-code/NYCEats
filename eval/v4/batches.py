"""Cut a round's packets into blind labeling batches. No database, no model.

    python eval/v4/batches.py                      # both passes, round 1
    python eval/v4/batches.py --pass same_input
    python eval/v4/batches.py --dir eval/v4/round2

Two passes, labeled separately and never shown to the same labeler at once:

  same_input     the packet is exactly the model's input
  full_context   the packet is the full thread around the same unit

Batches hold about 20 single comments, or exactly one thread chunk, in
hashed (shuffled) order. A self-consistency subset of about 10% of items is
added a second time under a different packet id, always in a different batch
from its original, so Claude's agreement with itself can be measured.

Writes, per pass:
  batches/<pass>/bNNN.txt        what a labeler reads: instructions, then each
                                 packet between delimiter lines, verbatim
  batches/<pass>/packets.jsonl   the same packets as JSON, for API-driven labeling
  keys/<pass>.json               packet id -> item, copy, batch. NOT for labelers.
  keys/<pass>.meta.json          the renderer the pass's packets were drawn with and
                                 a fingerprint of the key's bracket numbers

Nothing in batches/ names an item, a stratum, a weight or production output.
Production's output is not even exported until both passes are labeled
(export_production.py), and it never enters the repo.
Labels go to labels/<pass>/bNNN.jsonl; see labels.py for the format.
"""

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from design import h  # noqa: E402  (one md5 ordering for every v4 draw)
import labels as L  # noqa: E402  (the key fingerprint labels.py checks)
SEED = "nyceats-eval-v4-batches"
BATCH_SIZE = 20
DUP_SHARE = 0.10
PASSES = ("same_input", "full_context")

HEADER = {
    "same_input": """\
NYCEats extraction labeling -- batch {batch} -- pass: same_input -- {n} packet(s)

Apply the extraction prompt you were given to each packet below. Each packet is
exactly the input the extraction model receives, so judge it from what is
shown. Packets are independent: never carry anything from one packet to another.

Write one JSON line per packet to labels/same_input/{batch}.jsonl:
  {{"packet_id": "<id>", "output": {{"mentions": [ ... ]}}}}
"output" is the JSON object the prompt asks for. A comment packet's mentions
carry no "id". A thread packet's mentions each carry "id", the bracket number
of the comment they come from. Use {{"mentions": []}} when nothing qualifies.
""",
    "full_context": """\
NYCEats extraction labeling -- batch {batch} -- pass: full_context -- {n} packet(s)

Apply the extraction prompt you were given, but read the whole conversation
shown before deciding what each comment means. Label ONLY the comment marked
">>> COMMENT TO LABEL", or in a thread packet ONLY the comments with a bracket
number [n]; everything else is context. Packets are independent.

Write one JSON line per packet to labels/full_context/{batch}.jsonl:
  {{"packet_id": "<id>", "output": {{"mentions": [ ... ]}}}}
"output" is the JSON object the prompt asks for. A comment packet's mentions
carry no "id". A thread packet's mentions each carry "id", the bracket number
of the comment they come from. Use {{"mentions": []}} when nothing qualifies.
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


def renderer_of(packets, pass_name):
    """The one renderer every packet of the pass was drawn with. Packets
    written before packets.py recorded it were production's."""
    if pass_name == "full_context":
        return "full_context"
    found = {p.get("same_input_renderer", "production") for p in packets}
    if len(found) != 1:
        raise SystemExit(f"packets mix same_input renderers {sorted(found)}; rebuild them with packets.py")
    return found.pop()


def render_batch(batch_id, units, pass_name):
    out = [HEADER[pass_name].format(batch=batch_id, n=len(units))]
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
                    f.write(render_batch(batch_id, units, pass_name))
                for pid, p, copy in units:
                    pj.write(json.dumps({"packet_id": pid, "batch": batch_id, "mode": p["mode"],
                                         "input": p[pass_name]}, ensure_ascii=False) + "\n")
                    # A pass may number a chunk its own way (v6's same_input
                    # renderer does), so the key keeps that pass's numbers.
                    sids = p.get(pass_name + "_short_ids", p.get("short_ids"))
                    key[pid] = {"item_id": p["item_id"], "mode": p["mode"], "copy": copy, "batch": batch_id,
                                **({"short_ids": sids} if p["mode"] == "thread" else {})}
        with open(os.path.join(args.dir, "keys", pass_name + ".json"), "w", encoding="utf-8") as f:
            json.dump(key, f, indent=1)
        # The key's meta file says how the pass's packets were drawn, so
        # labels.py can refuse labels made against another rendering (v6
        # renumbers thread chunks; production's renderer does not).
        with open(os.path.join(args.dir, "keys", pass_name + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump({"renderer": renderer_of(packets, pass_name),
                       "short_ids_sha256": L.key_fingerprint(key)}, f, indent=1)
        n_dup = sum(1 for v in key.values() if v["copy"])
        print(f"{pass_name}: {len(batches)} batches, {len(key)} packets ({n_dup} duplicates) -> {bdir}")


if __name__ == "__main__":
    main()
