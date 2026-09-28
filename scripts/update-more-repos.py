#!/usr/bin/env python3
"""Regenerate the profile README's Featured table and 'More repos' columns.

Featured table: 'What it is' is pulled from each repo's GitHub description
(API wins, curated fallback fills gaps); 'Stack' and demo links are curated
in FEATURED below. Only replaces content between <!-- FEATURED:START -->
and <!-- FEATURED:END -->.

More repos rules (per request):
- Max 10 repos per column, add columns as repo count grows, max 4 columns (40 shown).
- Anything past 40 gets a redirect link to the repos tab.
- Each cell: repo title hyperlink in <h4>, description in <p>.
- Keeps the <details> collapsible wrapper; only replaces content between
  <!-- MORE-REPOS:START --> and <!-- MORE-REPOS:END -->.

Usage:
    python3 scripts/update-more-repos.py [--check] [--readme PATH]

- Default README path: <repo-root>/README.md
- --check: exit 1 if README would change (for CI dry-run).
- Uses `gh` CLI (authenticated) to list repos; falls back to `gh api`.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

OWNER = "needlehmbl"
REPOS_TAB = f"https://github.com/{OWNER}?tab=repositories"

# Featured table config — display order, curated Stack column, optional demo
# link appended to the API description. Featured repos are never duplicated
# into "More repos".
FEATURED_ORDER = [
    "3d-portfolio",
    "job-scraper",
    "local-rag",
    "media-manager",
    "doc-pipeline",
    "kanban",
]
FEATURED_NAMES = set(FEATURED_ORDER)

FEATURED_STACK = {
    "3d-portfolio": "React, Three.js, GSAP, JavaScript",
    "job-scraper": "Python, Playwright, FastAPI, Postgres, React",
    "local-rag": "Python, Ollama, Postgres/pgvector, FastAPI",
    "media-manager": "Python, FastAPI, React, Docker Compose",
    "doc-pipeline": "Python, Ollama, SQLite",
    "kanban": "TypeScript, Express, Socket.io, Prisma, Postgres, React, Docker",
}

FEATURED_DEMO = {
    "3d-portfolio": " Live [here](https://needlehmbl.github.io/3d-portfolio/).",
    "kanban": " Live demo [here](https://needlehmbl.github.io/kanban-demo/).",
}

# Used only if a featured repo's GitHub description is empty (API wins).
FEATURED_FALLBACK = {
    "3d-portfolio": "Personal 3D portfolio with GSAP scroll animations — showcases everything below.",
    "job-scraper": "Metro Manila junior-dev job scraper (Indeed / LinkedIn / JobStreet) with Postgres + dashboard, feedback learning, per-posting resume tailoring.",
    "local-rag": "Fully-local RAG: chunk → embed via Ollama → pgvector search → cited answers. FastAPI + SSE streaming + demo UI.",
    "media-manager": "Self-hosted media download manager: parallel yt-dlp queue, playlist recursion, metadata embed, auto-resume, searchable library, channel checks.",
    "doc-pipeline": "Offline document intelligence: ingest PDFs/images/CSVs, extract structured data with Ollama, schema + confidence validation, load to SQLite.",
    "kanban": "Real-time multi-user kanban board with GitHub OAuth, drag-and-drop, live WebSocket updates.",
}

# Never listed (profile README repo itself).
EXCLUDE = {"needlehmbl"}

# Fallbacks for repos with an empty GitHub description.
# If the API description is non-empty it always wins; these only fill gaps
# so future auto-added repos still get a one-liner until you set a description.
FALLBACK_DESCRIPTIONS = {
    "glowpoint-dashboard": "Admin dashboard for Glow Point salon bookings (Next.js + TypeScript + Supabase): appointments, payments, calendar, analytics",
    "glowpoint-client": "Customer booking app for Glow Point salon (React + Vite + Supabase): service catalog, booking flow, GCash QR payments, live walk-in queue",
    "nasa-react-app": "NASA API React app",
    "go-go-ghost": "Godot / GDScript game",
    "TPWeb": "Web tech project (CSS)",
}

PER_COLUMN = 10
MAX_COLUMNS = 4
MAX_SHOWN = PER_COLUMN * MAX_COLUMNS

START_MARKER = "<!-- MORE-REPOS:START -->"
END_MARKER = "<!-- MORE-REPOS:END -->"
FEATURED_START = "<!-- FEATURED:START -->"
FEATURED_END = "<!-- FEATURED:END -->"


def fetch_repos() -> list[dict]:
    out = subprocess.run(
        [
            "gh",
            "repo",
            "list",
            OWNER,
            "--limit",
            "200",
            "--json",
            "name,description,url,isFork,isPrivate,isArchived",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout or "[]")


def pick_repos(all_repos: list[dict]) -> list[dict]:
    picked = []
    for r in all_repos:
        name = r.get("name", "")
        if name in FEATURED_NAMES or name in EXCLUDE:
            continue
        if r.get("isPrivate") or r.get("isFork") or r.get("isArchived"):
            continue
        desc = (r.get("description") or "").strip() or FALLBACK_DESCRIPTIONS.get(name, "No description yet.")
        picked.append({"name": name, "url": r.get("url") or f"https://github.com/{OWNER}/{name}", "description": desc})
    picked.sort(key=lambda r: r["name"].lower())
    return picked


def repo_block(repo: dict) -> str:
    name = html.escape(repo["name"])
    url = html.escape(repo["url"], quote=True)
    desc = html.escape(repo["description"])
    return f"<h4><a href=\"{url}\">{name}</a></h4>\n<p>{desc}</p>"


def build_featured_table(by_name: dict[str, dict]) -> str:
    lines = [FEATURED_START]
    lines.append("<!-- Auto-generated by scripts/update-more-repos.py — do not edit manually. 'What it is' comes from each repo's GitHub description. -->")
    lines.append("| Project | What it is | Stack |")
    lines.append("|---|---|---|")
    for name in FEATURED_ORDER:
        r = by_name.get(name, {})
        url = r.get("url") or f"https://github.com/{OWNER}/{name}"
        desc = (r.get("description") or "").strip() or FEATURED_FALLBACK.get(name, "No description yet.")
        desc = " ".join(desc.split())
        desc = desc.replace("|", "\\|")
        if name in FEATURED_DEMO and not desc.endswith((".", "!", "?", ":")):
            desc += "."
        desc += FEATURED_DEMO.get(name, "")
        stack = FEATURED_STACK.get(name, "")
        lines.append(f"| **[{name}]({url})** | {desc} | {stack} |")
    lines.append(FEATURED_END)
    return "\n".join(lines) + "\n"


def build_table(repos: list[dict]) -> str:
    shown = repos[:MAX_SHOWN]
    overflow = len(repos) - len(shown)
    # Chunk into columns of PER_COLUMN.
    columns = [shown[i : i + PER_COLUMN] for i in range(0, len(shown), PER_COLUMN)] or [[]]

    lines = [START_MARKER]
    lines.append("<!-- Auto-generated by scripts/update-more-repos.py — do not edit manually. Columns: max 10 repos each, up to 4 columns (40 repos max). Overflow links to the repos tab. -->")
    lines.append("<table>")
    lines.append("<tr>")
    for col in columns:
        lines.append('<td valign="top">')
        lines.append("")
        for repo in col:
            lines.append(repo_block(repo))
            lines.append("")
        lines.append("</td>")
    lines.append("</tr>")
    lines.append("</table>")
    if overflow > 0:
        lines.append("")
        lines.append(f'<p align="center">➡️ Showing {MAX_SHOWN} of {len(repos)} repos — <a href="{REPOS_TAB}">See all repositories</a></p>')
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def replace_block(text: str, start: str, end: str, new_block: str) -> str:
    if start not in text or end not in text:
        raise ValueError(f"Marker {start}...{end} not found")
    before, _, rest = text.partition(start)
    _, _, after = rest.partition(end)
    if end not in rest:
        raise ValueError(f"End marker {end} not found after {start}")
    # Normalize surrounding blank lines so repeated runs are idempotent.
    return before + new_block + "\n" + after.lstrip("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Exit 1 if README would change.")
    ap.add_argument("--readme", default=None, help="Path to README.md (default: repo-root/README.md).")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    readme = Path(args.readme) if args.readme else repo_root / "README.md"

    all_repos = fetch_repos()
    by_name = {r.get("name", ""): r for r in all_repos}
    repos = pick_repos(all_repos)

    text = readme.read_text(encoding="utf-8")
    for marker in (FEATURED_START, FEATURED_END, START_MARKER, END_MARKER):
        if marker not in text:
            print(f"Marker {marker} not found in {readme}", file=sys.stderr)
            return 2
    updated = replace_block(text, FEATURED_START, FEATURED_END, build_featured_table(by_name))
    updated = replace_block(updated, START_MARKER, END_MARKER, build_table(repos))

    if updated == text:
        print(f"No change ({len(FEATURED_ORDER)} featured, {len(repos)} more repos).")
        return 0
    if args.check:
        print(f"Would update featured table and/or more repos ({len(repos)} more repos).")
        return 1
    readme.write_text(updated, encoding="utf-8")
    print(f"Updated {readme}: {len(FEATURED_ORDER)} featured, {len(repos)} more repos ({min(len(repos), MAX_SHOWN)} shown).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
