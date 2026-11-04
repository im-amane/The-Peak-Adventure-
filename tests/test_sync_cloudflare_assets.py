import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_cloudflare_assets


class CloudflareAssetSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.worker = root / "worker.mjs"
        self.asset = root / "game.js"
        self.asset.write_text("current game bundle", encoding="utf-8")
        self.worker.write_text(
            'const STATIC_ASSETS = {"/game.js":{"body":"stale bundle","type":"application/javascript"}}'
            "\n\nconst STATIC_PATHS = new Set([]);\n",
            encoding="utf-8",
        )
        self.patches = [
            patch.object(sync_cloudflare_assets, "WORKER", self.worker),
            patch.object(
                sync_cloudflare_assets,
                "ASSETS",
                {"/game.js": (self.asset, "application/javascript")},
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_check_mode_accepts_matching_embedded_assets(self):
        self.asset.write_text("current game bundle", encoding="utf-8")
        payload = {"/game.js": {"body": "current game bundle", "type": "application/javascript"}}
        self.worker.write_text(
            "const STATIC_ASSETS = " + json.dumps(payload)
            + "\n\nconst STATIC_PATHS = new Set([]);\n",
            encoding="utf-8",
        )
        before = self.worker.read_text(encoding="utf-8")
        with patch("sys.argv", ["sync_cloudflare_assets.py", "--check"]):
            sync_cloudflare_assets.main()
        self.assertEqual(before, self.worker.read_text(encoding="utf-8"))

    def test_check_mode_fails_without_modifying_stale_worker(self):
        before = self.worker.read_text(encoding="utf-8")
        with patch("sys.argv", ["sync_cloudflare_assets.py", "--check"]):
            with self.assertRaises(SystemExit):
                sync_cloudflare_assets.main()
        self.assertEqual(before, self.worker.read_text(encoding="utf-8"))

    def test_sync_mode_updates_embedded_asset(self):
        with patch("sys.argv", ["sync_cloudflare_assets.py"]):
            sync_cloudflare_assets.main()
        source = self.worker.read_text(encoding="utf-8")
        start = source.index("const STATIC_ASSETS = ") + len("const STATIC_ASSETS = ")
        assets, consumed = json.JSONDecoder().raw_decode(source[start:])
        self.assertEqual(assets["/game.js"]["body"], "current game bundle")
        self.assertEqual(source[start + consumed], ";")

    def test_check_mode_accepts_security_headers_between_assets_and_paths(self):
        payload = {"/game.js": {"body": "current game bundle", "type": "application/javascript"}}
        self.worker.write_text(
            "const STATIC_ASSETS = " + json.dumps(payload)
            + ";\n\nconst STATIC_SECURITY_HEADERS = {};\n\nconst STATIC_PATHS = new Set([]);\n",
            encoding="utf-8",
        )
        with patch("sys.argv", ["sync_cloudflare_assets.py", "--check"]):
            sync_cloudflare_assets.main()

    def test_cloudflare_static_headers_cover_all_assets_without_worker_invocation(self):
        headers_path = sync_cloudflare_assets.ROOT / "webapp" / "_headers"
        headers = headers_path.read_text(encoding="utf-8")
        self.assertTrue(headers.startswith("/*\n"))
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("Referrer-Policy: strict-origin-when-cross-origin", headers)
        self.assertIn("X-Content-Type-Options: nosniff", headers)

        config_path = sync_cloudflare_assets.ROOT / "wrangler.jsonc"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        worker_first = set(config["assets"]["run_worker_first"])
        static_routes = set(sync_cloudflare_assets.ASSETS)
        self.assertFalse(
            static_routes & worker_first,
            "Static assets should remain edge-served rather than invoke the Worker.",
        )


if __name__ == "__main__":
    unittest.main()
