# Context for a new session

Everything needed to rerun or extend this study is in this repository. This
file is the handoff: what the pipeline does, the decisions that are easy to get
wrong, and what is still open.

## What this is

Nine frontier models, eight labs, asked for their most heretical beliefs under
seven prompt framings. Every answer graded by three models from three different
labs on whether specialists already accept it and whether it traces to a known
thinker. The question is whether "contrarian" output is actually contrarian.

Headline: it mostly isn't. Requiring all three graders to agree, 348 of 849
answers are genuinely minority views, 45 of those are untraceable to anyone,
and 39 would cost a person anything to say out loud.

## Pipeline order

Each stage reads the previous stage's output from `data/raw/`. Run from `code/`.

```
generate.py          → generations.jsonl     (costs money; ~$4 for the pilot)
repair_truncated.py  → re-draws rows where reasoning ate the token budget
normalize.py         → normalized.jsonl      (one claim sentence per answer)
embed.py             → emb_*.npy             (costs money; two providers)
calibrate.py         → calibration.json      (picks the clustering threshold)
contrarian_audit.py  → audit.jsonl           (costs money; the three graders)
audit_analyze.py     → audit_results.json
analyze.py           → results.json          (diversity; needs emb_*.npy)
make_reports.py      → both HTML pages from their templates
make_chart_images.py → docs/img/*.png, screenshotted out of the built report
make_readme_tables.py→ the README's generated tables
export_release.py    → the two public CSVs
make_repo.sh         → assembles this repository
```

Nothing between `analyze.py` and what a reader sees is hand-edited. If a number
in the README or either report disagrees with the data, that is a bug, not a
stale edit.

## Decisions that are easy to get wrong

**Token budget.** `MAX_TOKENS = 1200` with `reasoning.effort = "low"`. Reasoning
tokens come out of the completion budget, so at 500 the reasoning models
returned raw reasoning and no answer. `reasoning.enabled = false` is not a
workaround — Gemini and Grok reject it and Qwen returns empty.

**Judges truncate their own JSON.** Twice, at two different stages. At
temperature 0 every retry fails identically, so a retry loop does not help and
the failures correlate with the grader. Raise the cap and re-run only the
failures.

**Hill numbers are sample-size dependent.** Comparing them at unequal n is
wrong; `hill_at_n()` rarefies first. This changed a result once it was fixed.

**Clustering.** HDBSCAN produced 428 mostly-singleton clusters and drove JSD to
0.93. Replaced with agglomerative clustering at an empirically calibrated
cosine threshold — see `calibrate.py`.

**Never colour a chart by something derived from an axis.** An earlier scatter
coloured points by a grade computed from the y-axis, so colour just restated
height. That chart has since been removed entirely.

**Dark mode inverts the sequential ramp.** A caption saying "darker is more X"
is only true in one theme. Say it without naming a direction.

**CSS beats SVG presentation attributes.** `.tick { fill: … }` silently
overrode a `fill` attribute and killed the white-on-dark branch in the heatmap
for months. Use an inline `style` when a fill must vary per element.

**P3 is flawed.** *"Tell me something top experts would say is wrong"* invites
a model to name a known falsehood rather than assert a belief, and several did
("The Earth is flat"). Those score 0% specialist agreement and are not
heresies. P3 counts in the aggregates but is excluded from the ranked table in
the README. Fixing the wording is the first change a follow-up should make.

**Prompt codes were renumbered** after the temperature arms were dropped.
`config.published_condition()` and `config.published_id()` are the only places
that mapping lives. The internal names survive in `data/raw/` and in the
`raw_id` column of both CSVs.

## Still open

- The OpenRouter key is not in this repository and should be re-issued. Put it
  in a gitignored `.env` as `OPENROUTER_API_KEY`.
- The embedding matrices (`emb_closed.npy`, `emb_open.npy`) are not committed —
  17 MB of float32 that GitHub does not need. `embed.py` regenerates them from
  `data/raw/embed_index.jsonl` for a few cents. Embedding endpoints drift, so a
  regenerated matrix reproduces `results.json` closely but not bit-exactly. The
  graded findings in `audit_results.json` do not depend on them at all.
- `CITATION.cff` lists a GitHub alias rather than a real name.
- The temperature sweep was run and dropped for being underpowered. Its rows
  are still in `data/raw/generations.jsonl` if anyone wants to power it
  properly.
- This is a pilot: ~10 answers per model per prompt. Every between-model
  comparison is underpowered on its own.
