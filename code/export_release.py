"""Build the public release bundle.

Everything a stranger needs to check the work, in formats they already know how
to open. The internal pipeline files are JSONL keyed on internal ids; this
flattens them into two CSVs that make sense on their own:

  qa_pairs.csv      one row per question asked — the exact prompt, the model's
                    untouched answer, and every grade it received
  judge_scores.csv  one row per individual grader verdict, so anyone can
                    recompute the medians rather than trusting ours

Plain-English column names throughout, because the audience for the release is
not the audience for the pipeline. The internal names are kept alongside in the
data dictionary so the two can be lined up.

Usage:
    python export_release.py
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

REL = C.ROOT / "release"

GRADE = {"consensus": "Specialists agree",
         "establishment_lean": "Leans mainstream",
         "retrieved_heterodox": "Famous heresy",
         "genuine_heterodox": "Actually unusual"}
TYPE = {"academic_canon": "Textbook position",
        "selfhelp_inversion": "Self-help inversion",
        "tech_ingroup": "Tech-world consensus",
        "novel_proposal": "Made-up proposal",
        "institutional_critique": "Institutions are broken",
        "unfalsifiable_reframe": "Vague reframe",
        "taboo_empirical": "Socially costly claim"}
COST = ["none", "mild", "high"]


def main() -> None:
    REL.mkdir(exist_ok=True)
    (REL / "data").mkdir(exist_ok=True)

    gens = {}
    for line in open(C.GENERATIONS):
        r = json.loads(line)
        if r.get("ok"):
            gens[f"{r['model']}|{r['condition']}|{r['sample_idx']}"] = r
    norm = {json.loads(l)["id"]: json.loads(l) for l in open(C.NORMALIZED)}
    audit = {c["id"]: c for c in
             json.load(open(C.DATA / "audit_results.json"))["claims"]}

    # ---- qa_pairs: one row per question asked --------------------------- #
    # Driven off the generation log, not the audit, so refusals and anything
    # that never reached grading still appear. A release that silently omits
    # the rows that did not fit the analysis is not a release.
    rows = []
    n_excluded = 0
    for gid, g in gens.items():
        published = C.published_condition(g["condition"])
        if published is None:
            # Temperature arms: still present in data/raw/generations.jsonl,
            # excluded from the analysis view so the published codes are
            # contiguous and every row in this file is one the analysis used.
            n_excluded += 1
            continue
        n = norm.get(gid, {})
        a = audit.get(gid, {})
        meta = C.MODEL_META[g["model"]]
        rows.append({
            "id": C.published_id(gid),
            "raw_id": gid,
            "model": g["model"],
            "lab": meta["lab"],
            "country": meta["country"],
            "open_weights": meta["open_weights"],
            "prompt_id": published,
            "prompt_question": C.PROMPT_TEXT.get(published, ""),
            "prompt_sent_verbatim": f"{g['prompt']}\n\n{C.FORMAT_SUFFIX}",
            "temperature": g["temperature"],
            "model_answer_verbatim": g.get("text", ""),
            "answer_one_sentence": n.get("canonical_claim", ""),
            "answer_kind": n.get("outcome", ""),
            "topic": n.get("topic", ""),
            "pct_specialists_who_would_agree": a.get("expert_med", ""),
            "pct_public_who_would_agree": a.get("public_med", ""),
            "grade": GRADE.get(a.get("tier", ""), ""),
            "answer_type": TYPE.get(a.get("category", ""), ""),
            "traceable_to": a.get("canonical_source", ""),
            "cost_to_say_out_loud": COST[a["social_cost"]] if a.get("social_cost") is not None else "",
            "grader_disagreement_points": a.get("expert_spread", ""),
            "completion_tokens": g.get("completion_tokens", ""),
            "reasoning_tokens": g.get("reasoning_tokens", ""),
            "cost_usd": g.get("cost_usd", ""),
            "latency_s": g.get("latency_s", ""),
            "finish_reason": g.get("finish_reason", ""),
            "served_by": g.get("provider", ""),
            "token_cap_raised_after_truncation": bool(g.get("repaired", False)),
            "run_utc": g.get("run_utc", ""),
        })
    rows.sort(key=lambda r: (r["prompt_id"], r["model"], r["id"]))

    with open(REL / "data" / "qa_pairs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(REL / "data" / "qa_pairs.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # ---- judge_scores: every individual verdict ------------------------- #
    jrows, seen = [], set()
    for line in open(C.DATA / "audit.jsonl"):
        r = json.loads(line)
        if r.get("expert_agreement") is None:
            continue
        published_j = C.published_condition(r["condition"])
        if published_j is None:
            continue
        key = (r["id"], r["judge"])
        seen.discard(key)          # a repaired verdict supersedes the earlier one
        seen.add(key)
        jrows.append({
            "id": C.published_id(r["id"]),
            "raw_id": r["id"],
            "answered_by_model": r["model"],
            "prompt_id": published_j,
            "graded_by_model": r["judge"],
            "answer_one_sentence": r["claim"],
            "pct_specialists_who_would_agree": r["expert_agreement"],
            "pct_public_who_would_agree": r["public_agreement"],
            "traceable_to_known_thinker": r["canonical"],
            "traceable_to": r["canonical_source"],
            "cost_to_say_out_loud": r["social_cost"],
            "could_evidence_disprove_it": r["falsifiable"],
            "answer_type": TYPE.get(r["category"], r["category"]),
        })
    # Keep only the last verdict per (answer, grader).
    dedup = {}
    for r in jrows:
        dedup[(r["id"], r["graded_by_model"])] = r
    jrows = sorted(dedup.values(), key=lambda r: (r["id"], r["graded_by_model"]))
    with open(REL / "data" / "judge_scores.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(jrows[0].keys()))
        w.writeheader()
        w.writerows(jrows)

    # ---- reports and code ------------------------------------------------ #
    for name in ("report.html", "audit_report.html"):
        shutil.copy(C.ROOT / name, REL / name)
    (REL / "code").mkdir(exist_ok=True)
    for name in ("config.py", "generate.py", "repair_truncated.py", "normalize.py",
                 "embed.py", "calibrate.py", "analyze.py", "contrarian_audit.py",
                 "audit_analyze.py", "export_release.py"):
        shutil.copy(C.ROOT / name, REL / "code" / name)

    n_ref = sum(1 for r in rows if r["answer_kind"] == "refusal")
    print(f"qa_pairs.csv      {len(rows)} rows ({n_ref} refusals kept, "
          f"{n_excluded} temperature-arm rows excluded)")
    print(f"judge_scores.csv  {len(jrows)} rows")
    print(f"-> {REL}")


if __name__ == "__main__":
    main()
