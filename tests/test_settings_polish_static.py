from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SettingsPolishStaticTests(unittest.TestCase):
    def test_system_views_hide_work_panel_and_main_is_top_aligned(self):
        css = (ROOT / 'static' / 'settings-session-polish.css').read_text(encoding='utf-8')
        self.assertIn('.pz-system-view .work-panel', css)
        self.assertIn('main{margin:0 auto!important;align-self:start!important}', css)

    def test_connection_loader_has_bounded_local_path(self):
        js = (ROOT / 'static' / 'settings-session-polish.js').read_text(encoding='utf-8')
        self.assertIn("post('/api/v1/settings/connections',{})", js)
        self.assertIn("3000,'Verbindungen konnten nicht innerhalb von 3 Sekunden geladen werden.'", js)
        self.assertIn('data-pz-connections-retry', js)

    def test_profile_avatar_is_embedded_in_profile_panel(self):
        js = (ROOT / 'static' / 'settings-session-polish.js').read_text(encoding='utf-8')
        avatar = (ROOT / 'static' / 'profile-avatar.js').read_text(encoding='utf-8')
        self.assertIn('data-pz-profile-avatar-button', js)
        self.assertIn('Profilbild hochladen', avatar)
        self.assertIn('Profilbild löschen', avatar)
        self.assertNotIn("panel.dataset.profileImagePanel", avatar)


if __name__ == '__main__':
    unittest.main()
