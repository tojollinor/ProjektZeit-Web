from pathlib import Path
import unittest


class DashboardIconContractTests(unittest.TestCase):
    def test_dashboard_icon_uses_three_part_layout(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / 'static' / 'settings-session-polish.js').read_text(encoding='utf-8')
        css = (root / 'static' / 'settings-session-polish.css').read_text(encoding='utf-8')
        self.assertIn("pz-dashboard-glyph';dash.innerHTML='<i></i><i></i><i></i>'", js)
        self.assertIn('.pz-dashboard-glyph i:first-child{grid-row:1/3}', css)
        self.assertIn('.pz-settings-gear svg', css)


if __name__ == '__main__':
    unittest.main()
