"""Stage 1b — repair truncated generations.

A minority of rows from three reasoning-heavy models exhausted the 1200-token
budget on chain-of-thought and returned a reasoning trace instead of an answer
(finish_reason=length, or content empty so the text fell back to reasoning).

These rows must not enter the belief space, but they must not simply be dropped
either. Truncation is not random: the responses that reasoned longest are
plausibly the more unusual beliefs, so discarding them would shrink each
model's apparent diversity and bias the result *toward* the study's own thesis.
The honest fix is to re-draw those specific cells with a larger budget and
record that the cap was raised, keeping the sample complete and auditable.

Re-drawn rows are tagged `repaired: true` with the cap used, so any analysis
can exclude them and check that the headline is unchanged.

Usage:
    python repair_truncated.py --max-tokens 4000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
import generate as G  # noqa: E402


def needs_repair(r: dict) -> bool:
    return bool(r.get("ok")) and (
        r.get("finish_reason") == "length" or r.get("used_reasoning_fallback")
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--concurrency", type=int, default=12)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(C.GENERATIONS)]
    bad = [r for r in rows if needs_repair(r)]
    if not bad:
        print("nothing to repair")
        return

    by_model = {}
    for r in bad:
        by_model[r["model"]] = by_model.get(r["model"], 0) + 1
    print(f"repairing {len(bad)} truncated rows at max_tokens={args.max_tokens}")
    for m, n in sorted(by_model.items()):
        print(f"  {m:<32} {n}")

    key = G.api_key()
    session = requests.Session()
    orig_cap = C.MAX_TOKENS
    C.MAX_TOKENS = args.max_tokens  # generate.one_call reads the module value

    repaired = {}
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = {
                pool.submit(G.one_call, session, key, r["model"], r["condition"],
                            r["prompt"], r["temperature"], r["sample_idx"]):
                (r["model"], r["condition"], r["sample_idx"])
                for r in bad
            }
            for n, fut in enumerate(as_completed(futs), 1):
                row = fut.result()
                row["repaired"] = True
                row["repaired_max_tokens"] = args.max_tokens
                repaired[(row["model"], row["condition"], row["sample_idx"])] = row
                if n % 20 == 0 or n == len(bad):
                    print(f"  {n}/{len(bad)}", flush=True)
    finally:
        C.MAX_TOKENS = orig_cap

    # Rewrite in place, substituting repaired rows and keeping file order so
    # the dataset stays a stable, diffable artifact.
    n_sub = n_still = 0
    with open(C.GENERATIONS, "w") as f:
        for r in rows:
            k = (r["model"], r["condition"], r["sample_idx"])
            if needs_repair(r) and k in repaired and repaired[k].get("ok"):
                new = repaired[k]
                if needs_repair(new):
                    n_still += 1
                f.write(json.dumps(new) + "\n")
                n_sub += 1
            else:
                f.write(json.dumps(r) + "\n")

    cost = sum(v.get("cost_usd") or 0 for v in repaired.values())
    print(f"\nsubstituted {n_sub} rows | still truncated after repair: {n_still} "
          f"| repair spend ${cost:.4f}")


if __name__ == "__main__":
    main()
