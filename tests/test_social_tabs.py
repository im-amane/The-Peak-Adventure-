"""Accessibility and structure checks for the Mini App social tabs."""
from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SocialTabParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = {}
        self.panels = {}
        self.ids = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids[element_id] = self.ids.get(element_id, 0) + 1
        if attributes.get("role") == "tab":
            self.tabs[attributes.get("data-social-tab")] = attributes
        if attributes.get("role") == "tabpanel":
            self.panels[attributes.get("data-social-panel")] = attributes


class SocialTabMarkupTests(unittest.TestCase):
    def test_social_tabs_have_linked_panels_and_one_initial_selection(self):
        parser = SocialTabParser()
        parser.feed((ROOT / "webapp" / "index.html").read_text(encoding="utf-8"))

        expected = {"friends", "party", "guild", "trading"}
        self.assertEqual(set(parser.tabs), expected)
        self.assertEqual(set(parser.panels), expected)

        selected = []
        visible = []
        for name in sorted(expected):
            tab = parser.tabs[name]
            panel = parser.panels[name]
            self.assertEqual(tab.get("aria-controls"), panel.get("id"))
            self.assertEqual(panel.get("aria-labelledby"), tab.get("id"))
            self.assertEqual(panel.get("data-social-panel"), name)
            if tab.get("aria-selected") == "true":
                selected.append(name)
            if "hidden" not in panel:
                visible.append(name)
        self.assertEqual(selected, ["friends"])
        self.assertEqual(visible, ["friends"])

    def test_social_tab_ids_are_unique_and_render_targets_exist(self):
        parser = SocialTabParser()
        parser.feed((ROOT / "webapp" / "index.html").read_text(encoding="utf-8"))
        required_ids = {
            "social-tabs",
            "social-overview",
            "social-friends-overview",
            "social-party-overview",
            "social-guild-overview",
            "social-trading-overview",
            "social-search-form",
            "party-create",
            "matchmaking-casual",
            "guild-chat-panel",
        }
        for element_id in required_ids:
            self.assertEqual(parser.ids.get(element_id), 1, element_id)

    def test_social_tabs_support_click_and_keyboard_navigation(self):
        source = (ROOT / "webapp" / "game.js").read_text(encoding="utf-8")
        self.assertIn('socialTabs.addEventListener("click"', source)
        self.assertIn('socialTabs.addEventListener("keydown"', source)
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            self.assertIn(key, source)
        for panel in ("friends", "party", "guild", "trading"):
            self.assertIn(f'document.getElementById("social-{panel}-overview")', source)


if __name__ == "__main__":
    unittest.main()
