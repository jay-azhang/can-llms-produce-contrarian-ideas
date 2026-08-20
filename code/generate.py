"""Stage 1 — generation.

Draws N independent samples per (model, condition) cell and appends one JSONL
row per call, including the full request config, the raw response text, token
usage and cost. Every downstream stage reads this file and nothing else, so the
dataset released alongside the study is exactly what the analysis ran on.

Fresh context per call: each request is a single user turn with no history and
no system prompt, so samples within a cell are genuinely independent draws
rather than a conversation drifting.

Resumable: rows already present for a (model, condition, sample_idx) triple are
skipped, so an interrupted run continues where it stopped instead of
re-spending. Run with --dry-run for a cost estimate before committing.

Usage:
    python generate.py --pilot              # full pilot matrix
    python generate.py --pilot --dry-run    # cost/latency estimate only
    python generate.py --pilot --limit 2    # 2 samples per cell (smoke test)
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
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

API = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 4
_write_lock = threading.Lock()


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("OPENROUTER_API_KEY not set — run: bash tools/bootstrap-env.sh")
    return key


def build_prompt(text: str) -> str:
    return f"{text}\n\n{C.FORMAT_SUFFIX}"


def extract_content(msg: dict) -> tuple[str, bool]:
    """Return (content, used_reasoning_fallback).

    Reasoning models spend their token budget on a `reasoning` field first and
    can return empty `content` when the budget runs out. That is a real failure
    mode worth measuring, not something to paper over, so it is recorded rather
    than silently backfilled: the fallback flag marks any row where the visible
    answer had to come from the reasoning trace.
    """
    content = (msg.get("content") or "").strip()
    if content:
        return content, False
    reasoning = (msg.get("reasoning") or "").strip()
    return reasoning, bool(reasoning)


def one_call(session: requests.Session, key: str, model: str, cond_id: str,
             prompt_text: str, temperature: float, idx: int) -> dict:
    """One sample. Retries transient failures; records terminal ones as rows."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(prompt_text)}],
        "temperature": temperature,
        "top_p": C.TOP_P,
        "max_tokens": C.MAX_TOKENS,
        "reasoning": C.REASONING,
    }
    base = {
        "model": model,
        "condition": cond_id,
        "sample_idx": idx,
        "prompt": prompt_text,
        "temperature": temperature,
        "top_p": C.TOP_P,
        "max_tokens": C.MAX_TOKENS,
        "reasoning": C.REASONING,
        "run_utc": datetime.now(timezone.utc).isoformat(),
    }

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            r = session.post(API, headers={"Authorization": f"Bearer {key}"},
                             json=body, timeout=180)
            latency = time.time() - t0

            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"http_{r.status_code}"
                time.sleep((2 ** attempt) + random.random())
                continue

            data = r.json()
            if "error" in data:
                msg = str(data["error"].get("message", ""))[:300]
                # Rate/capacity errors are worth another attempt; the rest are
                # deterministic (bad model id, refused params) so stop early.
                if any(w in msg.lower() for w in ("rate", "capacity", "overload", "timeout")):
                    last_err = msg
                    time.sleep((2 ** attempt) + random.random())
                    continue
                return {**base, "ok": False, "error": msg, "latency_s": latency}

            choice = data["choices"][0]
            content, used_reasoning = extract_content(choice.get("message", {}))
            usage = data.get("usage", {}) or {}
            return {
                **base,
                "ok": True,
                "response_model": data.get("model"),
                "provider": data.get("provider"),
                "gen_id": data.get("id"),
                "text": content,
                "used_reasoning_fallback": used_reasoning,
                "finish_reason": choice.get("finish_reason"),
                "native_finish_reason": choice.get("native_finish_reason"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "cost_usd": usage.get("cost"),
                "latency_s": round(latency, 2),
            }
        except Exception as e:  # network/parse — retry
            last_err = f"{type(e).__name__}: {str(e)[:150]}"
            time.sleep((2 ** attempt) + random.random())

    return {**base, "ok": False, "error": f"exhausted_retries: {last_err}"}


def load_done(path) -> set:
    """(model, condition, sample_idx) triples already recorded and successful."""
    done = set()
    if not path.exists():
        return done
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok"):
                done.add((r["model"], r["condition"], r["sample_idx"]))
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="use pilot sample sizes")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap samples per cell (smoke test)")
    ap.add_argument("--models", type=str, default=None,
                    help="comma-separated subset of model ids")
    ap.add_argument("--conditions", type=str, default=None,
                    help="comma-separated subset of condition ids")
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the call matrix and exit without spending")
    args = ap.parse_args()

    models = args.models.split(",") if args.models else C.MODEL_IDS
    n_field = 3 if args.pilot else 4  # index of n_pilot vs n_full

    tasks = []
    for cond in C.CONDITIONS:
        cond_id, text, temp, n_pilot, n_full = cond
        if args.conditions and cond_id not in args.conditions.split(","):
            continue
        n = cond[n_field]
        if args.limit:
            n = min(n, args.limit)
        for model in models:
            for i in range(n):
                tasks.append((model, cond_id, text, temp, i))

    C.DATA.mkdir(parents=True, exist_ok=True)
    done = load_done(C.GENERATIONS)
    todo = [t for t in tasks if (t[0], t[1], t[4]) not in done]

    print(f"matrix: {len(models)} models x conditions -> {len(tasks)} calls")
    print(f"already done: {len(done)} | to run: {len(todo)}")
    if args.dry_run:
        by_cond = {}
        for m, c, _, _, _ in todo:
            by_cond[c] = by_cond.get(c, 0) + 1
        for c, n in sorted(by_cond.items()):
            print(f"  {c:<14} {n}")
        return
    if not todo:
        print("nothing to do")
        return

    key = api_key()
    session = requests.Session()
    t_start = time.time()
    n_ok = n_fail = 0
    cost = 0.0

    with open(C.GENERATIONS, "a") as out:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = {pool.submit(one_call, session, key, m, c, txt, tp, i): (m, c, i)
                    for m, c, txt, tp, i in todo}
            for n_done, fut in enumerate(as_completed(futs), 1):
                row = fut.result()
                with _write_lock:
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                if row.get("ok"):
                    n_ok += 1
                    cost += row.get("cost_usd") or 0.0
                else:
                    n_fail += 1
                if n_done % 25 == 0 or n_done == len(todo):
                    el = time.time() - t_start
                    rate = n_done / el if el else 0
                    eta = (len(todo) - n_done) / rate if rate else 0
                    print(f"  {n_done}/{len(todo)}  ok={n_ok} fail={n_fail}  "
                          f"${cost:.3f}  {el:.0f}s elapsed, ~{eta:.0f}s left",
                          flush=True)

    print(f"\ndone: ok={n_ok} fail={n_fail} spend=${cost:.4f} "
          f"wall={time.time() - t_start:.0f}s")
    print(f"-> {C.GENERATIONS}")


if __name__ == "__main__":
    main()
