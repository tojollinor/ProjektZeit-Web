import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TeamViewerDiagnosticsUiTest(unittest.TestCase):
    def test_connection_help_uses_current_teamviewer_path(self):
        js=(ROOT/'static'/'app.js').read_text(encoding='utf-8')
        self.assertIn('Einstellungen → Verbindungsprotokolle',js)
        self.assertIn('Berechtigungen &amp; Protokolle prüfen',js)
        self.assertIn('Verbindungen mit dem angemeldeten Firmenkonto starten',js)
        self.assertIn('Benutzer-, Gruppen- und Datumsfilter entfernen',js)
        self.assertIn('Zugehörigkeit zum bisherigen Unternehmensprofil prüfen',js)

    def test_ui_explains_api_boundary_and_replacement_token(self):
        js=(ROOT/'static'/'app.js').read_text(encoding='utf-8')
        self.assertIn('nicht Bestandteil der öffentlichen API',js)
        self.assertIn('Bestehende TeamViewer-Tokens lassen sich nicht erweitern',js)
        self.assertIn('Kontoinformationen',js)
        self.assertIn('Verbindungsberichte',js)


if __name__=='__main__':
    unittest.main()
