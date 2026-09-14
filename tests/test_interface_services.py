import base64
import smtplib
import socket
import time
import unittest
from unittest.mock import patch, MagicMock
import app
import admin_controls as acl
import auth_mfa
import smtp_service
import next_batch_runtime
import provider_nav_runtime
import test_workday as fixtures


class InterfaceServicesTest(unittest.TestCase):
    def setUp(self):
        fixtures.WorkdayTest.setUp(self)
        with app.db() as c:
            acl.migrate(c);auth_mfa.migrate(c)
            self.user=dict(c.execute('SELECT * FROM users WHERE id=?',(self.uid,)).fetchone())
    def tearDown(self):fixtures.WorkdayTest.tearDown(self)

    def test_new_user_permissions_password_and_duplicate(self):
        with app.db() as c:
            new=acl.create_user(c,self.uid,{'username':'Techniker','password':'a-safe-password','first_name':'Erika'},app.hash_password)
            self.assertTrue(acl.can(c,new,'categories.create'))
            self.assertFalse(acl.can(c,new,'users.create'))
            with self.assertRaises(PermissionError):acl.create_user(c,new,{'username':'Other','password':'a-safe-password'},app.hash_password)
            with self.assertRaises(ValueError):acl.create_user(c,self.uid,{'username':'Techniker','password':'a-safe-password'},app.hash_password)
            row=c.execute('SELECT * FROM users WHERE id=?',(new,)).fetchone()
            self.assertTrue(app.verify_password('a-safe-password',row['password_salt'],row['password_hash']))
            role=acl._role(c,'user')['id'];acl.assign_roles(c,self.uid,new,[role,role])
            self.assertEqual(c.execute('SELECT COUNT(*) n FROM user_role_links WHERE user_id=?',(new,)).fetchone()['n'],1)

    def test_user_deactivation_permissions_and_protected_accounts(self):
        with app.db() as c:
            target=acl.create_user(c,self.uid,{'username':'ActiveTest','password':'a-safe-password'},app.hash_password)
            with self.assertRaises(PermissionError):acl.set_user_active(c,target,{'user_id':self.uid,'active':False})
            with self.assertRaises(ValueError):acl.set_user_active(c,self.uid,{'user_id':self.uid,'active':False})
            with self.assertRaises(ValueError):acl.set_user_active(c,self.uid,{'user_id':target,'active':'false'})
            self.assertEqual(acl.set_user_active(c,self.uid,{'user_id':target,'active':False}),(target,False))
            self.assertEqual(c.execute('SELECT active FROM users WHERE id=?',(target,)).fetchone()['active'],0)
            acl.set_user_active(c,self.uid,{'user_id':target,'active':True})
            self.assertEqual(c.execute('SELECT active FROM users WHERE id=?',(target,)).fetchone()['active'],1)

    def test_totp_reference_enrollment_replay_and_recovery(self):
        # RFC 6238 Appendix B, SHA-1 at 59 seconds, truncated to six digits.
        secret=base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(auth_mfa.totp(secret,1),'287082')
        clock=int(time.time())
        with app.db() as c:
            setup=auth_mfa.begin(c,self.user,app.DATA_DIR)
            code=auth_mfa.totp(setup['secret'],clock//30)
            result=auth_mfa.verify(c,self.uid,code,app.DATA_DIR,enroll=True,clock=clock)
            stored=c.execute('SELECT * FROM user_mfa WHERE user_id=?',(self.uid,)).fetchone()
            self.assertNotIn(setup['secret'],stored['secret'])
            self.assertNotIn(result['recovery_codes'][0],stored['recovery_json'])
            with self.assertRaises(ValueError):auth_mfa.verify(c,self.uid,code,app.DATA_DIR,clock=clock)
            auth_mfa.verify(c,self.uid,result['recovery_codes'][0],app.DATA_DIR,clock=clock)
            with self.assertRaises(ValueError):auth_mfa.verify(c,self.uid,result['recovery_codes'][0],app.DATA_DIR,clock=clock)

    def test_mandatory_policy_and_existing_session_gate(self):
        clock=int(time.time())
        with app.db() as c:
            self.assertEqual(auth_mfa.login(c,self.user,{},app.DATA_DIR),{})
            acl.set_setting(c,'policy.two_factor_mode','required')
            acl.set_setting(c,'policy.two_factor_grace_days',1)
            self.assertFalse(auth_mfa.required(c,self.user,clock=clock))
            self.assertTrue(auth_mfa.required(c,self.user,clock=clock+86401))
            acl.set_setting(c,'policy.two_factor_grace_days',0)
            self.assertFalse(auth_mfa.session_allowed(c,self.user,'old-session'))
            challenge=auth_mfa.login(c,self.user,{},app.DATA_DIR)
            self.assertTrue(challenge['enrollment_required'])
            with self.assertRaises(ValueError):auth_mfa.login(c,self.user,{'otp':'wrong'},app.DATA_DIR)
            result=auth_mfa.login(c,self.user,{'otp':auth_mfa.totp(challenge['secret'],int(time.time())//30)},app.DATA_DIR)
            self.assertTrue(result['_mfa_verified'])
            c.execute('INSERT INTO session_mfa(token_hash) VALUES(?)',('verified-session',))
            self.assertTrue(auth_mfa.session_allowed(c,self.user,'verified-session'))

    def test_dashboard_legacy_layout_and_height_bounds(self):
        layout=next_batch_runtime.dashboard_layout(['stats','missed_calls'])
        self.assertIn('timeline',layout['widgets']);self.assertIn('entries',layout['widgets'])
        layout=next_batch_runtime.dashboard_layout({'widgets':['entries','invalid','entries'],'heights':{'entries':9000,'stats':-1,'timeline':None}})
        self.assertEqual(layout['widgets'],['entries']);self.assertEqual(layout['heights']['entries'],1200);self.assertEqual(layout['heights']['stats'],240)
        self.assertEqual(layout['heights']['timeline'],420)

    def test_central_starface_secret_without_personal_login(self):
        with app.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS starface_system_config(id INTEGER PRIMARY KEY,domain TEXT,client_secret TEXT)')
            c.execute('INSERT INTO starface_system_config VALUES(1,?,?)',('https://pbx.invalid','encrypted-secret'))
            self.assertTrue(provider_nav_runtime._starface_client_secret(app,c,self.uid))
            status=provider_nav_runtime.provider_status(app,c,self.uid,'starface')
            self.assertEqual(status['reason'],'missing');self.assertFalse(status['connected'])

    def test_removed_central_starface_secret_ignores_legacy_login(self):
        with app.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS starface_system_config(id INTEGER PRIMARY KEY,domain TEXT,client_secret TEXT)')
            c.execute('INSERT INTO starface_system_config VALUES(1,?,?)',('https://pbx.invalid',''))
            c.execute('INSERT INTO integrations(owner_id,provider,domain,username,secret,updated_at) VALUES(?,?,?,?,?,?)',
                      (self.uid,'starface','https://pbx.invalid','old-client','old-encrypted-secret','2026-09-14T00:00:00Z'))
            with patch.object(app.integrations,'config',return_value={'secret':'old-secret'}):
                status=provider_nav_runtime.provider_status(app,c,self.uid,'starface')
            self.assertEqual(status['reason'],'missing_client_secret')
            self.assertFalse(status['client_secret_configured'])
            self.assertFalse(status['connected'])

    def test_category_default_is_one_time_and_profile_keeps_last_login(self):
        with app.db() as c:
            role=acl._role(c,'user')['id'];c.execute("DELETE FROM role_permissions WHERE role_id=? AND permission_key='categories.create'",(role,))
            acl.migrate(c)
            self.assertFalse(c.execute("SELECT 1 FROM role_permissions WHERE role_id=? AND permission_key='categories.create'",(role,)).fetchone())
            acl.mark_login(c,self.uid);before=c.execute('SELECT last_login_at FROM user_profiles WHERE user_id=?',(self.uid,)).fetchone()['last_login_at']
            acl.update_user_profile(c,self.uid,{'user_id':self.uid,'first_name':'Erika'})
            self.assertEqual(c.execute('SELECT last_login_at FROM user_profiles WHERE user_id=?',(self.uid,)).fetchone()['last_login_at'],before)


class SmtpTest(unittest.TestCase):
    def setUp(self):self.settings={'host':'mail.invalid','port':587,'security_mode':'starttls','username':'user','sender_name':'ProjektZeit','sender_email':'test@example.invalid'}
    @patch('smtp_service.smtplib.SMTP')
    def test_connection_only_and_explicit_mail(self, smtp):
        client=smtp.return_value
        self.assertTrue(smtp_service.check(self.settings,'password')['ok'])
        client.send_message.assert_not_called();client.login.assert_called_once_with('user','password');client.starttls.assert_called_once()
        smtp_service.check(self.settings,'password','receiver@example.invalid')
        client.send_message.assert_called_once()
    @patch('smtp_service.smtplib.SMTP')
    def test_auth_failure_not_masked_by_quit(self,smtp):
        smtp.return_value.login.side_effect=smtplib.SMTPAuthenticationError(535,b'password rejected')
        smtp.return_value.quit.side_effect=OSError('disconnect')
        with self.assertRaisesRegex(ValueError,'Benutzername'):smtp_service.check(self.settings,'password')
    @patch('smtp_service.smtplib.SMTP',side_effect=socket.timeout())
    def test_timeout_is_clear(self,smtp):
        with self.assertRaisesRegex(ValueError,'Zeitüberschreitung'):smtp_service.check(self.settings,'password')
