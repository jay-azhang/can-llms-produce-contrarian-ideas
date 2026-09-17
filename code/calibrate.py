"""Stage 3b — calibrate the "same opinion" threshold.

Clustering needs a decision boundary: at what cosine similarity do two
canonical claims count as the same opinion? Picking `min_cluster_size` or an
eyeballed cutoff makes the headline number a function of an arbitrary
hyperparameter, which is precisely the kind of researcher degree of freedom
this study is supposed to foreclose.

So the boundary is measured instead of chosen. The design already calls for
"LLM-judge pairwise 'same claim?' adjudication on a sample"; this uses that
adjudication as ground truth and fits the threshold to it:

  1. sample claim pairs stratified across the whole cosine range, so the judge
     sees easy and hard cases in similar numbers rather than the overwhelming
     majority of unrelated pairs a uniform sample would produce
  2. ask a judge, blind to the cosine value, whether the two express the same
     underlying belief
  3. sweep the threshold and take the one maximising Youden's J
  4. report the separation achieved, so a weak boundary is visible rather than
     hidden inside a cluster count

The fitted threshold is written to data/calibration.json and consumed by
analyze.py. Both embedding spaces get their own threshold: cosine values are
not comparable across embedding models, and forcing one number on both would
silently mis-cluster one of the two spaces.

Usage:
    python calibrate.py --pairs 300
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
import normalize as N  # noqa: E402

PAIR_RUBRIC = """You are adjudicating whether two statements express the SAME \
underlying belief, for a study of opinion diversity.

Answer YES if a reasonable reader would say these are the same opinion, even \
if worded very differently or differing in emphasis, scope or hedging.
Answer NO if they are different opinions, even if they are about the same \
topic or share vocabulary.

Two statements about the same SUBJECT are not automatically the same OPINION. \
"Nuclear power is underrated" and "Nuclear power is dangerous" share a topic \
but are different beliefs.

Return STRICT JSON only: {"same": true} or {"same": false}"""


def judge_pair(session, key, model, a, b):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": PAIR_RUBRIC},
            {"role": "user", "content": f"Statement A: {a}\n\nStatement B: {b}"},
        ],
        "temperature": 0.0,
        "max_tokens": 400,
        "reasoning": {"effort": "low"},
    }
    for attempt in range(4):
        try:
            r = session.post(N.API, headers={"Authorization": f"Bearer {key}"},
                             json=body, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                continue
            d = r.json()
            if "error" in d:
                continue
            out = N.parse_json(d["choices"][0]["message"].get("content") or "")
            if out is not None and "same" in out:
                return bool(out["same"])
        except Exception:
            pass
    return None


def sweep_threshold(sims: np.ndarray, labels: np.ndarray):
    """Threshold maximising Youden's J = sensitivity + specificity - 1."""
    best = None
    for t in np.arange(0.30, 0.96, 0.01):
        pred = sims >= t
        tp = int((pred & labels).sum())
        fp = int((pred & ~labels).sum())
        fn = int((~pred & labels).sum())
        tn = int((~pred & ~labels).sum())
        sens = tp / max(tp + fn, 1)
        spec = tn / max(tn + fp, 1)
        j = sens + spec - 1
        prec = tp / max(tp + fp, 1)
        f1 = 2 * prec * sens / max(prec + sens, 1e-9)
        if best is None or j > best["youden_j"]:
            best = {"threshold": round(float(t), 3), "youden_j": round(j, 4),
                    "sensitivity": round(sens, 4), "specificity": round(spec, 4),
                    "precision": round(prec, 4), "f1": round(f1, 4),
                    "tp": tp, "fp": fp, "fn": fn, "tn": tn}
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=16)
    args = ap.parse_args()

    key = N.api_key()
    index = [json.loads(l) for l in open(C.DATA / "embed_index.jsonl")]
    rng = np.random.default_rng(20260817)

    # Pairs are selected on the closed space and then scored in both, so the
    # judge adjudicates one fixed set of pairs and the two thresholds are
    # fitted to identical ground truth.
    vec_closed = np.load(C.DATA / "emb_closed.npy")
    n = len(index)

    # Stratified sample: uniform random pairs are almost all near-zero
    # similarity, which would fit a threshold on nothing but easy negatives.
    cand = rng.integers(0, n, size=(args.pairs * 60, 2))
    cand = cand[cand[:, 0] != cand[:, 1]]
    csim = (vec_closed[cand[:, 0]] * vec_closed[cand[:, 1]]).sum(axis=1)
    bins = [(0.2, 0.4), (0.4, 0.55), (0.55, 0.65), (0.65, 0.75),
            (0.75, 0.85), (0.85, 1.01)]
    per_bin = max(args.pairs // len(bins), 1)
    picks = []
    for lo, hi in bins:
        idx = np.where((csim >= lo) & (csim < hi))[0]
        if len(idx):
            picks.extend(rng.choice(idx, size=min(per_bin, len(idx)), replace=False))
    picks = np.array(picks)
    pairs = cand[picks]
    print(f"adjudicating {len(pairs)} stratified pairs")

    session = requests.Session()
    verdicts = [None] * len(pairs)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(judge_pair, session, key, C.JUDGE_MODEL,
                            index[int(i)]["canonical_claim"],
                            index[int(j)]["canonical_claim"]): k
                for k, (i, j) in enumerate(pairs)}
        for done, fut in enumerate(as_completed(futs), 1):
            verdicts[futs[fut]] = fut.result()
            if done % 50 == 0 or done == len(pairs):
                print(f"  {done}/{len(pairs)}", flush=True)

    keep = [k for k, v in enumerate(verdicts) if v is not None]
    pairs, labels = pairs[keep], np.array([verdicts[k] for k in keep])
    print(f"usable verdicts: {len(labels)} | same={int(labels.sum())} "
          f"different={int((~labels).sum())}")

    out = {"n_pairs": int(len(labels)), "n_same": int(labels.sum()),
           "judge": C.JUDGE_MODEL, "spaces": {}}
    for tag, path in (("closed", "emb_closed.npy"), ("open", "emb_open.npy")):
        V = np.load(C.DATA / path)
        sims = (V[pairs[:, 0]] * V[pairs[:, 1]]).sum(axis=1)
        best = sweep_threshold(sims, labels)
        best["mean_sim_same"] = round(float(sims[labels].mean()), 4) if labels.any() else None
        best["mean_sim_diff"] = round(float(sims[~labels].mean()), 4) if (~labels).any() else None
        out["spaces"][tag] = best
        print(f"  {tag}: threshold={best['threshold']} J={best['youden_j']} "
              f"f1={best['f1']} sens={best['sensitivity']} spec={best['specificity']} "
              f"| mean_sim same={best['mean_sim_same']} diff={best['mean_sim_diff']}")

    (C.DATA / "calibration.json").write_text(json.dumps(out, indent=2))
    print(f"-> {C.DATA / 'calibration.json'}")


if __name__ == "__main__":
    main()
