"""Build both HTML reports from their templates and the analysis output.

Each template carries a single `__PAYLOAD__` token where its data goes. This
injects it, so the pages are always a pure function of the committed data —
there is no hand-editing step between `analyze.py` and what a reader sees.

    audit_report.html  <- audit_template.html  + data/audit_results.json
    report.html        <- report_template.html + data/results.json

Run after analyze.py or audit_analyze.py, then make_chart_images.py to refresh
the README figures from the rebuilt pages.

Usage:
    python make_reports.py [run-date]
"""

from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

# Fields the corpus browser needs per claim. Everything else in
# audit_results.json is aggregate and is passed through untouched.
CLAIM_FIELDS = (
    "model", "condition", "claim", "expert_med", "public_med",
    "gap_public_expert", "canonical", "canonical_source", "social_cost",
    "social_cost_score", "originality", "originality_spread",
    "category", "category_agreement", "tier", "expert_spread",
    "prompt_text", "raw_output", "temperature", "topic",
)


def inject(template: str, payload: dict) -> str:
    """Splice the payload into the template's script tag.

    `</` is escaped because a literal `</script>` anywhere inside the JSON —
    in a model's own answer text, for instance — would close the tag early and
    silently truncate the page.
    """
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    out = template.replace("__PAYLOAD__", blob)
    if "__PAYLOAD__" in out:
        raise SystemExit("payload token still present after injection")
    return out


def build_audit() -> None:
    data = json.loads((C.DATA / "audit_results.json").read_text())
    data["claims"] = [{k: c.get(k) for k in CLAIM_FIELDS} for c in data["claims"]]
    html = inject((C.ROOT / "audit_template.html").read_text(), data)
    (C.ROOT / "audit_report.html").write_text(html)
    print(f"audit_report.html  {len(html)/1024:.0f} KB  "
          f"({len(data['claims'])} claims)")


def build_diversity(run_date: str) -> None:
    R = json.loads((C.DATA / "results.json").read_text())
    meta = R["meta"]["models"]

    def space(tag: str) -> dict:
        s = R["spaces"][tag]
        models = list(s["per_model"].keys())
        jm = s["jsd_matrix"]
        # The matrix is stored as unordered "a||b" pairs; expand to a square so
        # the page can index it positionally.
        mat = [[0.0] * len(models) for _ in models]
        for i, a in enumerate(models):
            for j, b in enumerate(models):
                if i != j:
                    mat[i][j] = jm.get(f"{a}||{b}", jm.get(f"{b}||{a}", 0.0))
        return {
            "models": [{
                "id": m, "label": meta[m]["label"], "lab": meta[m]["lab"],
                "country": meta[m]["country"], "tier": meta[m]["tier"],
                "open_weights": meta[m]["open_weights"],
                **{k: s["per_model"][m][k] for k in (
                    "n_claims", "n_distinct_clusters",
                    "hill_q1_effective_opinions", "hill_q2_simpson",
                    "top5_mode_share")},
                "rarefaction": {"x": s["per_model"][m]["rarefaction_x"],
                                "y": s["per_model"][m]["rarefaction_y"]},
            } for m in models],
            "jsd_matrix": mat,
            "cluster_info": s["cluster_info"],
            "within_vs_between": s["within_vs_between"],
            "within": s["within_model_similarity"],
            "mean_pairwise_jsd": s["mean_pairwise_jsd"],
            "permutation": s["permutation_null"],
            "robustness": s["robustness_hill_q1"],
            "paraphrase": s["paraphrase"],
            "h5": s["h5_self_aware_divergence"],
            "top_clusters": s["top_clusters"][:12],
            "pooled_rarefaction": s["pooled_rarefaction"],
        }

    payload = {
        "meta": {k: R["meta"][k] for k in (
            "judge", "embed_closed", "embed_open", "max_tokens", "reasoning",
            "top_p", "n_generations", "total_cost_usd")},
        "conditions": R["meta"]["conditions"],
        "calibration": R["meta"]["calibration"],
        "outcome_rates": {meta[m]["label"]: v for m, v in R["outcome_rates"].items()},
        "generation_health": {meta[m]["label"]: v
                              for m, v in R["generation_health"].items()},
        "replication": R["replication"],
        "closed": space("closed"),
        "open": space("open"),
        "validation": json.loads((C.DATA / "validation_report.json").read_text()),
        "run_date": run_date,
    }
    # Kept on disk so the page's inputs are inspectable without unpicking the
    # HTML; the page itself is built from this dict, not from the file.
    (C.DATA / "report_payload.json").write_text(json.dumps(payload))
    html = inject((C.ROOT / "report_template.html").read_text(), payload)
    (C.ROOT / "report.html").write_text(html)
    print(f"report.html        {len(html)/1024:.0f} KB")


def main() -> None:
    run_date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    build_audit()
    build_diversity(run_date)


if __name__ == "__main__":
    main()
