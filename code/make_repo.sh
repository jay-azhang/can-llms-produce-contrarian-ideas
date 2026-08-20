#!/usr/bin/env bash
#
# Assemble the standalone public repository from this experiment directory.
#
# The experiment lives inside a private monorepo; the public release is a fresh
# repo with no shared history, so nothing internal leaks through `git log`.
#
# Usage:
#   ./make_repo.sh <github-username> [repo-name] [output-dir]
#
# Then:
#   cd <output-dir> && git init && git add -A && git commit -m "..."
#   gh repo create <username>/<repo> --public --source=. --push
#   # finally: Settings > Pages > Source: main branch, /docs folder
set -euo pipefail

USER_NAME="${1:?usage: ./make_repo.sh <github-username> [repo-name] [output-dir]}"
REPO_NAME="${2:-borrowed-heresies}"
# Display title, derived from the repo name unless overridden by $TITLE.
TITLE="${TITLE:-$(printf '%s' "$REPO_NAME" | tr '-' ' ' | sed -E 's/(^| )([a-z])/\1\U\2/g')}"
OUT="${3:-/tmp/${REPO_NAME}}"
REPO_URL="https://github.com/${USER_NAME}/${REPO_NAME}"
# Avoid "Title?: subtitle" when the title is already a question.
case "$TITLE" in
  *\?) CITATION_TITLE="$TITLE" ;;
  *)   CITATION_TITLE="${TITLE}: are AI models' contrarian opinions actually contrarian?" ;;
esac

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REL="${SRC}/release"

if [ ! -d "$REL" ]; then
    echo "error: ${REL} not found — run: python3 export_release.py" >&2
    exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"/{docs,data,code}

# --- data + code ---------------------------------------------------------- #
cp "$REL"/data/qa_pairs.csv "$REL"/data/qa_pairs.jsonl "$REL"/data/judge_scores.csv "$OUT/data/"
cp "$REL"/code/*.py "$OUT/code/"

# Report sources and release tooling. Without these the repo can reproduce the
# numbers but not rebuild the pages or the README figures from them, which is
# half of what makes it re-runnable.
cp "$SRC"/audit_template.html "$SRC"/report_template.html "$OUT/code/"
cp "$SRC"/make_reports.py "$SRC"/make_chart_images.py "$SRC"/make_readme_tables.py \
   "$SRC"/make_preview.py "$SRC"/make_repo.sh "$OUT/code/"

# Every intermediate the pipeline produced. qa_pairs.csv is the friendly view;
# these are what the analysis actually read, so a sceptic can re-run any single
# stage without paying for generation again.
mkdir -p "$OUT/data/raw"
for f in generations.jsonl normalized.jsonl audit.jsonl audit_results.json \
         results.json calibration.json validation_report.json \
         validation_judge2.jsonl embed_index.jsonl handcheck_sheet.jsonl \
         condition_prompts.json report_payload.json; do
    [ -f "$SRC/data/$f" ] && cp "$SRC/data/$f" "$OUT/data/raw/"
done
cp "$REL"/README.md "$REL"/DATA_DICTIONARY.md "$OUT/"

# Handoff notes: what the pipeline does and which decisions are load-bearing.
# Picked up automatically by a Claude Code session opened on this repo.
cp "$SRC"/CLAUDE.md "$OUT/"


# Static chart images for the README: GitHub renders Markdown without
# JavaScript, so the interactive SVG charts are invisible there. These are
# screenshotted straight out of the built report by make_chart_images.py, in a
# light and a dark variant each.
mkdir -p "$OUT/docs/img"
cp "$REL"/docs_img/*.png "$OUT/docs/img/"

# --- reports become the GitHub Pages site --------------------------------- #
# The audit report is the landing page: it is the one that answers the question
# a visitor arrives with. The diversity report sits behind it.
cp "$REL"/audit_report.html "$OUT/docs/index.html"
cp "$REL"/report.html "$OUT/docs/diversity.html"

# Both pages carry a __REPO_URL__ placeholder in their footer so the published
# HTML links back to the data rather than mentioning it.
for f in "$OUT"/docs/*.html; do
    python3 - "$f" "$REPO_URL" <<'PY'
import sys, pathlib
p, url = pathlib.Path(sys.argv[1]), sys.argv[2]
p.write_text(p.read_text().replace("__REPO_URL__", url))
PY
done

# GitHub Pages runs Jekyll by default, which ignores files it does not
# understand and can mangle others. These are plain static pages.
touch "$OUT/docs/.nojekyll"

# --- licences: code and data differ --------------------------------------- #
YEAR=2026
cat > "$OUT/LICENSE" <<EOF
MIT License

Copyright (c) ${YEAR} ${USER_NAME}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

cat > "$OUT/data/LICENSE" <<EOF
The dataset in this directory is released under the Creative Commons
Attribution 4.0 International licence (CC BY 4.0).

https://creativecommons.org/licenses/by/4.0/

You may share and adapt it for any purpose, including commercially, provided
you give appropriate credit and indicate if changes were made.

The code in ../code is separately licensed under MIT; see ../LICENSE.

Note on provenance: this data records outputs produced by third-party language
models via the OpenRouter API. The text of the model responses is machine
generated. Attribution applies to the dataset — its construction, grading and
documentation — not to the underlying model outputs.
EOF

cat > "$OUT/CITATION.cff" <<EOF
cff-version: 1.2.0
title: "${CITATION_TITLE}"
message: "If you use this dataset, please cite it."
type: dataset
authors:
  - alias: ${USER_NAME}
repository-code: "${REPO_URL}"
url: "https://${USER_NAME}.github.io/${REPO_NAME}/"
abstract: >-
  855 responses from nine frontier language models across eight labs, asked
  for their most heretical beliefs under seven prompt framings, each graded by
  three independent models on whether specialists already agree with the claim
  and whether it traces to a known thinker.
keywords:
  - large language models
  - output diversity
  - model homogeneity
  - evaluation
license: CC-BY-4.0
date-released: "${YEAR}-08-18"
EOF

cat > "$OUT/.gitignore" <<'EOF'
__pycache__/
*.pyc
.venv/
.env
*.npy
.DS_Store
EOF

# --- point the README at the live site ------------------------------------ #
python3 - "$OUT/README.md" "$REPO_URL" "https://${USER_NAME}.github.io/${REPO_NAME}/" "$TITLE" <<'PY'
import sys, pathlib
p, repo, site, title = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
t = p.read_text()
# H1 tracks the repo name so the page, the repo and the citation agree.
t = t.replace("# The Consensus of Contrarians", f"# {title}", 1)
banner = f"""
**[Read the findings &rarr;]({site})** &nbsp;·&nbsp;
[All 855 questions and answers (CSV)]({repo}/blob/main/data/qa_pairs.csv) &nbsp;·&nbsp;
[Data dictionary]({repo}/blob/main/DATA_DICTIONARY.md)
"""
# Slot the banner in after the opening bold summary paragraph.
marker = "contrarian.**\n"
t = t.replace(marker, marker + banner, 1)
t = t.replace("`audit_report.html`", f"[`docs/index.html`]({site})")
t = t.replace("`report.html`", f"[`docs/diversity.html`]({site}diversity.html)")
p.write_text(t)
PY

echo "assembled ${REPO_NAME} at ${OUT}"
find "$OUT" -type f | sed "s|${OUT}/||" | sort | sed 's/^/  /'
echo
echo "size: $(du -sh "$OUT" | cut -f1)"
echo
echo "next:"
echo "  cd ${OUT}"
echo "  git init -b main && git add -A && git commit -m 'Borrowed Heresies: pilot release'"
echo "  gh repo create ${USER_NAME}/${REPO_NAME} --public --source=. --push"
echo "  then enable Pages: Settings > Pages > main branch, /docs folder"
