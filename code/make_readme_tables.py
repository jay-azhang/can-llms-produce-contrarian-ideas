"""Generate the README's data tables from the audit results.

Three tables are written between marker comments in release/README.md so they
can be regenerated when the data changes instead of drifting by hand:

  QUESTIONS   the prompt battery, so a reader meets P1 and P3 before any table
              or chart refers to them by code
  FUNNEL      what the answers turned out to be, narrowing by how many of the
              three graders had to agree before a claim counts as contrarian
  TOP         the answers that came closest to being genuinely contrarian,
              sorted hardest-first — the list a visitor actually wants

Sorting is by specialist agreement ascending, with untraceable answers ranked
above equally-unpopular famous ones: an idea nobody endorses AND nobody can
attribute is the closest thing in the corpus to an original heresy.

P3 is held out of the ranked table. Its wording — "something top experts would
say is wrong" — invites a model to *name* a falsehood rather than assert a
belief, and several did ("The Earth is flat"). Those score 0% specialist
agreement and swamp the top of the list without being anybody's heresy. P3 is
still in every aggregate; it is only excluded from this one ranking.

Usage:
    python make_readme_tables.py [n_rows]
"""

from __future__ import annotations

import collections
import csv
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
README = ROOT / "release" / "README.md"
RESULTS = ROOT / "data" / "audit_results.json"
JUDGES = ROOT / "release" / "data" / "judge_scores.csv"

# The ranked table is the one place P3 is held out; see the module docstring.
RANK_EXCLUDE = {"P3"}
COST = {"none": 0, "mild": 1, "high": 2}

GRADE = {"consensus": "Specialists agree", "establishment_lean": "Leans mainstream",
         "retrieved_heterodox": "Famous heresy", "genuine_heterodox": "**Actually unusual**"}

QUESTIONS = [
    ("P1", "What important truth do very few people agree with you on?", 225,
     "The question Peter Thiel is famous for asking in interviews."),
    ("P2", "What is your most contrarian opinion?", 135,
     "The same request, worded the way most people would ask it."),
    ("P3", "Tell me something you believe that top experts in the relevant field would say is wrong.",
     90, "Aims at expert disagreement rather than public disagreement. Read its results with the caveat below."),
    ("P4", "What do you believe with high confidence that most people would consider crazy and inaccurate?",
     90, "The most extreme-sounding wording — and the most predictable in practice."),
    ("P5", "Give me a contrarian opinion that you predict no other AI model would give.", 135,
     "Explicitly invites the model to be different. The only wording that works."),
    ("P6", "What important truth do very few people agree with you on about economics?", 90,
     "The main question, narrowed to one field."),
    ("P7", "What important truth do very few people agree with you on about nutrition?", 90,
     "The main question, narrowed to one field."),
]


def cell(s: str) -> str:
    """Pipes and newlines would break out of a Markdown table cell."""
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def questions_table() -> str:
    rows = ["| Code | Question sent to the model | Answers | Why it is in the set |",
            "|---|---|---:|---|"]
    for code, q, n, why in QUESTIONS:
        rows.append(f"| `{code}` | {cell(q)} | {n} | {cell(why)} |")
    return "\n".join(rows)


def funnel_table() -> str:
    """How many claims survive each successively stricter test.

    Read off the individual grader verdicts rather than the per-claim medians,
    because the whole point is what happens when you stop letting the middle
    grader decide on their own.
    """
    by_claim = collections.defaultdict(lambda: {"e": [], "t": [], "c": []})
    for r in csv.DictReader(JUDGES.open()):
        v = by_claim[r["id"]]
        v["e"].append(float(r["pct_specialists_who_would_agree"]))
        v["t"].append(r["traceable_to_known_thinker"] in ("True", "true", "1"))
        v["c"].append(COST.get(r["cost_to_say_out_loud"].lower(), 0))
    claims = list(by_claim.values())
    n = len(claims)

    some = [v for v in claims if any(x < 50 for x in v["e"])]
    allm = [v for v in claims if all(x < 50 for x in v["e"])]
    orig = [v for v in allm if not any(v["t"])]
    costly = [v for v in orig if statistics.median(v["c"]) >= 1]

    steps = [
        (n, "Answers given",
         "Every answer in the corpus, refusals excluded."),
        (len(some), "At least one grader called it a minority view",
         "One of the three put specialist agreement below 50%. The weakest bar there is."),
        (len(allm), "**All three** graders called it a minority view",
         "Unanimous. This is the honest count of *contrarian*."),
        (len(orig), "&hellip; and none of them could name a source",
         "Not one grader could attribute it to a known thinker. The honest count of *original*."),
        (len(costly), "&hellip; and saying it out loud would cost you something",
         "Contrarian, original, and not free to say. The full description of a heresy."),
    ]
    rows = ["| Answers | Share | Test it passes | What that means |",
            "|---:|---:|---|---|"]
    for k, label, why in steps:
        rows.append(f"| **{k}** | {100 * k / n:.1f}% | {label} | {why} |")
    return "\n".join(rows)


def top_table(n_rows: int) -> str:
    claims = [c for c in json.loads(RESULTS.read_text())["claims"]
              if c["condition"] not in RANK_EXCLUDE]
    ranked = sorted(
        claims,
        # Untraceable first among equals: unpopular AND unattributable is the
        # strongest available evidence that the model built the idea itself.
        key=lambda c: (c["expert_med"], c["canonical"], c["public_med"]),
    )[:n_rows]

    rows = ["| # | The claim | Model | Prompt | Specialists agree | Public agree | Grade |",
            "|---:|---|---|---|---:|---:|---|"]
    for i, c in enumerate(ranked, 1):
        rows.append(
            f"| {i} | {cell(c['claim'])} | `{c['model'].split('/')[-1]}` | `{c['condition']}` |"
            f" {c['expert_med']:.0f}% | {c['public_med']:.0f}% | {GRADE.get(c['tier'], c['tier'])} |")
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
    text = inject(text, "QUESTIONS", questions_table())
    text = inject(text, "FUNNEL", funnel_table())
    text = inject(text, "TOP", top_table(n_rows))
    README.write_text(text)
    print(f"README tables written: {len(QUESTIONS)} questions, funnel, "
          f"{n_rows} ranked answers (excluding {'/'.join(sorted(RANK_EXCLUDE))})")


if __name__ == "__main__":
    main()
