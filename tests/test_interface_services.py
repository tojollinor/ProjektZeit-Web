import base64
import json
import os
import re
import smtplib
import socket
import time
import unittest
from unittest.mock import patch, MagicMock
import app
import admin_controls as acl
import auth_mfa
import email_runtime
import smtp_service
import next_batch_runtime
import provider_nav_runtime
import zammad_cache_runtime
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
            temporary=acl.create_user(c,self.uid,{'username':'Temporary','password':'a-safe-password','must_change_password':True},app.hash_password)
            state=c.execute('SELECT must_change_password FROM user_security_state WHERE user_id=?',(temporary,)).fetchone()
            self.assertEqual(state['must_change_password'],1)
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
        with app.db() as c:
            self.assertEqual(auth_mfa.login(c,self.user,{},app.DATA_DIR),{})
            assigned=c.execute('''SELECT d.role_key FROM role_definitions d JOIN user_role_links l
                                  ON l.role_id=d.id WHERE l.user_id=? ORDER BY d.id LIMIT 1''',(self.uid,)).fetchone()['role_key']
            acl.set_setting(c,'policy.two_factor_mode','roles')
            acl.set_setting(c,'policy.two_factor_required_roles',['not-assigned'])
            self.assertFalse(auth_mfa.required(c,self.user))
            acl.set_setting(c,'policy.two_factor_required_roles',[assigned])
            self.assertTrue(auth_mfa.required(c,self.user))
            acl.set_setting(c,'policy.two_factor_mode','required')
            self.assertFalse(auth_mfa.session_allowed(c,self.user,'old-session'))
            challenge=auth_mfa.login(c,self.user,{},app.DATA_DIR)
            self.assertTrue(challenge['enrollment_required'])
            with self.assertRaises(ValueError):auth_mfa.login(c,self.user,{'otp':'wrong'},app.DATA_DIR)
            result=auth_mfa.login(c,self.user,{'otp':auth_mfa.totp(challenge['secret'],int(time.time())//30)},app.DATA_DIR)
            self.assertTrue(result['_mfa_verified'])
            c.execute('INSERT INTO session_mfa(token_hash) VALUES(?)',('verified-session',))
            self.assertTrue(auth_mfa.session_allowed(c,self.user,'verified-session'))

    def test_email_mfa_code_settings_template_and_single_use(self):
        with app.db() as c:
            email_runtime.migrate(c)
            c.execute("UPDATE user_profiles SET first_name='Tobi',email='tobi@example.invalid' WHERE user_id=?",(self.uid,))
            email_runtime._replace_state(c,self.uid,'tobi@example.invalid',email_runtime.now_iso())
            c.execute('''INSERT INTO smtp_settings(id,sender_name,sender_email,host,port,security_mode,username,password_secret,updated_at)
                         VALUES(1,'ProjektZeit','portal@example.invalid','mail.example.invalid',587,'starttls','','',?)''',(email_runtime.now_iso(),))
            acl.set_setting(c,'policy.email_mfa_code_kind','alphanumeric')
            acl.set_setting(c,'policy.email_mfa_code_length',8)
            self.assertEqual(email_runtime._email_code_settings(c),(8,'alphanumeric'))
            with patch.object(email_runtime,'_generate_email_code',return_value='ABCD2345'):
                result=email_runtime.begin_email_mfa(c,app.DATA_DIR,self.user)
            self.assertEqual(result['masked_email'],'t***@example.invalid')
            queued=c.execute('SELECT body_secret FROM email_outbox ORDER BY id DESC LIMIT 1').fetchone()
            content=__import__('json').loads(__import__('integrations').cipher(app.DATA_DIR).decrypt(queued['body_secret'].encode()).decode())
            self.assertIn('Hallo Tobi',content['html'])
            self.assertIn('cid:projektzeit-logo',content['html'])
            self.assertIn('ABCD2345',content['html'])
            with self.assertRaisesRegex(ValueError,'falsch'):
                email_runtime.verify_email_mfa(c,self.uid,'WRONG234')
            self.assertTrue(email_runtime.verify_email_mfa(c,self.uid,'ABCD2345'))
            self.assertTrue(email_runtime.email_mfa_enabled(c,self.uid))
            with self.assertRaisesRegex(ValueError,'abgelaufen'):
                email_runtime.verify_email_mfa(c,self.uid,'ABCD2345')

    @patch.dict(os.environ,{'APP_PUBLIC_URL':'https://projektzeit.example.invalid'},clear=False)
    def test_email_verification_and_password_reset_links_are_single_use(self):
        with app.db() as c:
            email_runtime.migrate(c)
            c.execute("UPDATE user_profiles SET first_name='Tobi',email='tobi@example.invalid' WHERE user_id=?",(self.uid,))
            email_runtime._replace_state(c,self.uid,'tobi@example.invalid')
            c.execute('DELETE FROM smtp_settings WHERE id=1')
            c.execute('''INSERT INTO smtp_settings(id,sender_name,sender_email,host,port,security_mode,username,password_secret,updated_at)
                         VALUES(1,'ProjektZeit','portal@example.invalid','mail.example.invalid',587,'starttls','','',?)''',(email_runtime.now_iso(),))
            acl.set_setting(c,'policy.email_verify_required',True)
            self.assertTrue(email_runtime.request_verification(c,app.DATA_DIR,self.uid))
            queued=c.execute('SELECT body_secret FROM email_outbox ORDER BY id DESC LIMIT 1').fetchone()
            content=json.loads(__import__('integrations').cipher(app.DATA_DIR).decrypt(queued['body_secret'].encode()).decode())
            verify_token=re.search(r'[?&]verify-email=([^\s]+)',content['text']).group(1)
            self.assertEqual(email_runtime.consume_verification(c,verify_token),self.uid)
            self.assertTrue(email_runtime.email_verified(c,self.uid))
            with self.assertRaisesRegex(ValueError,'ungültig|abgelaufen'):
                email_runtime.consume_verification(c,verify_token)

            acl.set_setting(c,'policy.email_password_reset_allowed',True)
            self.assertTrue(email_runtime.request_password_reset(c,app.DATA_DIR,'tobi@example.invalid'))
            queued=c.execute('SELECT body_secret FROM email_outbox ORDER BY id DESC LIMIT 1').fetchone()
            content=json.loads(__import__('integrations').cipher(app.DATA_DIR).decrypt(queued['body_secret'].encode()).decode())
            reset_token=re.search(r'[?&]password-reset=([^\s]+)',content['text']).group(1)
            self.assertEqual(email_runtime.reset_password(c,app.DATA_DIR,reset_token,'a-brand-new-password','a-brand-new-password',app.hash_password),self.uid)
            user=c.execute('SELECT password_salt,password_hash FROM users WHERE id=?',(self.uid,)).fetchone()
            self.assertTrue(app.verify_password('a-brand-new-password',user['password_salt'],user['password_hash']))
            with self.assertRaisesRegex(ValueError,'ungültig|abgelaufen'):
                email_runtime.reset_password(c,app.DATA_DIR,reset_token,'another-safe-password','another-safe-password',app.hash_password)

    def test_dashboard_legacy_layout_and_height_bounds(self):
        layout=next_batch_runtime.dashboard_layout(['stats','missed_calls'])
        self.assertIn('timeline',layout['widgets']);self.assertIn('entries',layout['widgets'])
        layout=next_batch_runtime.dashboard_layout({'widgets':['entries','invalid','entries'],'heights':{'entries':9000,'stats':-1,'timeline':None}})
        self.assertEqual(layout['widgets'],['entries']);self.assertEqual(layout['heights']['entries'],1200);self.assertEqual(layout['heights']['stats'],240)
        self.assertEqual(layout['heights']['timeline'],420)
        self.assertEqual(next_batch_runtime._call_display_name('004946642459805 : Claudia Keßmann','004946642459805'),'Claudia Keßmann')
        self.assertEqual(next_batch_runtime._call_display_name('Zentrale','004946642459805'),'Zentrale')

    def test_log_limits_and_filtered_total(self):
        import provider_archive
        with app.db() as c:
            provider_archive.migrate(c)
            for index in range(30):
                provider_archive.add_log(c,self.uid,'zammad' if index%2 else 'starface','success','sync',str(index))
            self.assertEqual(len(provider_archive.list_logs(c,self.uid,limit=25)),25)
            self.assertEqual(len(provider_archive.list_logs(c,self.uid,limit='all')),30)
            self.assertEqual(provider_archive.count_logs(c,self.uid,'zammad','success'),15)

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

    def test_zammad_refresh_paginates_complete_snapshot_and_removes_stale_rows(self):
        import customer_data
        import final_batch_runtime
        import integrations
        import provider_archive
        with app.db() as c:
            integrations.migrate(c);customer_data.migrate(c);provider_archive.migrate(c);final_batch_runtime.migrate(c);zammad_cache_runtime.migrate(c)
            secret=integrations.cipher(app.DATA_DIR).encrypt(b'test-token').decode()
            c.execute("INSERT INTO integrations(owner_id,provider,domain,username,secret,updated_at) VALUES(?,'zammad','https://tickets.example.invalid','admin@example.invalid',?,'')",(self.uid,secret))
            zammad_cache_runtime._upsert(c,self.uid,{'id':'stale','number':'stale','title':'Alter Eintrag','state':'open'},'old')
        tickets=[{'id':i,'number':str(i),'title':'Ticket '+str(i),'owner':{'email':'admin@example.invalid'},
                  'customer':{'email':'customer'+str(i)+'@example.invalid'},'state':'open','updated_at':'2026-09-14T10:00:00Z'} for i in range(1,53)]
        client=MagicMock();client.request.side_effect=[(200,tickets[:50],''),(200,tickets[50:],'')]
        with patch.object(zammad_cache_runtime.integrations,'Client',return_value=client):
            result=zammad_cache_runtime._full_refresh(app,self.uid)
        self.assertEqual(result['pages'],2)
        self.assertEqual(result['total_records'],52)
        self.assertEqual(result['removed'],1)
        with app.db() as c:
            ids={row['ticket_id'] for row in c.execute('SELECT ticket_id FROM zammad_ticket_cache WHERE owner_id=?',(self.uid,))}
        self.assertNotIn('stale',ids)
        self.assertEqual(len(ids),52)

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
    @patch('smtp_service.smtplib.SMTP')
    def test_html_mail_contains_plain_fallback_and_inline_logo(self,smtp):
        smtp_service.send(self.settings,'password','receiver@example.invalid','Sicherheitscode','Plain fallback',
                          '<html><body><img src="cid:projektzeit-logo">Code</body></html>',b'png-bytes')
        message=smtp.return_value.send_message.call_args.args[0]
        self.assertEqual(message.get_content_type(),'multipart/alternative')
        self.assertIn('Plain fallback',message.get_body(preferencelist=('plain',)).get_content())
        html=message.get_body(preferencelist=('html',))
        self.assertIn('cid:projektzeit-logo',html.get_content())
        image=next(part for part in message.walk() if part.get_content_maintype()=='image')
        self.assertEqual(image['Content-ID'],'<projektzeit-logo>')
        self.assertEqual(image.get_payload(decode=True),b'png-bytes')
