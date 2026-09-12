from pathlib import Path
import unittest


class SettingsColorTests(unittest.TestCase):
    def test_provider_dots_are_bright_and_session_actions_have_expected_colors(self):
        css = (Path(__file__).resolve().parents[1] / 'static' / 'settings-session-polish.css').read_text(encoding='utf-8')
        self.assertIn('#43e7a2', css)
        self.assertIn('#ff727a', css)
        self.assertIn('background:#f04f5b', css)
        self.assertIn('background:#2f7fe6!important', css)


if __name__ == '__main__':
    unittest.main()
