"""Stage 3 — embedding.

Embeds every canonical claim under two independent embedding models: one
closed-weights, one open-weights. The design requires that headline results
replicate across both; a result that appears under only one embedding space is
an artifact of that space, not a fact about the models.

Vectors are written as .npy next to an index file mapping row order back to
generation ids. They are deliberately NOT committed — they are large and fully
reproducible from generations.jsonl plus this script.

Usage:
    python embed.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

API = "https://openrouter.ai/api/v1/embeddings"
BATCH = 64


def api_key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        sys.exit("OPENROUTER_API_KEY not set")
    return k


def embed_batch(session, key, model, texts) -> list[list[float]]:
    for attempt in range(5):
        try:
            r = session.post(API, headers={"Authorization": f"Bearer {key}"},
                             json={"model": model, "input": texts}, timeout=180)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            d = r.json()
            if "error" in d:
                time.sleep(2 ** attempt)
                continue
            # Preserve request order — the API returns an index per item, and
            # a reordered batch would silently mis-associate every claim with
            # someone else's vector.
            items = sorted(d["data"], key=lambda x: x["index"])
            return [it["embedding"] for it in items]
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embedding failed after retries: {model}")


def main() -> None:
    key = api_key()
    rows = [json.loads(l) for l in open(C.NORMALIZED)]
    # Only rows with an actual extracted claim enter the embedding space.
    # Refusals and hedges are counted separately as outcome rates; they have no
    # belief content to place in a semantic space.
    claims = [r for r in rows if r["outcome"] == "claim" and r["canonical_claim"]]
    print(f"{len(claims)} claims to embed (of {len(rows)} normalized rows)")

    index = [{"id": r["id"], "model": r["model"], "condition": r["condition"],
              "sample_idx": r["sample_idx"], "canonical_claim": r["canonical_claim"],
              "topic": r["topic"]} for r in claims]
    with open(C.DATA / "embed_index.jsonl", "w") as f:
        for r in index:
            f.write(json.dumps(r) + "\n")

    texts = [r["canonical_claim"] for r in claims]
    session = requests.Session()

    for tag, model in (("closed", C.EMBED_CLOSED), ("open", C.EMBED_OPEN)):
        print(f"embedding with {model} ({tag})")
        vecs = []
        for i in range(0, len(texts), BATCH):
            vecs.extend(embed_batch(session, key, model, texts[i:i + BATCH]))
            print(f"  {min(i + BATCH, len(texts))}/{len(texts)}", flush=True)
        arr = np.array(vecs, dtype=np.float32)
        # L2-normalize once here so downstream cosine work is a plain dot
        # product and every metric sees identically scaled vectors.
        arr /= np.linalg.norm(arr, axis=1, keepdims=True).clip(min=1e-9)
        path = C.DATA / f"emb_{tag}.npy"
        np.save(path, arr)
        print(f"  -> {path} shape={arr.shape}")


if __name__ == "__main__":
    main()
