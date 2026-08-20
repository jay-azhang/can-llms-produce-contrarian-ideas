"""Stage 2 — normalization.

A judge model reduces each free-text answer to one canonical claim sentence,
so that clustering operates on beliefs rather than on prose style. This is the
answer to the "you measured phrasing similarity, not belief similarity"
objection: the clustered object is a stripped declarative sentence with the
model's voice, hedging and framing removed.

Refusals and hedges are coded as their own outcomes, never dropped. A model
that evades the question is exhibiting the phenomenon under study; deleting
those rows would quietly improve the diversity score of the most evasive
models, which is exactly backwards.

Two judges run over a validation subsample so that inter-judge agreement can be
reported. The design also calls for 200 hand-checked items; `--sheet` writes
that sheet out for a human to fill, since agreement between two LLM judges
measures reproducibility, not correctness.

Usage:
    python normalize.py                 # normalize all generations
    python normalize.py --validate 200  # second judge on 200 items, report kappa
    python normalize.py --sheet 200     # write human hand-check sheet
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

API = "https://openrouter.ai/api/v1/chat/completions"
_lock = threading.Lock()

# Fixed rubric. Kept verbatim in the repo so the extraction step is auditable
# and so a re-run months later normalizes identically.
RUBRIC = """You are coding responses for a study of AI model opinion diversity.

You will be given a model's answer to a question asking for a contrarian or \
unpopular belief. Classify it and extract its core claim.

Return STRICT JSON with exactly these keys:
{
  "outcome": "claim" | "refusal" | "hedge",
  "canonical_claim": "<one declarative sentence>",
  "topic": "<2-4 word topic label>"
}

Definitions:
- "claim": the answer commits to a substantive belief the speaker holds.
- "refusal": the answer declines to give an opinion (e.g. "as an AI I don't \
have personal beliefs"), or answers about not having beliefs.
- "hedge": the answer engages but never commits — it lists several possible \
views, discusses the question itself, or states something so uncontroversial \
that no belief is at stake.

Rules for canonical_claim:
- ONE declarative sentence, under 25 words, present tense.
- State the belief plainly. Remove hedging ("I think", "arguably"), framing \
("Here's a contrarian view:"), justification, and all rhetorical flourish.
- Preserve the SPECIFIC content. Do not generalize "nuclear power is unfairly \
maligned" into "energy policy is misunderstood".
- If outcome is "refusal", set canonical_claim to "" (empty string).
- If outcome is "hedge" and a claim is recoverable, extract it; otherwise "".

Rules for topic:
- A short noun-phrase label, e.g. "consciousness", "nuclear energy", \
"education reform", "free will".

Output ONLY the JSON object. No markdown fences, no commentary."""


def api_key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        sys.exit("OPENROUTER_API_KEY not set")
    return k


def parse_json(text: str) -> dict | None:
    """Judges occasionally wrap JSON in fences despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t[3:]
        t = t[4:] if t.lower().startswith("json") else t
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < 0:
        return None
    try:
        return json.loads(t[i:j + 1])
    except json.JSONDecodeError:
        return None


def judge_one(session, key, model, text, row_key) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": f"Answer to code:\n\n{text}"},
        ],
        "temperature": 0.0,   # deterministic extraction, not sampling
        # 500 truncated the judge's own JSON mid-object on longer claims; because
        # temperature is 0 every retry truncated identically, so the failure
        # correlated with models that give longer answers rather than being noise.
        "max_tokens": 1500,
        "reasoning": {"effort": "low"},
    }
    for attempt in range(4):
        try:
            r = session.post(API, headers={"Authorization": f"Bearer {key}"},
                             json=body, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            d = r.json()
            if "error" in d:
                time.sleep(2 ** attempt)
                continue
            out = parse_json(d["choices"][0]["message"].get("content") or "")
            if out is None:
                time.sleep(2 ** attempt)
                continue
            oc = str(out.get("outcome", "")).lower().strip()
            if oc not in ("claim", "refusal", "hedge"):
                oc = "hedge"
            return {
                **row_key,
                "outcome": oc,
                "canonical_claim": str(out.get("canonical_claim", "")).strip(),
                "topic": str(out.get("topic", "")).strip().lower(),
                "judge_model": model,
            }
        except Exception:
            time.sleep(2 ** attempt)
    return {**row_key, "outcome": "judge_error", "canonical_claim": "",
            "topic": "", "judge_model": model}


def load_generations() -> list[dict]:
    rows = []
    with open(C.GENERATIONS) as f:
        for line in f:
            r = json.loads(line)
            if r.get("ok") and (r.get("text") or "").strip():
                rows.append(r)
    return rows


def row_id(r: dict) -> str:
    return f"{r['model']}|{r['condition']}|{r['sample_idx']}"


def run_judge(rows, model, key, concurrency, out_path=None, desc=""):
    session = requests.Session()
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = {}
        for r in rows:
            rk = {"id": row_id(r), "model": r["model"],
                  "condition": r["condition"], "sample_idx": r["sample_idx"],
                  "raw_text": r["text"]}
            futs[pool.submit(judge_one, session, key, model, r["text"], rk)] = rk
        for n, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if n % 100 == 0 or n == len(rows):
                print(f"  {desc}{n}/{len(rows)}", flush=True)
    if out_path:
        with open(out_path, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
    return results


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Agreement on the outcome code, corrected for chance."""
    cats = sorted(set(a) | set(b))
    n = len(a)
    obs = sum(x == y for x, y in zip(a, b)) / n
    exp = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (obs - exp) / (1 - exp) if exp < 1 else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int, default=0,
                    help="run a second judge on N items and report agreement")
    ap.add_argument("--sheet", type=int, default=0,
                    help="write N-item hand-check sheet for a human")
    ap.add_argument("--concurrency", type=int, default=16)
    args = ap.parse_args()

    key = api_key()
    rows = load_generations()
    print(f"loaded {len(rows)} successful generations")

    if args.sheet:
        random.seed(20260817)
        norm = {json.loads(l)["id"]: json.loads(l)
                for l in open(C.NORMALIZED)} if C.NORMALIZED.exists() else {}
        sample = random.sample(rows, min(args.sheet, len(rows)))
        path = C.DATA / "handcheck_sheet.jsonl"
        with open(path, "w") as f:
            for r in sample:
                n = norm.get(row_id(r), {})
                f.write(json.dumps({
                    "id": row_id(r),
                    "model": r["model"],
                    "condition": r["condition"],
                    "raw_text": r["text"],
                    "judge_outcome": n.get("outcome"),
                    "judge_canonical_claim": n.get("canonical_claim"),
                    "HUMAN_outcome_agrees": None,
                    "HUMAN_claim_faithful": None,
                    "HUMAN_notes": "",
                }) + "\n")
        print(f"hand-check sheet -> {path} ({len(sample)} items)")
        return

    if args.validate:
        random.seed(20260817)
        sample = random.sample(rows, min(args.validate, len(rows)))
        primary = {r["id"]: r for r in
                   (json.loads(l) for l in open(C.NORMALIZED))}
        print(f"second judge ({C.JUDGE_MODEL_ALT}) on {len(sample)} items")
        second = run_judge(sample, C.JUDGE_MODEL_ALT, key, args.concurrency,
                           C.DATA / "validation_judge2.jsonl", desc="v ")
        pairs = [(primary[r["id"]], r) for r in second if r["id"] in primary]
        a = [p[0]["outcome"] for p in pairs]
        b = [p[1]["outcome"] for p in pairs]
        agree = sum(x == y for x, y in zip(a, b)) / len(a)

        # Outcome codes are near-degenerate (almost everything is a "claim"),
        # which makes kappa unstable and uninformative on its own. The axis that
        # actually matters is whether two judges extract the SAME claim from the
        # same answer, so agreement is also measured semantically: cosine
        # similarity between the two judges' canonical claims.
        both = [(p, q) for p, q in pairs
                if p.get("canonical_claim") and q.get("canonical_claim")]
        claim_sim = None
        if both:
            import numpy as np
            sess = requests.Session()
            xs = [p["canonical_claim"] for p, _ in both]
            ys = [q["canonical_claim"] for _, q in both]

            def emb(texts):
                out = []
                for i in range(0, len(texts), 64):
                    r = sess.post(
                        "https://openrouter.ai/api/v1/embeddings",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": C.EMBED_CLOSED, "input": texts[i:i + 64]},
                        timeout=180).json()
                    out += [d["embedding"] for d in
                            sorted(r["data"], key=lambda d: d["index"])]
                A = np.array(out, dtype=np.float32)
                return A / np.linalg.norm(A, axis=1, keepdims=True).clip(min=1e-9)

            A, B = emb(xs), emb(ys)
            sims = (A * B).sum(axis=1)
            claim_sim = {
                "n": len(both),
                "mean_cosine": round(float(sims.mean()), 4),
                "median_cosine": round(float(np.median(sims)), 4),
                "pct_above_0.80": round(float((sims > 0.80).mean()), 4),
                "pct_above_0.90": round(float((sims > 0.90).mean()), 4),
            }

        report = {
            "n": len(pairs),
            "judge_primary": C.JUDGE_MODEL,
            "judge_secondary": C.JUDGE_MODEL_ALT,
            "outcome_agreement": round(agree, 4),
            "cohens_kappa": round(cohens_kappa(a, b), 4),
            "kappa_caveat": ("outcome codes are ~99% 'claim', so kappa is "
                             "unstable here; claim_similarity is the "
                             "informative measure"),
            "claim_similarity": claim_sim,
        }
        print(json.dumps(report, indent=2))
        (C.DATA / "validation_report.json").write_text(json.dumps(report, indent=2))
        return

    print(f"judging with {C.JUDGE_MODEL}")
    run_judge(rows, C.JUDGE_MODEL, key, args.concurrency, C.NORMALIZED, desc="")
    print(f"-> {C.NORMALIZED}")


if __name__ == "__main__":
    main()
