import os
import unittest
from unittest.mock import patch
import release_updates as updates


class ReleaseUpdateTest(unittest.TestCase):
    def setUp(self):
        updates._cache=None;updates._expires=0
        self.env=patch.dict(os.environ,{'BUILD_REVISION':'a'*40});self.env.start()
    def tearDown(self):
        self.env.stop();updates._cache=None;updates._expires=0
    def run_info(self,sha):
        return {'workflow_runs':[dict(id=123,head_sha=sha,head_branch='main',event='push',conclusion='success')]}
    def test_only_published_newer_build_is_available_and_shared(self):
        with patch.object(updates,'_read',side_effect=[self.run_info('b'*40),{'status':'ahead'}]) as read:
            self.assertEqual(updates.check()['state'],'available')
            self.assertEqual(updates.check()['state'],'available')
            self.assertEqual(read.call_count,2)
    def test_same_or_older_published_build_is_not_offered(self):
        with patch.object(updates,'_read',return_value=self.run_info('a'*40)):
            self.assertEqual(updates.check()['state'],'current')
        updates._cache=None
        with patch.object(updates,'_read',side_effect=[self.run_info('b'*40),{'status':'behind'}]):
            self.assertEqual(updates.check()['state'],'current')
    def test_unreachable_github_and_unversioned_build_stay_unknown(self):
        with patch.object(updates,'_read',side_effect=TimeoutError):
            self.assertEqual(updates.check()['state'],'error')
        with patch.dict(os.environ,{'BUILD_REVISION':''}),patch.object(updates,'_read') as read:
            self.assertEqual(updates.check()['state'],'unknown');read.assert_not_called()
    def test_in_progress_request_does_not_start_another_check(self):
        updates._lock.acquire()
        try:
            with patch.object(updates,'_read') as read:
                self.assertEqual(updates.check()['state'],'checking');read.assert_not_called()
        finally:updates._lock.release()
