"""Stage 4 — clustering and metrics.

Produces every number behind the four headline artifacts:

  1. the table    — top opinion clusters with per-model frequencies
  2. the curves   — rarefaction: distinct opinions discovered vs samples drawn
  3. the heatmap  — pairwise divergence between models' opinion distributions
  4. the number   — effective distinct opinions per model, exp(Shannon entropy)

Everything is computed twice, once per embedding space, and both are reported.
A finding that moves between the two spaces is an embedding artifact.

Clustering is done ONCE over the pooled set of all models' claims, then each
model's distribution is read off the shared cluster labels. Clustering each
model separately would produce incomparable label sets and make cross-model
divergence undefined.

Usage:
    python analyze.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from itertools import combinations

import numpy as np
from scipy.special import gammaln
from sklearn.cluster import AgglomerativeClustering, HDBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

PCA_DIMS = 50
# Smallest per-model n across the temperature arms; all arms rarefy to it.
TEMP_MATCH_N = 12
RNG = np.random.default_rng(20260817)


# --------------------------------------------------------------------------- #
# Diversity metrics
# --------------------------------------------------------------------------- #

def hill(counts: np.ndarray, q: int) -> float:
    """Hill number of order q — the 'effective number of distinct opinions'.

    q=0 is the raw cluster count, q=1 is exp(Shannon) and weights clusters by
    frequency, q=2 is inverse-Simpson and is dominated by the largest cluster.
    Hill numbers are used rather than raw entropy because they are on the scale
    of "number of opinions", which is the unit the headline claim is stated in.
    """
    p = counts[counts > 0].astype(float)
    p = p / p.sum()
    if q == 0:
        return float(len(p))
    if q == 1:
        return float(np.exp(-(p * np.log(p)).sum()))
    return float((p ** q).sum() ** (1.0 / (1.0 - q)))


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence in bits (0 = identical, 1 = disjoint support).

    scipy's jensenshannon returns the *distance* (the square root); this is the
    divergence itself, which is what the design specifies.
    """
    p = p / p.sum()
    q = q / q.sum()
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = a > 0
        return float((a[mask] * np.log2(a[mask] / b[mask])).sum())

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def rarefaction(counts: np.ndarray, max_m: int | None = None) -> tuple[list, list]:
    """Expected distinct clusters when drawing m samples without replacement.

    Uses the exact Hurlbert expectation rather than bootstrap resampling, so
    the curve is deterministic and has no simulation noise:
        E[S_m] = sum_i (1 - C(N - n_i, m) / C(N, m))
    Computed in log-space; the binomials overflow badly otherwise.
    """
    n = counts[counts > 0].astype(float)
    N = int(n.sum())
    max_m = max_m or N
    xs, ys = [], []
    for m in range(1, max_m + 1):
        # log C(N - n_i, m) - log C(N, m), guarded where N - n_i < m
        with np.errstate(invalid="ignore"):
            log_num = gammaln(N - n + 1) - gammaln(m + 1) - gammaln(N - n - m + 1)
            log_den = gammaln(N + 1) - gammaln(m + 1) - gammaln(N - m + 1)
            frac = np.exp(log_num - log_den)
        frac = np.where(N - n < m, 0.0, frac)
        xs.append(m)
        ys.append(float((1.0 - frac).sum()))
    return xs, ys


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #

def cluster_pooled(vecs: np.ndarray, threshold: float) -> tuple[np.ndarray, dict]:
    """Agglomerative clustering at the empirically calibrated "same opinion"
    cosine threshold, with HDBSCAN and k-means retained as robustness checks.

    Agglomerative is primary because its one free parameter is exactly the
    quantity calibrate.py measured against LLM-judge adjudication: the cosine
    at which two claims stop being the same opinion. HDBSCAN's `min_cluster_size`
    has no such external referent, and at min_cluster_size=3 it split 1064
    claims into 428 mostly-singleton clusters (28% noise, silhouette 0.15),
    which drives every distributional metric to its degenerate limit — pairwise
    JSD near 1.0 purely because the distributions share almost no support.

    Average linkage, so a cluster absorbs a new claim when it is that similar
    to the cluster *on average* rather than to a single nearest member; single
    linkage chains unrelated opinions together through intermediate claims.
    """
    n = len(vecs)
    agg = AgglomerativeClustering(
        n_clusters=None, distance_threshold=1.0 - threshold,
        metric="cosine", linkage="average")
    labels = agg.fit_predict(vecs)

    sizes = Counter(labels)
    info = {
        "n_items": n,
        "primary_method": "agglomerative_cosine_average",
        "calibrated_threshold": threshold,
        "n_clusters": int(len(sizes)),
        "n_singletons": int(sum(1 for v in sizes.values() if v == 1)),
        "singleton_rate": round(sum(1 for v in sizes.values() if v == 1) / len(sizes), 4),
        "largest_cluster": int(max(sizes.values())),
        "median_cluster_size": float(np.median(list(sizes.values()))),
    }
    try:
        info["silhouette_agglomerative"] = round(
            float(silhouette_score(vecs, labels, metric="cosine")), 4)
    except Exception:
        info["silhouette_agglomerative"] = None

    # --- robustness: HDBSCAN over PCA-reduced vectors -----------------------
    # Noise points are promoted to singletons rather than dropped: a claim too
    # unusual to join any cluster is the most distinctive thing a model
    # produced, and discarding it would make every model look *less* diverse.
    dims = min(PCA_DIMS, n - 1, vecs.shape[1])
    reduced = PCA(n_components=dims, random_state=0).fit_transform(vecs)
    hdb_labels = HDBSCAN(min_cluster_size=3, min_samples=1,
                         metric="euclidean").fit_predict(reduced)
    noise = hdb_labels == -1
    nxt = int(hdb_labels.max()) + 1 if (hdb_labels >= 0).any() else 0
    hdb_labels = hdb_labels.copy()
    for i in np.where(noise)[0]:
        hdb_labels[i] = nxt
        nxt += 1
    info["hdbscan_n_clusters"] = int(len(set(hdb_labels)))
    info["hdbscan_noise_rate"] = round(float(noise.mean()), 4)

    k = max(2, min(info["n_clusters"], n - 1))
    km_labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(reduced)
    info["kmeans_k"] = k
    try:
        info["silhouette_hdbscan"] = round(float(silhouette_score(reduced, hdb_labels)), 4)
        info["silhouette_kmeans"] = round(float(silhouette_score(reduced, km_labels)), 4)
    except Exception:
        info["silhouette_hdbscan"] = info["silhouette_kmeans"] = None

    return labels, info, {"hdbscan": hdb_labels, "kmeans": km_labels}


# --------------------------------------------------------------------------- #
# Per-space analysis
# --------------------------------------------------------------------------- #

def hill_at_n(labels, n_target: int, q: int = 1, reps: int = 400) -> float | None:
    """Mean Hill number over random subsamples of fixed size.

    Hill numbers grow with sample size, so comparing exp(Shannon) between cells
    of different n measures the n, not the diversity. Every cross-condition
    comparison here (temperature arms at n=12 vs P1 at n=25, paraphrase cells
    at n=86..225) therefore rarefies to a common n before comparing.
    """
    labels = np.asarray(labels)
    if len(labels) < n_target:
        return None
    vals = []
    for _ in range(reps):
        pick = RNG.choice(len(labels), size=n_target, replace=False)
        cnt = np.array(list(Counter(labels[pick]).values()), dtype=float)
        vals.append(hill(cnt, q))
    return round(float(np.mean(vals)), 3)


def dist_over(labels_subset, all_labels) -> np.ndarray:
    """Frequency vector over the shared global cluster vocabulary."""
    vocab = sorted(set(all_labels))
    c = Counter(labels_subset)
    return np.array([c.get(v, 0) for v in vocab], dtype=float)


def analyze_space(tag, vecs, index, norm_rows, threshold):
    models = [m for m in C.MODEL_IDS if any(r["model"] == m for r in index)]
    labels, cinfo, alt_labels = cluster_pooled(vecs, threshold)

    core_idx = [i for i, r in enumerate(index) if r["condition"] in C.CORE_CONDITIONS]
    core_labels = labels[core_idx]
    core_rows = [index[i] for i in core_idx]

    # --- the number: effective diversity per model (core conditions) --------
    per_model = {}
    for m in models:
        sel = [i for i, r in enumerate(core_rows) if r["model"] == m]
        if not sel:
            continue
        lab = core_labels[sel]
        counts = np.array(list(Counter(lab).values()), dtype=float)
        top5 = sum(sorted(Counter(lab).values(), reverse=True)[:5])
        xs, ys = rarefaction(counts)
        per_model[m] = {
            "n_claims": int(len(lab)),
            "n_distinct_clusters": int(len(set(lab))),
            "hill_q0": round(hill(counts, 0), 3),
            "hill_q1_effective_opinions": round(hill(counts, 1), 3),
            "hill_q2_simpson": round(hill(counts, 2), 3),
            "top5_mode_share": round(top5 / len(lab), 4),
            "rarefaction_x": xs,
            "rarefaction_y": [round(v, 3) for v in ys],
        }

    # --- the heatmap: pairwise JSD between models' cluster distributions ----
    dists = {m: dist_over([core_labels[i] for i, r in enumerate(core_rows)
                           if r["model"] == m], core_labels)
             for m in per_model}
    jsd_matrix = {}
    for a, b in combinations(per_model, 2):
        jsd_matrix[f"{a}||{b}"] = round(jsd(dists[a], dists[b]), 4)

    # --- within vs between embedding similarity -----------------------------
    # The thesis test: if between-model distance is comparable to within-model
    # distance, the labs are drawing from one generator.
    core_vecs = vecs[core_idx]
    by_model_vecs = {m: core_vecs[[i for i, r in enumerate(core_rows)
                                   if r["model"] == m]] for m in per_model}

    def mean_pairwise(A, B=None):
        if B is None:
            if len(A) < 2:
                return None
            S = A @ A.T
            iu = np.triu_indices(len(A), k=1)
            return float(S[iu].mean())
        return float((A @ B.T).mean())

    within = {m: mean_pairwise(v) for m, v in by_model_vecs.items()}
    between = {f"{a}||{b}": mean_pairwise(by_model_vecs[a], by_model_vecs[b])
               for a, b in combinations(by_model_vecs, 2)}
    w_vals = [v for v in within.values() if v is not None]
    b_vals = [v for v in between.values() if v is not None]

    # --- the table: top clusters with per-model frequencies -----------------
    top_clusters = []
    for cid, n in Counter(core_labels).most_common(15):
        member_rows = [core_rows[i] for i, l in enumerate(core_labels) if l == cid]
        # Exemplar = claim closest to the cluster centroid, i.e. the most
        # representative phrasing rather than an arbitrary first member.
        midx = [i for i, l in enumerate(core_labels) if l == cid]
        cvecs = core_vecs[midx]
        centroid = cvecs.mean(axis=0)
        centroid /= max(np.linalg.norm(centroid), 1e-9)
        exemplar = member_rows[int(np.argmax(cvecs @ centroid))]
        per = Counter(r["model"] for r in member_rows)
        top_clusters.append({
            "cluster_id": int(cid),
            "size": int(n),
            "share_of_all_core": round(n / len(core_labels), 4),
            "exemplar_claim": exemplar["canonical_claim"],
            "topic_mode": Counter(r["topic"] for r in member_rows).most_common(1)[0][0],
            "n_models_present": len(per),
            "per_model_count": {m: per.get(m, 0) for m in per_model},
            "per_model_pct": {m: round(per.get(m, 0) / max(per_model[m]["n_claims"], 1), 4)
                              for m in per_model},
            "sample_claims": [r["canonical_claim"] for r in member_rows[:5]],
        })

    # --- H5: does P6 ("no other AI would give this") actually diverge? ------
    def between_sim_for(cond):
        sel = [i for i, r in enumerate(index) if r["condition"] == cond]
        bym = {}
        for m in models:
            ms = [i for i in sel if index[i]["model"] == m]
            if ms:
                bym[m] = vecs[ms]
        vals = [mean_pairwise(bym[a], bym[b]) for a, b in combinations(bym, 2)]
        return float(np.mean(vals)) if vals else None

    p1_between = between_sim_for("P1")
    p6_between = between_sim_for("P6")
    h5 = None
    if p1_between and p6_between:
        h5 = {
            "p1_mean_between_model_similarity": round(p1_between, 4),
            "p6_mean_between_model_similarity": round(p6_between, 4),
            "pct_reduction": round(100 * (p1_between - p6_between) / p1_between, 2),
            "hypothesis": "H5 predicts <20% reduction",
            "supported": bool((p1_between - p6_between) / p1_between < 0.20),
        }

    # --- paraphrase robustness ----------------------------------------------
    para = {}
    para_match_n = min(
        sum(1 for r in index if r["condition"] == c)
        for c in C.PARAPHRASE_CONDITIONS
        if any(r["condition"] == c for r in index))
    for cond in C.PARAPHRASE_CONDITIONS:
        sel = [i for i, r in enumerate(index) if r["condition"] == cond]
        if not sel:
            continue
        counts = np.array(list(Counter(labels[sel]).values()), dtype=float)
        para[C.published_condition(cond) or cond] = {
            "n": len(sel),
            "hill_q1_raw": round(hill(counts, 1), 3),
            "hill_q1_at_matched_n": hill_at_n(labels[sel], para_match_n, 1),
            "matched_n": para_match_n,
            "n_clusters": int(len(set(labels[sel]))),
        }

    # --- robustness: does the headline number survive the clustering method? -
    # Reported rather than reconciled. If exp(Shannon) moves a lot between
    # agglomerative, HDBSCAN and k-means, the number is a property of the
    # algorithm and the study should say so.
    robustness = {}
    for meth, labs in (("agglomerative", labels), ("hdbscan", alt_labels["hdbscan"]),
                       ("kmeans", alt_labels["kmeans"])):
        core_l = labs[core_idx]
        vals = {}
        for m in models:
            sel = [i for i, r in enumerate(core_rows) if r["model"] == m]
            if sel:
                cnt = np.array(list(Counter(core_l[sel]).values()), dtype=float)
                vals[m] = round(hill(cnt, 1), 3)
        md = {m: dist_over([core_l[i] for i, r in enumerate(core_rows)
                            if r["model"] == m], core_l) for m in vals}
        pj = [jsd(md[a], md[b]) for a, b in combinations(md, 2)]
        robustness[meth] = {
            "mean_hill_q1": round(float(np.mean(list(vals.values()))), 3),
            "per_model_hill_q1": vals,
            "mean_pairwise_jsd": round(float(np.mean(pj)), 4) if pj else None,
        }

    # --- permutation null: are the models distinguishable at all? -----------
    # This is the load-bearing test of the whole study, and the reason raw JSD
    # cannot be read directly at pilot sample sizes. With ~55 core claims per
    # model spread over a few hundred clusters, two IDENTICAL generators would
    # still produce near-disjoint empirical distributions and a JSD close to 1,
    # purely from sampling sparsity.
    #
    # So the observed statistics are compared against the distribution they
    # take when model labels are shuffled across the pooled claims, holding
    # each model's sample size fixed. Under the null, every "model" is a random
    # draw from one common generator — literally the "five labs, one generator"
    # hypothesis. If the observed statistic sits inside that null distribution,
    # the models are statistically indistinguishable; if it sits far outside,
    # they are genuinely different and the thesis fails.
    n_perm = 500
    obs_jsd = float(np.mean(list(jsd_matrix.values()))) if jsd_matrix else None
    obs_gap = (float(np.mean(w_vals)) - float(np.mean(b_vals))) if w_vals and b_vals else None

    model_of = np.array([r["model"] for r in core_rows])
    sizes = {m: int((model_of == m).sum()) for m in per_model}
    null_jsd, null_gap = [], []
    for _ in range(n_perm):
        perm = RNG.permutation(len(core_rows))
        start, assign = 0, {}
        for m, sz in sizes.items():
            assign[m] = perm[start:start + sz]
            start += sz
        d = {m: dist_over(core_labels[idx], core_labels) for m, idx in assign.items()}
        null_jsd.append(float(np.mean([jsd(d[a], d[b])
                                       for a, b in combinations(d, 2)])))
        wv = [mean_pairwise(core_vecs[idx]) for idx in assign.values()
              if len(idx) > 1]
        bv = [mean_pairwise(core_vecs[assign[a]], core_vecs[assign[b]])
              for a, b in combinations(assign, 2)]
        null_gap.append(float(np.mean(wv) - np.mean(bv)))

    null_jsd_a, null_gap_a = np.array(null_jsd), np.array(null_gap)

    def z(obs, null):
        sd = float(null.std())
        return round((obs - float(null.mean())) / sd, 3) if sd > 1e-12 else None

    permutation = {
        "n_permutations": n_perm,
        "note": ("null = model labels shuffled across pooled claims, i.e. all "
                 "models drawn from one generator. Observed values inside the "
                 "null interval mean the models are not distinguishable at "
                 "this sample size."),
        "jsd": {
            "observed": round(obs_jsd, 4) if obs_jsd else None,
            "null_mean": round(float(null_jsd_a.mean()), 4),
            "null_sd": round(float(null_jsd_a.std()), 4),
            "null_ci95": [round(float(np.percentile(null_jsd_a, 2.5)), 4),
                          round(float(np.percentile(null_jsd_a, 97.5)), 4)],
            "z": z(obs_jsd, null_jsd_a) if obs_jsd else None,
            "p_two_sided": round(float((np.abs(null_jsd_a - null_jsd_a.mean())
                                        >= abs(obs_jsd - null_jsd_a.mean())).mean()), 4)
            if obs_jsd else None,
        },
        "within_minus_between_gap": {
            "observed": round(obs_gap, 4) if obs_gap is not None else None,
            "null_mean": round(float(null_gap_a.mean()), 4),
            "null_sd": round(float(null_gap_a.std()), 4),
            "null_ci95": [round(float(np.percentile(null_gap_a, 2.5)), 4),
                          round(float(np.percentile(null_gap_a, 97.5)), 4)],
            "z": z(obs_gap, null_gap_a) if obs_gap is not None else None,
            "p_one_sided_greater": round(float((null_gap_a >= obs_gap).mean()), 4)
            if obs_gap is not None else None,
        },
    }

    # --- pooled across all models -------------------------------------------
    pooled_counts = np.array(list(Counter(core_labels).values()), dtype=float)
    pooled_x, pooled_y = rarefaction(pooled_counts)

    return {
        "embedding_space": tag,
        "cluster_info": cinfo,
        "robustness_hill_q1": robustness,
        "per_model": per_model,
        "jsd_matrix": jsd_matrix,
        "within_model_similarity": {k: round(v, 4) for k, v in within.items() if v},
        "between_model_similarity": {k: round(v, 4) for k, v in between.items() if v},
        "within_vs_between": {
            "mean_within": round(float(np.mean(w_vals)), 4) if w_vals else None,
            "mean_between": round(float(np.mean(b_vals)), 4) if b_vals else None,
            "gap": round(float(np.mean(w_vals) - np.mean(b_vals)), 4) if w_vals and b_vals else None,
        },
        "mean_pairwise_jsd": round(float(np.mean(list(jsd_matrix.values()))), 4) if jsd_matrix else None,
        "top_clusters": top_clusters,
        "paraphrase": para,
        "h5_self_aware_divergence": h5,
        "permutation_null": permutation,
        "pooled_rarefaction": {"x": pooled_x, "y": [round(v, 3) for v in pooled_y]},
    }


def main() -> None:
    calib = json.loads((C.DATA / "calibration.json").read_text())
    index = [json.loads(l) for l in open(C.DATA / "embed_index.jsonl")]
    # Temperature arms are excluded from every published figure. Filtering here
    # rather than downstream keeps the clustering, the metrics and the reported
    # per-condition tables all computed over the same rows.
    index = [r for r in index
             if C.published_condition(r["condition"]) is not None]
    norm_rows = [json.loads(l) for l in open(C.NORMALIZED)]
    gens = [json.loads(l) for l in open(C.GENERATIONS)]

    # --- outcome rates: refusals and hedges are results, not dropped rows ---
    outcomes = {}
    for m in C.MODEL_IDS:
        rs = [r for r in norm_rows if r["model"] == m]
        if not rs:
            continue
        c = Counter(r["outcome"] for r in rs)
        n = len(rs)
        outcomes[m] = {
            "n_normalized": n,
            "claim_rate": round(c.get("claim", 0) / n, 4),
            "refusal_rate": round(c.get("refusal", 0) / n, 4),
            "hedge_rate": round(c.get("hedge", 0) / n, 4),
            "judge_error_rate": round(c.get("judge_error", 0) / n, 4),
        }

    # --- generation-side health --------------------------------------------
    health = {}
    for m in C.MODEL_IDS:
        rs = [r for r in gens if r["model"] == m]
        if not rs:
            continue
        ok = [r for r in rs if r.get("ok")]
        health[m] = {
            "n_calls": len(rs),
            "n_ok": len(ok),
            "fail_rate": round(1 - len(ok) / len(rs), 4),
            "truncated_rate": round(sum(r.get("finish_reason") == "length" for r in ok) / max(len(ok), 1), 4),
            "reasoning_fallback_rate": round(sum(bool(r.get("used_reasoning_fallback")) for r in ok) / max(len(ok), 1), 4),
            "mean_completion_tokens": round(float(np.mean([r.get("completion_tokens") or 0 for r in ok])), 1),
            "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in ok), 4),
            "mean_latency_s": round(float(np.mean([r.get("latency_s") or 0 for r in ok])), 2),
        }

    results = {
        "meta": {
            "models": {m: C.MODEL_META[m] for m in C.MODEL_IDS},
            "conditions": [{"id": C.published_condition(c[0]), "n_pilot": c[3]}
                           for c in C.CONDITIONS
                           if C.published_condition(c[0]) is not None],
            "judge": C.JUDGE_MODEL,
            "embed_closed": C.EMBED_CLOSED,
            "embed_open": C.EMBED_OPEN,
            "calibration": calib,
            "max_tokens": C.MAX_TOKENS,
            "reasoning": C.REASONING,
            "top_p": C.TOP_P,
            "n_generations": len(gens),
            "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in gens), 4),
        },
        "outcome_rates": outcomes,
        "generation_health": health,
        "spaces": {},
    }

    for tag in ("closed", "open"):
        path = C.DATA / f"emb_{tag}.npy"
        if not path.exists():
            print(f"skip {tag}: {path} missing")
            continue
        vecs = np.load(path)
        # The index was filtered above; the vector array still holds every row,
        # so it has to be subset by the same mask or claims and vectors desync.
        full = [json.loads(l) for l in open(C.DATA / "embed_index.jsonl")]
        keep = [i for i, r in enumerate(full)
                if C.published_condition(r["condition"]) is not None]
        vecs = vecs[keep]
        print(f"analyzing {tag} space {vecs.shape}")
        results["spaces"][tag] = analyze_space(tag, vecs, index, norm_rows,
                                              calib["spaces"][tag]["threshold"])

    # --- cross-space replication check --------------------------------------
    if len(results["spaces"]) == 2:
        a, b = results["spaces"]["closed"], results["spaces"]["open"]
        ma = {m: v["hill_q1_effective_opinions"] for m, v in a["per_model"].items()}
        mb = {m: v["hill_q1_effective_opinions"] for m, v in b["per_model"].items()}
        common = sorted(set(ma) & set(mb))
        if len(common) > 2:
            x = np.array([ma[m] for m in common])
            y = np.array([mb[m] for m in common])
            # Spearman via rank-Pearson: does the *ordering* of models by
            # diversity survive changing the embedding space?
            rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
            rho = float(np.corrcoef(rx, ry)[0, 1])
            results["replication"] = {
                "n_models": len(common),
                "hill_q1_closed": {m: ma[m] for m in common},
                "hill_q1_open": {m: mb[m] for m in common},
                "spearman_rho_model_ranking": round(rho, 4),
                "mean_jsd_closed": a["mean_pairwise_jsd"],
                "mean_jsd_open": b["mean_pairwise_jsd"],
            }

    C.RESULTS.write_text(json.dumps(results, indent=2))
    print(f"-> {C.RESULTS}")


if __name__ == "__main__":
    main()
