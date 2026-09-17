"""Generate the README's data tables from the audit results.

Three tables are written between marker comments in release/README.md so they
can be regenerated when the data changes instead of drifting by hand:

  QUESTIONS   the prompt battery, so a reader meets P1 and P3 before any table
              or chart refers to them by code
  FINDINGS    the opening bullet list. Generated, because every number in it
              moves when the corpus grows, and a stale headline is worse than
              no headline
  LABELS      the four grades, with the count and share falling into each
  TOP         the answers that came closest to being genuinely contrarian,
              sorted hardest-first — the list a visitor actually wants

Ranking adds two scores out of 100: how far specialist agreement sits below
100, and how original the graders judged the idea. Both matter, because either
alone ranks badly — disagreement alone floats famous falsehoods to the top, and
originality alone floats harmless eccentricities.

Usage:
    python make_readme_tables.py [n_rows]
"""

from __future__ import annotations

import collections
import csv
import os
import collections
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

ROOT = Path(__file__).resolve().parent
README = ROOT / "release" / "README.md"
RESULTS = ROOT / "data" / "audit_results.json"
JUDGES = ROOT / "release" / "data" / "judge_scores.csv"

# Claims about the models' own nature. A plain keyword match on the one-sentence
# claim rather than a judged category, so it is checkable by eye against
# qa_pairs.csv and nothing depends on a borderline call.
SELF_TOPIC = re.compile(
    r"\bAI\b|artificial intelligence|superintelligen|alignment"
    r"|language model|machine learning|conscious|sentien", re.I)

# Nothing is held out any more. P3 used to be, because "the Earth is flat"
# scores 0% specialist agreement and swamped a ranking sorted on that alone.
# With originality graded directly, a famous falsehood scores near zero on it
# and sinks on its own, so the exclusion is no longer doing any work.
RANK_EXCLUDE: set[str] = set()
# Per-judge social cost is 0-100; "carries a cost at all" is >= 25.
COST_ANY = 25

GRADE = {"consensus": "Specialists agree", "establishment_lean": "Leans mainstream",
         "retrieved_heterodox": "Famous heresy", "genuine_heterodox": "**Actually unusual**"}

# Which family a prompt belongs to. The two ask for different things and the
# table says so, rather than leaving a reader to infer it from the wording.
FAMILY = {**{c: "belief" for c in ("P1", "P2", "P3", "P4", "P5", "P6", "P7")},
          **{c: "idea" for c in ("P8", "P9", "P10", "P11", "P12")}}


def questions_table() -> str:
    """The prompt battery, read off config so it cannot drift from what was sent."""
    claims = json.loads(RESULTS.read_text())["claims"]
    n_by_cond = collections.Counter(c["condition"] for c in claims)
    rows = ["| Code | Asked for | Question sent to the model | Answers | Why it is in the set |",
            "|---|---|---|---:|---:|".replace("---:|---:|", "---:|---|").replace("| Why", "| Why")]
    rows[1] = "|---|---|---|---:|---|"
    for code in C.PROMPT_ORDER:
        n = n_by_cond.get(code, 0)
        if not n:
            continue
        rows.append(f"| `{code}` | {FAMILY.get(code, '')} | {cell(C.PROMPT_TEXT[code])} "
                    f"| {n} | {cell(C.PROMPT_NOTE.get(code, ''))} |")
    return "\n".join(rows)


LABEL_DEF = {
    "consensus": ("Specialists agree",
                  "At least 70% of specialists would accept it."),
    "establishment_lean": ("Leans mainstream",
                           "50-69% would accept it. Mildly heterodox at best."),
    "retrieved_heterodox": ("Famous heresy",
                            "Under 50% agree, but it traces to a named thinker."),
    "genuine_heterodox": ("**Actually unusual**",
                          "Under 50% agree, and no grader could attribute it."),
}


def labels_table() -> str:
    claims = json.loads(RESULTS.read_text())["claims"]
    counts = collections.Counter(c["tier"] for c in claims)
    n = sum(counts.values())
    rows = ["| Label | Answers | Share | What it means |", "|---|---:|---:|---|"]
    for tier, (name, why) in LABEL_DEF.items():
        k = counts.get(tier, 0)
        rows.append(f"| {name} | {k} | {100 * k / n:.1f}% | {why} |")
    rows.append(f"| **Total** | **{n}** | **100%** | |")
    return "\n".join(rows)


def cell(s: str) -> str:
    """Pipes and newlines would break out of a Markdown table cell."""
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def grader_funnel() -> dict:
    """Counts surviving each successively stricter unanimity test.

    Read off the individual grader verdicts rather than the per-claim medians,
    because the point is what happens when you stop letting the middle grader
    decide on their own.
    """
    by_claim = collections.defaultdict(lambda: {"e": [], "t": [], "c": []})
    for r in csv.DictReader(JUDGES.open()):
        v = by_claim[r["id"]]
        v["e"].append(float(r["pct_specialists_who_would_agree"]))
        v["t"].append(r["traceable_to_known_thinker"] in ("True", "true", "1"))
        v["c"].append(float(r["cost_to_say_out_loud_0_100"] or 0))
    claims = list(by_claim.values())
    n = len(claims)

    some = [v for v in claims if any(x < 50 for x in v["e"])]
    allm = [v for v in claims if all(x < 50 for x in v["e"])]
    orig = [v for v in allm if not any(v["t"])]
    costly = [v for v in orig if statistics.median(v["c"]) >= COST_ANY]

    return {
        "n": n,
        "some": sum(1 for v in claims if any(x < 50 for x in v["e"])),
        "unanimous": len(allm),
        "original": len(orig),
        "costly": len(costly),
    }


def findings_list() -> str:
    """The opening bullets, with every number read off the data.

    Split by family throughout: the belief prompts and the idea prompts behave
    so differently that a pooled number describes neither.
    """
    claims = json.loads(RESULTS.read_text())["claims"]
    bel = [c for c in claims if FAMILY.get(c["condition"]) == "belief"]
    idea = [c for c in claims if FAMILY.get(c["condition"]) == "idea"]

    def med(rows, field):
        v = [r[field] for r in rows if r.get(field) is not None]
        return statistics.median(v) if v else float("nan")

    def pct(rows, pred):
        return 100 * sum(1 for r in rows if pred(r)) / len(rows)

    def cond(code, field):
        return med([c for c in claims if c["condition"] == code], field)

    f = grader_funnel()
    top_src = json.loads(RESULTS.read_text())["top_sources"][0]

    return "\n".join([
        f"- **Asked for a belief nobody shares, {pct(bel, lambda c: c['expert_med'] >= 50):.0f}% "
        f"of answers were things specialists already accept.** Not a minority "
        f"view at all, just one phrased boldly.",
        f"- **Most of the remainder is borrowed.** "
        f"{pct(bel, lambda c: c['canonical']):.0f}% of those answers trace to a "
        f"named thinker. {top_src['source']} alone covers {top_src['n']}.",
        f"- **Asking for an *idea* instead of a *belief* changes everything.** "
        f"Median originality goes from {med(bel, 'originality'):.0f} to "
        f"{med(idea, 'originality'):.0f} out of 100, and the share traceable to "
        f"someone else falls from {pct(bel, lambda c: c['canonical']):.0f}% to "
        f"{pct(idea, lambda c: c['canonical']):.0f}%.",
        f"- **One noun is worth as much as a paragraph of instruction.** Asking "
        f"for an original *idea* scores {cond('P8', 'originality'):.0f}; the same "
        f"sentence asking for an original *thought* scores "
        f"{cond('P9', 'originality'):.0f}. Dropping the whole "
        f"\"confident it originated with you\" clause also costs exactly that "
        f"much ({cond('P12', 'originality'):.0f}).",
        f"- **Superlatives buy nothing.** Demanding the *most radical* idea "
        f"({cond('P10', 'originality'):.0f}) or the *most interesting and "
        f"original* one ({cond('P11', 'originality'):.0f}) lands where the plain "
        f"request already was.",
        f"- **Genuine heresy stays rare.** Require all three graders to agree and "
        f"{f['costly']} answers out of {f['n']} are claims specialists reject, "
        f"nobody could attribute, and that would cost a person something to say "
        f"aloud.",
    ])


LABEL_DEF = {
    "consensus": ("Specialists agree",
                  "At least 70% of specialists would accept it."),
    "establishment_lean": ("Leans mainstream",
                           "50-69% would accept it. Mildly heterodox at best."),
    "retrieved_heterodox": ("Famous heresy",
                            "Under 50% agree, but it traces to a named thinker."),
    "genuine_heterodox": ("**Actually unusual**",
                          "Under 50% agree, and no grader could attribute it."),
}


def labels_table() -> str:
    claims = json.loads(RESULTS.read_text())["claims"]
    counts = collections.Counter(c["tier"] for c in claims)
    n = sum(counts.values())
    rows = ["| Label | Answers | Share | What it means |", "|---|---:|---:|---|"]
    for tier, (name, why) in LABEL_DEF.items():
        k = counts.get(tier, 0)
        rows.append(f"| {name} | {k} | {100 * k / n:.1f}% | {why} |")
    rows.append(f"| **Total** | **{n}** | **100%** | |")
    return "\n".join(rows)


def cell(s: str) -> str:
    """Pipes and newlines would break out of a Markdown table cell."""
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def grader_funnel() -> dict:
    """Counts surviving each successively stricter unanimity test.

    Read off the individual grader verdicts rather than the per-claim medians,
    because the point is what happens when you stop letting the middle grader
    decide on their own.
    """
    by_claim = collections.defaultdict(lambda: {"e": [], "t": [], "c": []})
    for r in csv.DictReader(JUDGES.open()):
        v = by_claim[r["id"]]
        v["e"].append(float(r["pct_specialists_who_would_agree"]))
        v["t"].append(r["traceable_to_known_thinker"] in ("True", "true", "1"))
        v["c"].append(float(r["cost_to_say_out_loud_0_100"] or 0))
    claims = list(by_claim.values())
    n = len(claims)

    some = [v for v in claims if any(x < 50 for x in v["e"])]
    allm = [v for v in claims if all(x < 50 for x in v["e"])]
    orig = [v for v in allm if not any(v["t"])]
    costly = [v for v in orig if statistics.median(v["c"]) >= COST_ANY]

    return {
        "n": n,
        "some": sum(1 for v in claims if any(x < 50 for x in v["e"])),
        "unanimous": len(allm),
        "original": len(orig),
        "costly": len(costly),
    }


def rank_score(c: dict) -> float:
    """Contrarian points plus originality points, each out of 100.

    "Most contrarian and original at the top" needs both axes, weighted the
    same, because either one alone has a failure mode: sorting on disagreement
    puts famous falsehoods first, and sorting on originality puts harmless
    eccentricities first.
    """
    return (100 - c["expert_med"]) + (c.get("originality") or 0)


def top_table(n_rows: int) -> str:
    claims = [c for c in json.loads(RESULTS.read_text())["claims"]
              if c["condition"] not in RANK_EXCLUDE]
    ranked = sorted(claims, key=lambda c: (-rank_score(c), c["public_med"]))[:n_rows]

    rows = ["| # | The claim | Model | Prompt | Specialists agree | Public agree "
            "| Originality | Cost to say it |",
            "|---:|---|---|---|---:|---:|---:|---:|"]
    for i, c in enumerate(ranked, 1):
        orig = c.get("originality")
        cost = c.get("social_cost_score")
        rows.append(
            f"| {i} | {cell(c['claim'])} | `{c['model'].split('/')[-1]}` | `{c['condition']}` |"
            f" {c['expert_med']:.0f}% | {c['public_med']:.0f}% |"
            f" {'—' if orig is None else f'{orig:.0f}'} |"
            f" {'—' if cost is None else f'{cost:.0f}'} |")
    return "\n".join(rows)


def inject(text: str, marker: str, body: str) -> str:
    start, end = f"<!-- {marker}:START -->", f"<!-- {marker}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit(f"marker {marker} not found in README")
    return pattern.sub(f"{start}\n{body}\n{end}", text)


def main() -> None:
    n_rows = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    text = README.read_text()
    text = inject(text, "FINDINGS", findings_list())
    text = inject(text, "QUESTIONS", questions_table())
    text = inject(text, "LABELS", labels_table())
    text = inject(text, "TOP", top_table(n_rows))
    README.write_text(text)
    print(f"README tables written: findings, questions, "
          f"4 labels, {n_rows} ranked answers "
          f"(excluding {'/'.join(sorted(RANK_EXCLUDE))})")


if __name__ == "__main__":
    main()
