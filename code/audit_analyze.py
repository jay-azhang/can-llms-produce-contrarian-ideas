"""Stage 5b — aggregate the contrarian audit.

Turns three judges' per-claim scores into the answer to one question: when a
model says "very few people agree with me about this", is that true?

The headline is the **self-refutation rate** — the share of claims where the
model population itself estimates that a majority of domain experts already
agree. No human survey is needed to call that a contradiction; the models are
being scored against their own collective judgement.

Claims are graded into four tiers by median expert agreement and canonicity:

  consensus            experts broadly agree (>= 70%) — not contrarian at all
  establishment-lean   50-69% — the respectable side of a live debate
  retrieved-heterodox  < 50% but a nameable famous position — contrarian in
                       content, but recalled rather than held
  genuine-heterodox    < 50% and not attributable to a famous source

Median across judges, not mean, so one lab's outlier cannot move a claim's tier.
Inter-judge agreement is reported so the reader can see how much the tiers
depend on which judge is asked.

Usage:
    python audit_analyze.py
"""

from __future__ import annotations

import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from contrarian_audit import AUDIT_JUDGES, CATEGORIES  # noqa: E402

COST_RANK = {"none": 0, "mild": 1, "high": 2}


def tier(expert_med: float, canonical: bool) -> str:
    if expert_med >= 70:
        return "consensus"
    if expert_med >= 50:
        return "establishment_lean"
    return "retrieved_heterodox" if canonical else "genuine_heterodox"


def main() -> None:
    raw = [json.loads(l) for l in open(C.DATA / "audit.jsonl")]
    raw = [r for r in raw if r.get("expert_agreement") is not None]

    # A retried judge appears twice; keep the last successful verdict per
    # (claim, judge) so repairs replace failures instead of double-counting.
    dedup = {}
    for r in raw:
        dedup[(r["id"], r["judge"])] = r
    by_claim = defaultdict(list)
    for r in dedup.values():
        by_claim[r["id"]].append(r)
    # Only claims scored by every judge, so no claim is graded on a thinner
    # panel than another.
    complete = {k: v for k, v in by_claim.items() if len(v) >= len(AUDIT_JUDGES)}
    print(f"{len(raw)} scores | {len(by_claim)} claims | "
          f"{len(complete)} scored by all {len(AUDIT_JUDGES)} judges")

    # Temperature arms are excluded from every published figure; see
    # config.EXCLUDED_CONDITIONS for why.
    complete = {k: v for k, v in complete.items()
                if C.published_condition(v[0]["condition"]) is not None}
    print(f"{len(complete)} after dropping {sorted(C.EXCLUDED_CONDITIONS)}")

    claims = []
    for cid, rs in complete.items():
        exp = [r["expert_agreement"] for r in rs]
        pub = [r["public_agreement"] for r in rs]
        canon_votes = sum(bool(r["canonical"]) for r in rs)
        cats = Counter(r["category"] for r in rs)
        costs = [COST_RANK.get(r["social_cost"], 0) for r in rs]
        srcs = [r["canonical_source"] for r in rs if r.get("canonical_source")]
        em = float(st.median(exp))
        # Canonical on a majority vote of the panel, not any single judge.
        canon = canon_votes >= 2
        claims.append({
            "id": cid,
            "model": rs[0]["model"],
            "condition": C.published_condition(rs[0]["condition"]),
            "claim": rs[0]["claim"],
            "expert_med": round(em, 1),
            "expert_spread": int(max(exp) - min(exp)),
            "public_med": round(float(st.median(pub)), 1),
            "gap_public_expert": round(em - float(st.median(pub)), 1),
            "canonical": canon,
            "canonical_votes": canon_votes,
            "canonical_source": Counter(srcs).most_common(1)[0][0] if srcs else "",
            "social_cost": int(round(float(st.median(costs)))),
            "falsifiable_votes": sum(bool(r["falsifiable"]) for r in rs),
            "category": cats.most_common(1)[0][0],
            "category_agreement": cats.most_common(1)[0][1] / len(rs),
            "tier": tier(em, canon),
        })

    n = len(claims)
    tiers = Counter(c["tier"] for c in claims)
    cats = Counter(c["category"] for c in claims)

    def pct(x):
        return round(100 * x / n, 1)

    # --- inter-judge reliability -------------------------------------------
    judge_vecs, ids = {}, sorted(complete)
    for j in AUDIT_JUDGES:
        judge_vecs[j] = [next((r["expert_agreement"] for r in complete[i]
                               if r["judge"] == j), None) for i in ids]
    pairs = {}
    for a in range(len(AUDIT_JUDGES)):
        for b in range(a + 1, len(AUDIT_JUDGES)):
            ja, jb = AUDIT_JUDGES[a], AUDIT_JUDGES[b]
            xs = [(x, y) for x, y in zip(judge_vecs[ja], judge_vecs[jb])
                  if x is not None and y is not None]
            if len(xs) > 5:
                x, y = np.array([p[0] for p in xs]), np.array([p[1] for p in xs])
                pairs[f"{ja.split('/')[-1]} vs {jb.split('/')[-1]}"] = {
                    "pearson_r": round(float(np.corrcoef(x, y)[0, 1]), 3),
                    "mean_abs_diff": round(float(np.abs(x - y).mean()), 1),
                }

    # --- per-model and per-condition ---------------------------------------
    def breakdown(keyfn):
        out = {}
        keys = {keyfn(c) for c in claims}
        order = {k: i for i, k in enumerate(C.PROMPT_ORDER)}
        for k in sorted(keys, key=lambda x: (order.get(x, 99), x)):
            sub = [c for c in claims if keyfn(c) == k]
            t = Counter(c["tier"] for c in sub)
            out[k] = {
                "n": len(sub),
                "expert_agreement_median": round(float(st.median(
                    [c["expert_med"] for c in sub])), 1),
                "self_refutation_rate": round(
                    sum(c["expert_med"] >= 50 for c in sub) / len(sub), 4),
                "canonical_rate": round(sum(c["canonical"] for c in sub) / len(sub), 4),
                "genuine_heterodox_rate": round(t["genuine_heterodox"] / len(sub), 4),
                "high_cost_rate": round(sum(c["social_cost"] >= 2 for c in sub) / len(sub), 4),
                "tiers": {k2: t.get(k2, 0) for k2 in
                          ("consensus", "establishment_lean",
                           "retrieved_heterodox", "genuine_heterodox")},
                "categories": dict(Counter(c["category"] for c in sub).most_common()),
            }
        return out

    # --- most-cited sources -------------------------------------------------
    # Judges spell the same attribution several ways ("Nisbett & Wilson (1977)",
    # "Richard Nisbett and Timothy Wilson, 'Telling More Than We Can Know'",
    # "Nisbett & Wilson / Jonathan Haidt"). Counting raw strings splits one
    # source across several rows and understates how concentrated the corpus's
    # reading list is. Attributions are grouped greedily: two spellings merge
    # when they share a distinctive surname-length token.
    import re as _re
    COMMON = {"the", "and", "of", "in", "on", "et", "al", "jr", "dr", "prof",
              "richard", "timothy", "jonathan", "michael", "john", "paul",
              "david", "james", "robert", "william", "george", "thomas",
              "daniel", "peter", "gary", "barry", "arthur", "milton", "nina",
              "galen", "cal", "author", "various", "unknown", "general"}

    def tokens(s: str) -> set:
        s = _re.sub(r"\(.*?\)|\d{4}", " ", s)
        s = _re.split(r"[/,:;]", s)[0]          # first attribution only
        return {t.lower() for t in _re.findall(r"[A-Za-z]+", s)
                if len(t) >= 5 and t.lower() not in COMMON}

    raw = Counter(c["canonical_source"] for c in claims
                  if c["canonical"] and c["canonical_source"])
    groups = []  # [{"toks": set, "spellings": Counter, "n": int}]
    for spelling, cnt in raw.most_common():      # frequent spellings seed groups
        tk = tokens(spelling)
        hit = next((g for g in groups if tk & g["toks"]), None) if tk else None
        if hit is None:
            groups.append({"toks": tk, "spellings": Counter({spelling: cnt}),
                           "n": cnt})
        else:
            hit["toks"] |= tk
            hit["spellings"][spelling] += cnt
            hit["n"] += cnt
    sources = Counter({g["spellings"].most_common(1)[0][0]: g["n"]
                       for g in groups})

    results = {
        "n_claims": n,
        "judges": AUDIT_JUDGES,
        "headline": {
            "self_refutation_rate": pct(sum(c["expert_med"] >= 50 for c in claims)),
            "expert_agreement_median": round(float(st.median(
                [c["expert_med"] for c in claims])), 1),
            "public_agreement_median": round(float(st.median(
                [c["public_med"] for c in claims])), 1),
            "canonical_rate": pct(sum(c["canonical"] for c in claims)),
            "genuine_heterodox_rate": pct(tiers["genuine_heterodox"]),
            "high_social_cost_rate": pct(sum(c["social_cost"] >= 2 for c in claims)),
            "unfalsifiable_rate": pct(sum(c["falsifiable_votes"] <= 1 for c in claims)),
        },
        "tiers": {k: {"n": v, "pct": pct(v)} for k, v in tiers.most_common()},
        "categories": {k: {"n": v, "pct": pct(v), "desc": CATEGORIES.get(k, "")}
                       for k, v in cats.most_common()},
        "inter_judge": pairs,
        "by_model": breakdown(lambda c: c["model"]),
        "by_condition": breakdown(lambda c: c["condition"]),
        "top_sources": [{"source": s, "n": k} for s, k in sources.most_common(20)],
        "claims": sorted(claims, key=lambda c: c["expert_med"]),
    }

    (C.DATA / "audit_results.json").write_text(json.dumps(results, indent=2))

    print(f"\n{'='*74}\nHEADLINE\n{'='*74}")
    for k, v in results["headline"].items():
        print(f"  {k:<28} {v}")
    print(f"\n{'='*74}\nTIERS\n{'='*74}")
    for k, v in results["tiers"].items():
        print(f"  {k:<22} {v['n']:>5}  {v['pct']:>5}%")
    print(f"\n{'='*74}\nCATEGORIES\n{'='*74}")
    for k, v in results["categories"].items():
        print(f"  {k:<24} {v['n']:>5}  {v['pct']:>5}%")
    print(f"\n{'='*74}\nINTER-JUDGE (expert_agreement)\n{'='*74}")
    for k, v in pairs.items():
        print(f"  {k:<48} r={v['pearson_r']:<7} mad={v['mean_abs_diff']}")
    print(f"\n-> {C.DATA / 'audit_results.json'}")


if __name__ == "__main__":
    main()
