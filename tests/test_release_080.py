import base64
import hashlib
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import admin_controls
import app
import auth_mfa
import email_runtime
import release_080_runtime as release
import system_features
import test_workday
import work_models


class Release080Tests(unittest.TestCase):
    tearDown = test_workday.WorkdayTest.tearDown

    def setUp(self):
        test_workday.WorkdayTest.setUp(self)
        with app.db() as c:
            admin_controls.migrate(c)
            auth_mfa.migrate(c)
            email_runtime.migrate(c)
            system_features.migrate(c)
            work_models.migrate(c)
            release.migrate(c)
            c.execute('''CREATE TABLE IF NOT EXISTS starface_manual_callbacks (
                owner_id INTEGER NOT NULL, external_key VARCHAR(255) NOT NULL,
                marked_by INTEGER, marked_at VARCHAR(40) NOT NULL,
                PRIMARY KEY(owner_id,external_key))''')

    @staticmethod
    def oauth_body(verifier='v' * 64):
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b'=').decode()
        return {
            'response_type': 'code',
            'client_id': release.CLIENT_ID,
            'client_name': 'ProjektZeit Test',
            'redirect_uri': 'http://127.0.0.1:49152/callback',
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'state': 'state-' + 's' * 32,
        }

    def test_browser_oauth_pkce_code_is_one_time(self):
        verifier = 'v' * 64
        with app.db() as c:
            approved = release.authorize(c, self.uid, self.oauth_body(verifier))
            query = parse_qs(urlsplit(approved['redirect_url']).query)
            self.assertEqual(query['state'], ['state-' + 's' * 32])
            token = release.exchange(c, app, {
                'grant_type': 'authorization_code',
                'client_id': release.CLIENT_ID,
                'redirect_uri': 'http://127.0.0.1:49152/callback',
                'code': query['code'][0],
                'code_verifier': verifier,
            })
            self.assertEqual(token['token_type'], 'Bearer')
            self.assertGreaterEqual(token['expires_in'], 3600)
            digest = hashlib.sha256(token['access_token'].encode()).hexdigest()
            self.assertTrue(c.execute(
                'SELECT 1 FROM native_sessions WHERE token_hash=?', (digest,)
            ).fetchone())
            with self.assertRaisesRegex(ValueError, 'bereits verwendet'):
                release.exchange(c, app, {
                    'grant_type': 'authorization_code',
                    'client_id': release.CLIENT_ID,
                    'redirect_uri': 'http://127.0.0.1:49152/callback',
                    'code': query['code'][0],
                    'code_verifier': verifier,
                })

    def test_browser_oauth_rejects_wrong_grant_and_redirects(self):
        with app.db() as c:
            with self.assertRaisesRegex(ValueError, 'OAuth-Grant'):
                release.exchange(c, app, {'grant_type': 'password'})
            for redirect in (
                'https://127.0.0.1:49152/callback',
                'http://localhost:49152/callback',
                'http://127.0.0.1:49152/other',
                'http://127.0.0.1:49152/callback?code=leak',
            ):
                body = self.oauth_body()
                body['redirect_uri'] = redirect
                with self.assertRaisesRegex(ValueError, 'Rückleitungsadresse'):
                    release.authorize(c, self.uid, body)

    def test_bootstrap_account_is_protected_and_other_account_is_anonymized(self):
        salt, digest = app.hash_password('Valid-test-password-123!')
        with app.db() as c:
            other = c.execute(
                "INSERT INTO users(username,password_salt,password_hash,role,created_at) VALUES(?,?,?,'user',?)",
                ('person@example.test', salt, digest, app.now_iso()),
            ).lastrowid
            c.execute(
                "INSERT INTO user_profiles(user_id,first_name,last_name,email,phone,note) VALUES(?,?,?,?,?,?)",
                (other, 'Erika', 'Muster', 'person@example.test', '12345', 'privat'),
            )
            with self.assertRaisesRegex(ValueError, 'ADMIN_USER'):
                release.delete_user(c, app, self.uid, self.uid, self_service=False)
            result = release.delete_user(
                c, app, other, other,
                password='Valid-test-password-123!', self_service=True,
            )
            self.assertTrue(result['logged_out'])
            user = c.execute('SELECT username,active FROM users WHERE id=?', (other,)).fetchone()
            self.assertEqual(user['active'], 0)
            self.assertRegex(user['username'], r'^gelöscht-\d+-[0-9a-f]{8}$')
            profile = c.execute('SELECT * FROM user_profiles WHERE user_id=?', (other,)).fetchone()
            self.assertFalse(any(profile[key] for key in ('first_name','last_name','email','phone','note')))
            visible = release.decorate_users(c, self.uid, admin_controls.list_users(c, self.uid))
            self.assertNotIn(other, [row['id'] for row in visible])

    def test_historical_work_model_can_be_edited_and_deleted_until_month_closes(self):
        with patch.object(work_models, 'now', return_value=datetime(
                2026, 9, 15, 12, tzinfo=timezone.utc)):
            with app.db() as c, patch.object(admin_controls, 'require_permission'):
                model = work_models.save(c, self.uid, {
                    'user_id': self.uid, 'valid_from': '2026-01-01',
                    'effective_mode': 'retroactive', 'mode': 'weekly', 'hours': 40,
                    'weekdays': [0,1,2,3,4], 'subdivision': 'SH',
                })
                work_models.save(c, self.uid, {
                    'id': model['id'], 'version': 1, 'user_id': self.uid,
                    'valid_from': '2026-01-01', 'effective_mode': 'retroactive',
                    'mode': 'weekly', 'hours': 35,
                    'weekdays': [0,1,2,3,4], 'subdivision': 'SH',
                })
                self.assertEqual(work_models.models(c, self.uid)[0]['target_seconds'], 35 * 3600)
                work_models.delete(c, self.uid, {'id': model['id'], 'user_id': self.uid})
                self.assertEqual(work_models.models(c, self.uid), [])

    def test_work_model_touching_closed_month_cannot_be_changed_or_deleted(self):
        with patch.object(work_models, 'now', return_value=datetime(
                2026, 9, 15, 12, tzinfo=timezone.utc)):
            with app.db() as c, patch.object(admin_controls, 'require_permission'):
                model = work_models.save(c, self.uid, {
                    'user_id': self.uid, 'valid_from': '2026-01-01',
                    'effective_mode': 'retroactive', 'mode': 'weekly', 'hours': 40,
                    'weekdays': [0,1,2,3,4], 'subdivision': 'SH',
                })
                c.execute('''CREATE TABLE staff_month_closures(
                    user_id INTEGER NOT NULL, month VARCHAR(7) NOT NULL,
                    snapshot_json LONGTEXT NOT NULL, created_by INTEGER NOT NULL,
                    created_at VARCHAR(40) NOT NULL, PRIMARY KEY(user_id,month))''')
                c.execute('INSERT INTO staff_month_closures VALUES(?,?,?,?,?)',
                          (self.uid, '2026-03', '{"posted_seconds":0,"days":[]}', self.uid, app.now_iso()))
                with self.assertRaisesRegex(ValueError, 'abgeschlossenen Abrechnungsmonat'):
                    work_models.save(c, self.uid, {
                        'id': model['id'], 'version': 1, 'user_id': self.uid,
                        'valid_from': '2026-07-01', 'effective_mode': 'retroactive',
                        'mode': 'weekly', 'hours': 35,
                        'weekdays': [0,1,2,3,4], 'subdivision': 'SH',
                    })
                with self.assertRaisesRegex(ValueError, 'abgeschlossenen Abrechnungsmonat'):
                    work_models.delete(c, self.uid, {'id': model['id'], 'user_id': self.uid})

    def test_totp_and_email_can_coexist_and_are_both_offered(self):
        stamp = app.now_iso()
        with app.db() as c:
            c.execute("UPDATE user_profiles SET email='admin@example.test' WHERE user_id=?", (self.uid,))
            email_runtime._replace_state(c, self.uid, 'admin@example.test', stamp)
            c.execute('DELETE FROM user_mfa WHERE user_id=?', (self.uid,))
            c.execute("""INSERT INTO user_mfa
                (user_id,secret,pending_secret,enabled,last_counter,recovery_json,pending_until)
                VALUES(?,'encrypted-secret','',1,-1,'[]',0)""", (self.uid,))
            c.execute('DELETE FROM user_email_mfa WHERE user_id=?', (self.uid,))
            c.execute('INSERT INTO user_email_mfa(user_id,email,enabled,created_at) VALUES(?,?,1,?)',
                      (self.uid, 'admin@example.test', stamp))
            context = email_runtime.mfa_context(c, self.uid)
            self.assertEqual(context['method'], 'multiple')
            self.assertEqual(context['methods'], ['totp', 'email'])

    def test_later_answered_starface_call_closes_only_older_missed_calls(self):
        calls = [
            ('missed-1', '2026-09-15T08:00:00+00:00', {
                'startTime':'2026-09-15T08:00:00+00:00', 'direction':'INBOUND',
                'result':'MISSED', 'callerNumber':'0049 40 123 45 67',
            }),
            ('missed-2', '2026-09-15T08:30:00+00:00', {
                'startTime':'2026-09-15T08:30:00+00:00', 'direction':'INBOUND',
                'result':'MISSED', 'callerNumber':'+49 (40) 1234567',
            }),
            ('callback', '2026-09-15T09:00:00+00:00', {
                'startTime':'2026-09-15T09:00:00+00:00', 'direction':'OUTBOUND',
                'result':'ANSWERED', 'calledNumber':'040 / 1234567', 'duration':120,
            }),
            ('missed-later', '2026-09-15T10:00:00+00:00', {
                'startTime':'2026-09-15T10:00:00+00:00', 'direction':'INBOUND',
                'result':'MISSED', 'callerNumber':'+49 40 1234567',
            }),
        ]
        with app.db() as c:
            for key, occurred, raw in calls:
                c.execute('''INSERT INTO provider_events
                    (owner_id,provider,external_key,occurred_at,summary,raw_json,hint_json,captured_at)
                    VALUES(?,'starface',?,?,?,?,'{}',?)''',
                    (self.uid, key, occurred, key, json.dumps(raw), occurred))
            self.assertEqual(release.reconcile_starface_callbacks(c, self.uid), 2)
            marked = {row['external_key'] for row in c.execute(
                'SELECT external_key FROM starface_manual_callbacks WHERE owner_id=?', (self.uid,))}
            self.assertEqual(marked, {'missed-1', 'missed-2'})
            self.assertEqual(release.reconcile_starface_callbacks(c, self.uid), 0)

    def test_windows_and_mobile_release_contract(self):
        root = Path(__file__).resolve().parents[1]
        ET.parse(root / 'windows-client' / 'App.xaml')
        ET.parse(root / 'windows-client' / 'MainWindow.xaml')
        source = (root / 'windows-client' / 'MainWindow.xaml.cs').read_text(encoding='utf-8')
        xaml = (root / 'windows-client' / 'MainWindow.xaml').read_text(encoding='utf-8')
        js = (root / 'static' / 'release-080.js').read_text(encoding='utf-8')
        css = (root / 'static' / 'release-080.css').read_text(encoding='utf-8')
        self.assertIn('grant_type = "authorization_code"', source)
        self.assertIn('code_challenge_method=S256', source)
        self.assertIn('ProtectedData.Protect', source)
        self.assertNotIn('PasswordBox', xaml)
        self.assertIn('Im Browser anmelden', xaml)
        self.assertIn("document.addEventListener('touchmove',pinchMove", js)
        self.assertIn("document.addEventListener('wheel',wheelZoom", js)
        self.assertIn('.company-calendar-mobile{display:grid!important', css)
        self.assertIn('.provider-view .pz-assignment-dot{display:none!important}', css)
        self.assertIn('.provider-view .mobile-assignment-dot{display:inline-block!important}', css)
        self.assertIn('normalizeProviderDots', js)


if __name__ == '__main__':
    unittest.main()
