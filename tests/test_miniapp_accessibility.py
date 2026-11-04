import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "webapp" / "style.css").read_text(encoding="utf-8")


class MiniAppAccessibilityAuditTests(unittest.TestCase):
    def test_document_declares_language_viewport_and_main_landmark(self):
        self.assertRegex(HTML, r"<html[^>]+lang=[\"']en[\"']")
        self.assertRegex(HTML, r'<meta[^>]+name="viewport"[^>]+width=device-width')
        self.assertRegex(HTML, r"<main\b")

    def test_primary_sections_have_accessible_names(self):
        sections = re.findall(r"<section\b([^>]*)>", HTML)
        self.assertTrue(sections)
        named = [attrs for attrs in sections if "aria-labelledby=" in attrs or "aria-label=" in attrs]
        self.assertGreaterEqual(len(named), 10)

    def test_social_tabs_expose_tab_and_panel_relationships(self):
        self.assertRegex(HTML, r'role="tablist"')
        self.assertRegex(HTML, r'role="tab"')
        self.assertRegex(HTML, r'role="tabpanel"')
        self.assertIn("aria-selected=", HTML)
        self.assertIn("aria-labelledby=", HTML)

    def test_keyboard_focus_has_a_visible_indicator(self):
        self.assertRegex(CSS, r":focus-visible\s*\{")
        self.assertRegex(CSS, r"outline:\s*(?!none)")

    def test_small_screens_and_touch_targets_are_supported(self):
        self.assertRegex(CSS, r"@media\s*\(max-width:")
        self.assertRegex(CSS, r"min-height:\s*44px")
        self.assertIn("viewport-fit=cover", HTML)

    def test_motion_and_forced_color_preferences_are_respected(self):
        self.assertIn("prefers-reduced-motion:reduce", CSS)
        self.assertIn("forced-colors:active", CSS)


if __name__ == "__main__":
    unittest.main()
