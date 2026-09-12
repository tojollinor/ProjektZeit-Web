import tempfile
import unittest
from pathlib import Path

import frontend_update_runtime


class FrontendUpdateTests(unittest.TestCase):
    def test_fingerprint_changes_with_ui_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<html><head></head><body></body></html>', encoding='utf-8')
            (root / 'app.js').write_text('console.log(1)', encoding='utf-8')
            first = frontend_update_runtime._frontend_version(root)
            (root / 'app.js').write_text('console.log(2)', encoding='utf-8')
            second = frontend_update_runtime._frontend_version(root)
            self.assertNotEqual(first, second)

    def test_index_gets_version_meta_update_assets_and_cache_busters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text(
                '<html><head><link rel="stylesheet" href="/app.css?v=1"></head>'
                '<body><script src="/app.js?v=1" defer></script></body></html>',
                encoding='utf-8',
            )
            html = frontend_update_runtime._versioned_index(root, 'abc123')
            self.assertIn('name="pz-frontend-version" content="abc123"', html)
            self.assertIn('/frontend-update.css?pzv=abc123', html)
            self.assertIn('/frontend-update.js?pzv=abc123', html)
            self.assertIn('/app.css?v=1&pzv=abc123', html)
            self.assertIn('/app.js?v=1&pzv=abc123', html)


if __name__ == '__main__':
    unittest.main()
