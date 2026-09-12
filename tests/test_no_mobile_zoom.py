import tempfile
import unittest
from pathlib import Path

import frontend_update_runtime


class MobileViewportTests(unittest.TestCase):
    def test_served_index_disables_page_zoom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body></body></html>', encoding='utf-8')
            html = frontend_update_runtime._versioned_index(root, 'test')
            self.assertIn('maximum-scale=1,user-scalable=no', html)


if __name__ == '__main__':
    unittest.main()
