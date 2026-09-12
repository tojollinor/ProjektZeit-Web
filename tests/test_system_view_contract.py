from pathlib import Path
import unittest


class SystemViewContractTests(unittest.TestCase):
    def test_settings_and_system_views_are_classified_as_system_pages(self):
        js = (Path(__file__).resolve().parents[1] / 'static' / 'settings-session-polish.js').read_text(encoding='utf-8')
        for token in ("name==='admin-options'", "name==='logs'", "name.startsWith('settings-')", "name.startsWith('workshop-')"):
            self.assertIn(token, js)
        self.assertIn("document.documentElement.classList.toggle('pz-system-view',system)", js)


if __name__ == '__main__':
    unittest.main()
