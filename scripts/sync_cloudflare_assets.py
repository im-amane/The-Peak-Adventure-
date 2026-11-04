#!/usr/bin/env python3
"""Refresh Cloudflare Worker fallback assets from the canonical Mini App files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "cloudflare" / "worker.mjs"
ASSETS = {
    "/": (ROOT / "webapp" / "index.html", "text/html; charset=utf-8"),
    "/style.css": (ROOT / "webapp" / "style.css", "text/css; charset=utf-8"),
    "/game.js": (ROOT / "webapp" / "game.js", "application/javascript; charset=utf-8"),
    "/pathfinding.js": (ROOT / "webapp" / "pathfinding.js", "application/javascript; charset=utf-8"),
    "/movement.js": (ROOT / "webapp" / "movement.js", "application/javascript; charset=utf-8"),
    "/character_profiles.js": (ROOT / "webapp" / "character_profiles.js", "application/javascript; charset=utf-8"),
    "/character_animation.js": (ROOT / "webapp" / "character_animation.js", "application/javascript; charset=utf-8"),
    "/monster_animation.js": (ROOT / "webapp" / "monster_animation.js", "application/javascript; charset=utf-8"),
    "/world_layout.js": (ROOT / "webapp" / "world_layout.js", "application/javascript; charset=utf-8"),
}
MARKER = "const STATIC_ASSETS = "
END_MARKER = "\n\nconst STATIC_PATHS"


def main() -> None:
    source = WORKER.read_text(encoding="utf-8")
    start = source.find(MARKER)
    if start < 0:
        raise SystemExit("Could not locate STATIC_ASSETS in cloudflare/worker.mjs")

    payload_start = start + len(MARKER)
    try:
        assets, consumed = json.JSONDecoder().raw_decode(source[payload_start:])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse STATIC_ASSETS JSON: {exc}") from exc
    suffix_start = payload_start + consumed
    if suffix_start < len(source) and source[suffix_start] == ";":
        suffix_start += 1

    expected = {
        route: {
            "body": path.read_text(encoding="utf-8"),
            "type": content_type,
        }
        for route, (path, content_type) in ASSETS.items()
    }
    drifted = [route for route, asset in expected.items() if assets.get(route) != asset]

    if "--check" in sys.argv[1:]:
        if drifted:
            raise SystemExit(
                "Cloudflare fallback assets are out of sync: "
                + ", ".join(drifted)
                + ". Run python scripts/sync_cloudflare_assets.py to update them."
            )
        print("Cloudflare fallback assets match webapp/.")
        return

    assets.update(expected)
    block = MARKER + json.dumps(assets, ensure_ascii=False, separators=(",", ":")) + ";"
    updated = source[:start] + block + source[suffix_start:]
    if updated != source:
        WORKER.write_text(updated, encoding="utf-8")
        print("Cloudflare fallback assets synchronized.")
    else:
        print("Cloudflare fallback assets already match webapp/.")


if __name__ == "__main__":
    main()
