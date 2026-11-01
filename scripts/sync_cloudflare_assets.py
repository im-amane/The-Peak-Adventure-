#!/usr/bin/env python3
"""Refresh Cloudflare Worker fallback assets from the canonical Mini App files."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "cloudflare" / "worker.mjs"
ASSETS = {
    "/": (ROOT / "webapp" / "index.html", "text/html; charset=utf-8"),
    "/style.css": (ROOT / "webapp" / "style.css", "text/css; charset=utf-8"),
    "/game.js": (ROOT / "webapp" / "game.js", "application/javascript; charset=utf-8"),
}
MARKER = "const STATIC_ASSETS = "
END_MARKER = "\n\nconst STATIC_PATHS"


def main() -> None:
    source = WORKER.read_text(encoding="utf-8")
    start = source.find(MARKER)
    end = source.find(END_MARKER, start)
    if start < 0 or end < 0:
        raise SystemExit("Could not locate STATIC_ASSETS in cloudflare/worker.mjs")

    raw = source[start + len(MARKER):end].strip()
    if raw.endswith(";"):
        raw = raw[:-1]
    assets = json.loads(raw)

    for route, (path, content_type) in ASSETS.items():
        if route not in assets:
            raise SystemExit(f"Missing embedded fallback route: {route}")
        assets[route]["body"] = path.read_text(encoding="utf-8")
        assets[route]["type"] = content_type

    block = MARKER + json.dumps(assets, ensure_ascii=False, separators=(",", ":"))
    updated = source[:start] + block + source[end:]
    if updated != source:
        WORKER.write_text(updated, encoding="utf-8")
        print("Cloudflare fallback assets synchronized.")
    else:
        print("Cloudflare fallback assets already match webapp/.")


if __name__ == "__main__":
    main()
