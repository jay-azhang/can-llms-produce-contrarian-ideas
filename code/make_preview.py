"""Render an inspectable preview of the assembled release repository.

The repo is built in a sandbox and pushed from elsewhere, so there is a gap
where nobody can see what is about to become public. This renders that: the
file tree, the README as it will appear on GitHub, a sample of the dataset, and
the commands to push it.

Usage:
    python make_preview.py <repo-dir> <github-url> [out.html]
"""

from __future__ import annotations

import csv
import html
import re
import subprocess
import sys
from pathlib import Path


def md(text: str) -> str:
    """Minimal Markdown -> HTML for the subset the README actually uses.

    A full parser is overkill here and a dependency; this covers headings,
    tables, fenced code, lists, bold, inline code and links, which is the whole
    vocabulary of the file being previewed.
    """
    out, lines, i = [], text.split("\n"), 0

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        s = s.replace("&amp;rarr;", "&rarr;").replace("&amp;nbsp;", "&nbsp;")
        s = s.replace("&amp;middot;", "&middot;").replace("·", "&middot;")
        return s

    while i < len(lines):
        ln = lines[i]
        if ln.lstrip().startswith("<!--"):
            # A marker comment is a single line, not the start of an HTML block.
            # Treating it as a block swallowed the generated table that follows
            # it, because there is no blank line in between.
            pass
        elif ln.lstrip().startswith("<"):
            # Raw HTML block (the README's <picture> figures). Markdown allows
            # it and GitHub renders it, so pass it through to the blank line.
            blk = []
            while i < len(lines) and lines[i].strip():
                blk.append(lines[i])
                i += 1
            out.append("\n".join(blk))
        elif ln.strip() in ("---", "***", "___"):
            out.append("<hr>")
        elif ln.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(html.escape(lines[i]))
                i += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            i -= 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            # A separator row must actually contain dashes — an empty
            # header row ("| | |") is all-empty cells and would otherwise be
            # mistaken for one, promoting the first data row into the header.
            def _is_sep(row):
                return any("-" in c for c in row) and \
                    all(set(c) <= set("-: ") for c in row)
            body = [r for r in cells if not _is_sep(r)]
            if body:
                head, rest = body[0], body[1:]
                # Wrapped: README tables carry long prose cells and would
                # otherwise push the whole page sideways.
                out.append('<div class="tscroll"><table><thead><tr>'
                           + "".join(f"<th>{inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>"
                           + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r)
                                     + "</tr>" for r in rest)
                           + "</tbody></table></div>")
        elif ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  ")):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:])
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            i -= 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and \
                    not lines[i + 1][0] in "|-#`":
                i += 1
                para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} MB"


def main() -> None:
    repo = Path(sys.argv[1])
    url = sys.argv[2]
    out = Path(sys.argv[3] if len(sys.argv) > 3 else repo.parent / "preview.html")
    name = repo.name

    files = sorted(p for p in repo.rglob("*")
                   if p.is_file() and ".git/" not in str(p.relative_to(repo)))
    tree = []
    for p in files:
        rel = p.relative_to(repo)
        tree.append((str(rel), p.stat().st_size))
    total = sum(s for _, s in tree)

    readme_html = md((repo / "README.md").read_text())

    # The preview ships as a single self-contained page, so every image the
    # README references is embedded rather than linked.
    import base64
    def _inline(m):
        rel = m.group(2)
        f = repo / rel
        if not f.exists():
            return m.group(0)
        b64 = base64.b64encode(f.read_bytes()).decode()
        return f'{m.group(1)}="data:image/png;base64,{b64}"'
    readme_html = re.sub(r'(srcset|src)="([^"]+\.png)"', _inline, readme_html)

    with open(repo / "data" / "qa_pairs.csv") as f:
        rdr = csv.DictReader(f)
        cols = rdr.fieldnames or []
        sample = [next(rdr) for _ in range(6)]

    try:
        log = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-1"],
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        log = ""

    show = ["model", "prompt_id", "model_answer_verbatim", "answer_one_sentence",
            "pct_specialists_who_would_agree", "pct_public_who_would_agree",
            "grade", "traceable_to"]

    rows_html = "".join(
        "<tr>" + "".join(
            f'<td class="{"num" if c.startswith("pct_") else ""}">'
            + html.escape((r.get(c) or "")[:190] + ("…" if len(r.get(c) or "") > 190 else ""))
            + "</td>" for c in show) + "</tr>"
        for r in sample)

    tree_html = "".join(
        f'<tr><td class="mono">{html.escape(p)}</td>'
        f'<td class="num mono">{human(s)}</td></tr>' for p, s in tree)

    doc = f"""<title>Release Preview</title>
<style>
:root{{color-scheme:light;--ground:#fbfbfc;--panel:#fff;--panel-2:#f4f5f8;--line:#e2e4ea;
 --line-strong:#c9ccd6;--ink:#10131a;--ink-2:#3d4354;--ink-3:#6b7186;--accent:#2a78d6;
 --pos:#1baf7a;--warn:#eda100;--shadow:0 1px 2px rgba(16,19,26,.05),0 4px 16px rgba(16,19,26,.05);}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;
 --ground:#14161b;--panel:#1b1e25;--panel-2:#22262e;--line:#2c313b;--line-strong:#3d4350;
 --ink:#f2f3f6;--ink-2:#b9bfcd;--ink-3:#868da0;--accent:#3987e5;--pos:#199e70;--warn:#c98500;
 --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 16px rgba(0,0,0,.3);}}}}
:root[data-theme="dark"]{{color-scheme:dark;--ground:#14161b;--panel:#1b1e25;--panel-2:#22262e;
 --line:#2c313b;--line-strong:#3d4350;--ink:#f2f3f6;--ink-2:#b9bfcd;--ink-3:#868da0;
 --accent:#3987e5;--pos:#199e70;--warn:#c98500;
 --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 16px rgba(0,0,0,.3);}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-size:16px;line-height:1.62;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 28px}}
h1,h2,h3{{text-wrap:balance;margin:0}}
h1{{font-size:clamp(1.9rem,4vw,2.9rem);line-height:1.1;letter-spacing:-.02em;font-weight:600;
 font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}}
h2{{font-size:1.45rem;letter-spacing:-.01em;font-weight:600}}
p{{margin:0}}
a{{color:var(--accent)}}
header{{border-bottom:1px solid var(--line);background:var(--panel);padding:44px 0 34px}}
.eyebrow{{font-size:.68rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--ink-3)}}
.status{{display:inline-flex;align-items:center;gap:8px;font-size:.78rem;font-weight:650;
 color:var(--warn);border:1px solid var(--warn);border-radius:99px;padding:4px 12px;margin-top:6px}}
.status::before{{content:"";width:7px;height:7px;border-radius:50%;background:var(--warn)}}
section{{padding:44px 0;border-bottom:1px solid var(--line)}}
.shead{{display:flex;flex-direction:column;gap:9px;margin-bottom:22px}}
.role{{font-size:.68rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--accent)}}
.shead p{{color:var(--ink-2);font-size:.93rem;max-width:72ch}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:22px;box-shadow:var(--shadow)}}
.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.83rem}}
th,td{{text-align:left;padding:8px 11px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:.64rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
 white-space:nowrap;border-bottom:1px solid var(--line-strong)}}
td.num,th.num{{text-align:right;font-family:ui-monospace,Menlo,monospace}}
tbody tr:hover{{background:var(--panel-2)}}
pre{{margin:0;background:var(--panel-2);border:1px solid var(--line);border-radius:3px;
 padding:14px 16px;overflow-x:auto;font-family:ui-monospace,Menlo,Consolas,monospace;
 font-size:.82rem;line-height:1.6;color:var(--ink-2)}}
code{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.9em;background:var(--panel-2);
 padding:1px 5px;border-radius:2px}}
pre code{{background:none;padding:0}}
.readme{{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:30px 34px;
 box-shadow:var(--shadow)}}
.readme h1{{font-size:1.9rem;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--line)}}
.readme h2{{font-size:1.3rem;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.readme p{{margin:12px 0;color:var(--ink-2)}}
.readme ul{{color:var(--ink-2);padding-left:22px}}
.readme li{{margin:6px 0}}
.tscroll{{overflow-x:auto;max-width:100%}}
.readme img{{max-width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:3px}}
.readme table{{margin:14px 0}}
.readme th{{white-space:normal}}
.readme th:empty{{padding:0;border:none}}
.readme hr{{border:none;border-top:1px solid var(--line);margin:26px 0}}
.readme pre{{margin:14px 0}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px}}
.tile{{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:15px 17px;
 display:flex;flex-direction:column;gap:4px}}
.tile .k{{font-size:.67rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3)}}
.tile .v{{font-size:1.6rem;font-weight:600;line-height:1.05;letter-spacing:-.02em}}
.note{{font-size:.8rem;color:var(--ink-3);line-height:1.55;margin-top:12px;max-width:80ch}}
.warn{{border-left:3px solid var(--warn)}}
footer{{padding:40px 0 56px;color:var(--ink-3);font-size:.8rem}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
</style>

<header><div class="wrap">
  <div class="eyebrow">Release preview &middot; not yet pushed</div>
  <h1>{html.escape(name)}</h1>
  <div class="status">Built and committed locally &mdash; awaiting your push</div>
  <p style="color:var(--ink-2);margin-top:14px;max-width:62ch">Everything that will become
    public at <a href="{html.escape(url)}">{html.escape(url.replace('https://',''))}</a>,
    exactly as assembled. Nothing has been uploaded.</p>
</div></header>

<div class="wrap">

<section>
  <div class="shead"><span class="role">Push it</span><h2>Three commands</h2>
  <p>The tarball contains a git repository with the commit already made, so this is a remote
     add and a push. Then enable Pages.</p></div>
  <pre><code>tar xzf {html.escape(name)}.tar.gz
cd {html.escape(name)}
git remote add origin {html.escape(url)}.git
git push -u origin main</code></pre>
  <p class="note">Then <strong>Settings &rarr; Pages &rarr; Source: main branch, /docs folder</strong>.
    The site appears at <span class="mono">jaynewcompute.github.io/{html.escape(name)}/</span>
    within a minute or two.</p>
  <div class="tiles" style="margin-top:20px">
    <div class="tile"><span class="k">Files</span><span class="v mono">{len(tree)}</span></div>
    <div class="tile"><span class="k">Total size</span><span class="v mono">{human(total)}</span></div>
    <div class="tile"><span class="k">Commits</span><span class="v mono">1</span></div>
    <div class="tile"><span class="k">Answers</span><span class="v mono">1,071</span></div>
    <div class="tile"><span class="k">Grader verdicts</span><span class="v mono">3,192</span></div>
  </div>
  <p class="note mono" style="margin-top:14px">{html.escape(log)}</p>
</section>

<section>
  <div class="shead"><span class="role">Contents</span><h2>Every file</h2>
  <p>No monorepo history &mdash; a single fresh commit, so nothing internal travels with it.</p></div>
  <div class="panel scroll">
    <table><thead><tr><th>Path</th><th class="num">Size</th></tr></thead>
    <tbody>{tree_html}</tbody></table>
  </div>
</section>

<section>
  <div class="shead"><span class="role">The data</span><h2>First rows of qa_pairs.csv</h2>
  <p>{len(cols)} columns &times; 1,071 rows. Showing 6 rows and 8 of the columns; the raw answer
     is truncated here for width but is complete in the file.</p></div>
  <div class="panel scroll">
    <table><thead><tr>{"".join(f'<th class="{"num" if c.startswith("pct_") else ""}">{html.escape(c)}</th>' for c in show)}</tr></thead>
    <tbody>{rows_html}</tbody></table>
  </div>
  <p class="note"><strong>All {len(cols)} columns:</strong>
    <span class="mono">{html.escape(", ".join(cols))}</span></p>
</section>

<section>
  <div class="shead"><span class="role">Front page</span><h2>README, as GitHub will render it</h2></div>
  <div class="readme">{readme_html}</div>
</section>

<section class="panel warn" style="border-bottom:none;margin-bottom:40px">
  <h2 style="font-size:1.15rem">Two things to check before pushing</h2>
  <p style="color:var(--ink-2);font-size:.92rem;margin-top:10px">
    <strong>1. The content note</strong> at the end of the README covers the socially costly
    claims in the dataset, almost all from one model. It frames them as a finding about the
    models rather than an endorsement. This will carry your name, not the company's.</p>
  <p style="color:var(--ink-2);font-size:.92rem;margin-top:10px">
    <strong>2. CITATION.cff</strong> lists you only as <span class="mono">alias:
    jaynewcompute</span>. Worth adding your real name and any co-authors before a citation
    exists in the wild.</p>
</section>
</div>

<footer class="wrap">Preview generated from the assembled repository. Nothing here is live.</footer>
"""
    out.write_text(doc)
    print(f"{out}  ({out.stat().st_size/1024:.0f} KB, {len(tree)} files listed)")


if __name__ == "__main__":
    main()
