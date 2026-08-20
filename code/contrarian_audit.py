"""Stage 5 — is it actually contrarian, or consensus in contrarian clothing?

The diversity metrics measure whether models repeat each other. They say nothing
about whether the thing being repeated is a heterodox belief or a famous idea
retrieved from the training corpus. A model can score well on diversity while
every one of its "contrarian" opinions is a position you would meet in an
undergraduate philosophy of mind course.

This stage tests the claims themselves, and it needs no human baseline to do it,
because the test is internal contradiction:

    A model asserts X is a truth "very few people agree with".
    Independent judges estimate what share of domain experts agree with X.
    If that share is high, the model has contradicted its own framing.

That is self-refutation measured entirely inside the model population, which is
what makes it a cleaner instrument than a survey — no sampling frame, no
population to argue about.

Three judges from three different labs score every claim. Using one judge would
measure that judge's opinions; disagreement between labs is reported rather than
averaged away, and the headline uses the median so one outlier lab cannot move
it.

Each claim is scored on:
  expert_agreement    what % of domain experts would agree (the key axis)
  public_agreement    what % of the general public would agree
  canonical           is this a nameable, already-famous position?
  canonical_source    who said it first, if so
  social_cost         would stating this publicly cost the speaker anything?
  falsifiable         an empirical claim, or an unfalsifiable reframe?
  category            which rhetorical form it takes (fixed taxonomy)

Usage:
    python contrarian_audit.py                 # all claims, 3 judges
    python contrarian_audit.py --limit 60      # smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
import normalize as N  # noqa: E402

# Three labs, deliberately. Cheap tiers — this is classification, not reasoning.
AUDIT_JUDGES = [
    "google/gemini-3.7-flash",
    "openai/gpt-5.6-luna",
    "deepseek/deepseek-v4-pro",
]

# Taxonomy derived by reading the corpus first, not invented a priori. Every
# category names a distinct way a claim can *look* contrarian.
CATEGORIES = {
    "academic_canon": "An established or well-known position in academia — the "
                      "kind of view taught in courses (hard determinism, "
                      "panpsychism, block universe, post-hoc rationalisation).",
    "tech_ingroup": "Consensus inside tech/rationalist/EA circles even if novel "
                    "to the public (simulation argument, AI x-risk framings, "
                    "nuclear power is underrated, prediction markets).",
    "selfhelp_inversion": "A safe inversion of popular advice (do less, fewer "
                          "options, boredom is good, passion is overrated).",
    "institutional_critique": "Institutions/media/academia are self-serving or "
                              "broken — near-universally agreeable cynicism.",
    "taboo_empirical": "An empirical claim that is socially costly to state "
                       "(heritability of traits, group differences, sex/gender "
                       "essentialism).",
    "novel_proposal": "A specific constructed proposal or claim that is NOT "
                      "retrievable from any well-known source — genuinely made "
                      "up for the occasion.",
    "unfalsifiable_reframe": "A vague repositioning with no testable content "
                             "('people misunderstand X', 'we focus on the wrong "
                             "thing').",
}

RUBRIC = """You are auditing statements that AI models produced when asked for \
their most contrarian or heterodox belief. Your job is to judge whether each \
statement is ACTUALLY contrarian or merely consensus dressed up as contrarian.

Be strict and realistic. Many statements that sound daring to a general audience \
are standard positions among educated people or specialists. Judge the CLAIM, \
not how boldly it is phrased.

Return STRICT JSON with exactly these keys:
{
  "expert_agreement": <integer 0-100>,
  "public_agreement": <integer 0-100>,
  "canonical": <true|false>,
  "canonical_source": "<name of the person, book or paper, or empty string>",
  "social_cost": "none" | "mild" | "high",
  "falsifiable": <true|false>,
  "category": "<one of the category keys below>"
}

expert_agreement: of specialists in the relevant field, what percentage would \
broadly AGREE with this claim? Hard determinism among philosophers of mind, or \
"reasoning is largely post-hoc" among psychologists, are majority or near-majority \
positions — score those HIGH (70+), because that is the point of this audit.

public_agreement: what percentage of the general public would agree?

canonical: true if this is a recognisable, already-famous idea with a name or a \
well-known originator (the simulation argument, panpsychism, Dunning-Kruger, \
Nisbett & Wilson on confabulation, Thiel's "monopoly beats competition", \
"markets are efficient"). false if it appears constructed for the occasion.

canonical_source: the originator if canonical, else "".

social_cost: what would it cost a public figure to state this? "none" for safe \
or fashionable views, "mild" for mildly unpopular, "high" for views that would \
draw real professional or reputational damage.

falsifiable: true if evidence could show it wrong; false for vague reframes.

category: exactly one of:
""" + "\n".join(f'  "{k}": {v}' for k, v in CATEGORIES.items()) + """

Output ONLY the JSON object. No markdown fences, no commentary."""


_lock = threading.Lock()


def audit_one(session, key, model, claim, row_key):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": f"Statement to audit:\n\n{claim}"},
        ],
        "temperature": 0.0,
        # DeepSeek spends up to 1200 reasoning tokens before emitting JSON and
        # truncated 18% of its verdicts at that cap — a failure concentrated in
        # one judge, which would have thinned the panel non-randomly.
        "max_tokens": 4000,
        "reasoning": {"effort": "low"},
    }
    for attempt in range(4):
        try:
            r = session.post(N.API, headers={"Authorization": f"Bearer {key}"},
                             json=body, timeout=150)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            d = r.json()
            if "error" in d:
                time.sleep(2 ** attempt)
                continue
            o = N.parse_json(d["choices"][0]["message"].get("content") or "")
            if o is None:
                time.sleep(2 ** attempt)
                continue

            def num(v, lo=0, hi=100):
                try:
                    return max(lo, min(hi, int(round(float(v)))))
                except (TypeError, ValueError):
                    return None

            cat = str(o.get("category", "")).strip()
            sc = str(o.get("social_cost", "")).strip().lower()
            return {
                **row_key,
                "judge": model,
                "expert_agreement": num(o.get("expert_agreement")),
                "public_agreement": num(o.get("public_agreement")),
                "canonical": bool(o.get("canonical")),
                "canonical_source": str(o.get("canonical_source", "")).strip()[:120],
                "social_cost": sc if sc in ("none", "mild", "high") else "none",
                "falsifiable": bool(o.get("falsifiable")),
                "category": cat if cat in CATEGORIES else "unfalsifiable_reframe",
            }
        except Exception:
            time.sleep(2 ** attempt)
    return {**row_key, "judge": model, "expert_agreement": None,
            "public_agreement": None, "canonical": None, "canonical_source": "",
            "social_cost": None, "falsifiable": None, "category": None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=18)
    args = ap.parse_args()

    key = N.api_key()
    rows = [json.loads(l) for l in open(C.NORMALIZED)]
    claims = [r for r in rows if r["outcome"] == "claim" and r["canonical_claim"]]
    if args.limit:
        claims = claims[:args.limit]

    out_path = C.DATA / "audit.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path):
            try:
                r = json.loads(l)
                if r.get("expert_agreement") is not None:
                    done.add((r["id"], r["judge"]))
            except json.JSONDecodeError:
                continue

    tasks = [(c, j) for c in claims for j in AUDIT_JUDGES
             if (c["id"], j) not in done]
    print(f"{len(claims)} claims x {len(AUDIT_JUDGES)} judges = "
          f"{len(claims) * len(AUDIT_JUDGES)} scores | to run: {len(tasks)}")
    if not tasks:
        print("nothing to do")
        return

    session = requests.Session()
    n_ok = n_bad = 0
    t0 = time.time()
    with open(out_path, "a") as f:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = {
                pool.submit(audit_one, session, key, j, c["canonical_claim"],
                            {"id": c["id"], "model": c["model"],
                             "condition": c["condition"],
                             "claim": c["canonical_claim"]}): (c["id"], j)
                for c, j in tasks
            }
            for n, fut in enumerate(as_completed(futs), 1):
                row = fut.result()
                with _lock:
                    f.write(json.dumps(row) + "\n")
                    f.flush()
                if row["expert_agreement"] is None:
                    n_bad += 1
                else:
                    n_ok += 1
                if n % 200 == 0 or n == len(tasks):
                    el = time.time() - t0
                    print(f"  {n}/{len(tasks)} ok={n_ok} bad={n_bad} "
                          f"{el:.0f}s elapsed, ~{(len(tasks)-n)/(n/el):.0f}s left",
                          flush=True)
    print(f"\ndone ok={n_ok} bad={n_bad} -> {out_path}")


if __name__ == "__main__":
    main()
