"""Render the report's charts as static images for the README.

GitHub renders Markdown without JavaScript, so the interactive SVG charts in the
reports are invisible there. A repository whose front page is a wall of prose
undersells work whose whole point is what the pictures show.

This screenshots a chosen few charts straight out of the built report — so the
images can never drift from the analysis, because they ARE the analysis — and
writes a light and a dark variant of each. The README pairs them with
`<picture>` so GitHub serves the right one for the reader's theme.

Selectors can span several elements (a chart plus its legend); the capture is
the union of their bounding boxes.

Usage:
    python make_chart_images.py <report.html> <out-dir>
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

# (slug, [selectors to union], extra padding px)
FIGURES = [
    ("model-vs-prompt", ["#c-heat"], 14),
    ("grades", ["#c-tiergroup"], 16),
    ("who-said-it-first", ["#c-sources"], 14),
]

BOX_JS = """(sels) => {
  let box = null;
  for (const s of sels) {
    const el = document.querySelector(s);
    if (!el) continue;
    const r = el.getBoundingClientRect();
    const b = {x: r.left + scrollX, y: r.top + scrollY, r: r.right + scrollX,
               b: r.bottom + scrollY};
    box = box ? {x: Math.min(box.x, b.x), y: Math.min(box.y, b.y),
                 r: Math.max(box.r, b.r), b: Math.max(box.b, b.b)} : b;
  }
  return box;
}"""


def main() -> None:
    report = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # The report is written as an artifact fragment (no <html>/<head>); wrap it
    # so a real browser lays it out the same way the artifact host would.
    tmp = out / "_render.html"
    tmp.write_text("<!doctype html><html><head><meta charset='utf-8'>"
                   + report.read_text() + "</html>")

    made = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1400, "height": 1000},
                                    color_scheme=theme,
                                    device_scale_factor=2)
            page.goto(tmp.as_uri())
            page.wait_for_timeout(2000)          # charts build on load
            for slug, sels, pad in FIGURES:
                box = page.evaluate(BOX_JS, sels)
                if not box:
                    print(f"  !! {slug}: no element matched {sels}")
                    continue
                clip = {"x": max(box["x"] - pad, 0), "y": max(box["y"] - pad, 0),
                        "width": box["r"] - box["x"] + pad * 2,
                        "height": box["b"] - box["y"] + pad * 2}
                path = out / f"{slug}-{theme}.png"
                # clip coords are page-absolute, so the capture must be
                # full-page or anything below the fold falls outside it.
                page.screenshot(path=str(path), clip=clip, full_page=True)
                made.append((path, clip))
            page.close()
        browser.close()
    tmp.unlink()

    for path, clip in made:
        kb = path.stat().st_size / 1024
        print(f"  {path.name:<32} {clip['width']:.0f}x{clip['height']:.0f}  {kb:.0f} KB")
    print(f"{len(made)} images -> {out}")


if __name__ == "__main__":
    main()
