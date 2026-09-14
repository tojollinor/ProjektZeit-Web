import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import provider_budget as budget

class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=budget._root;self.backend=patch.object(budget.database,'is_maria',return_value=False);self.backend.start();budget.initialize(self.tmp.name)
    def tearDown(self):budget._root=self.old;self.backend.stop();self.tmp.cleanup()
    def test_company_limit_counts_concurrent_users(self):
        budget.set_cap('teamviewer',3)
        def call(_):
            try:budget.reserve('teamviewer',100000);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(call,range(12))),3)
    def test_budget_persists_and_rolls_after_24_hours(self):
        budget.set_cap('teamviewer',1);budget.reserve('teamviewer',100000);budget.initialize(self.tmp.name)
        with self.assertRaises(ValueError):budget.reserve('teamviewer',100001)
        budget.reserve('teamviewer',186400)
    def test_cap_and_retry_after(self):
        with self.assertRaises(ValueError):budget.set_cap('teamviewer',3601)
        budget.backoff('teamviewer','300')
        with self.assertRaisesRegex(ValueError,'Wartezeit'):budget.reserve('teamviewer')

if __name__=='__main__':unittest.main()
