from pathlib import Path
import unittest


class ProfileSpacingContractTests(unittest.TestCase):
    def test_profile_panels_use_consistent_gap_and_legacy_avatar_panel_is_hidden(self):
        css = (Path(__file__).resolve().parents[1] / 'static' / 'settings-session-polish.css').read_text(encoding='utf-8')
        self.assertIn('.pz-profile-main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}', css)
        self.assertIn('[data-profile-image-panel]{display:none!important}', css)


if __name__ == '__main__':
    unittest.main()
