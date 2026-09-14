"""Shared customers, provider identities and company defaults regression."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import test_company_services as fixtures
import app
import admin_controls as acl
import collected_update_runtime as collected
import company_master
import customer_data
import customer_access_runtime as access
import duty_plan
import email_runtime
import permission_help
import staff_time
import system_features
import work_models
import zammad_cache_runtime as zammad


class CollectedUpdateTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.CompanyServiceTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.CompanyServiceTest.tearDownClass.__func__)
    setUp = fixtures.CompanyServiceTest.setUp
    tearDown = fixtures.CompanyServiceTest.tearDown

    def test_customers_and_contacts_are_shared_but_provider_archives_are_not(self):
        self.assertEqual([r['id'] for r in customer_data.list_all(self.c, 2)], [1])
        contact = customer_data.add_contact(self.c, 1, 1, 'Kontakt', 'contact@example.test')
        customer_data.add_contact_phone(self.c, 2, contact, '+49401234567')
        customer_data.add_contact_phone(self.c, 1, contact, '+49401234567')
        self.assertEqual(len(customer_data.get_one(self.c, 2, 1)['contacts'][0]['phones']), 1)
        customer_data.update(self.c, 2, 1, {'name': 'Gemeinsam', 'email': 'company@example.test'})
        customer = customer_data.get_one(self.c, 1, 1)
        self.assertEqual(customer['name'], 'Gemeinsam')
        self.assertEqual(customer['email'], 'company@example.test')
        self.assertEqual(self.c.execute('SELECT owner_id FROM customers WHERE id=1').fetchone()[0], 1)
        self.assertEqual(customer_data.activity(self.c, 2, 1), [])

    def test_customer_fields_and_mutations_require_separate_permissions(self):
        row = {'id': 1, 'name': 'Kunde', 'email': 'private@example.test', 'phones': [1], 'contacts': [2], 'devices': [3], 'provider_links': [4]}
        basic = access.filter_customer(row, {'customers.view_basic'})
        self.assertEqual(basic, {'id': 1, 'name': 'Kunde'})
        self.assertEqual(access.required_permissions('/api/v1/customers/contact/update', {}), {'customers.edit'})
        self.assertEqual(access.required_permissions('/api/v1/audit/history', {'entity_type': 'customer'}), {'customers.view_history'})
        self.assertEqual(access.required_permissions('/api/v1/customers/profile', {}), {'customers.create'})
        with self.assertRaises(ValueError):
            customer_data.create(self.c, 2, {'name': 'Kunde', 'email': 'must-not-overwrite@example.test'})

    def test_audit_is_shared_and_retains_actor_and_transaction(self):
        system_features.audit(self.c, 1, 1, 'customer', 1, 'created', {'name': 'Kunde'})
        access.audit_change(self.c, 2, 1, 'changed', {'name': 'Kunde'}, {'name': 'Neu'})
        entries = system_features.history(self.c, 1, 'customer', 1)
        self.assertEqual([e['actor'] for e in entries], ['worker', 'boss'])
        self.assertEqual(entries[0]['changes']['old']['name'], 'Kunde')
        self.c.commit()
        self.c.execute('BEGIN')
        access.audit_change(self.c, 2, 1, 'rolled_back', {}, {'name': 'Kein Eintrag'})
        self.c.rollback()
        self.assertEqual(len(system_features.history(self.c, 2, 'customer', 1)), 2)

    def test_region_default_does_not_rewrite_existing_models(self):
        with patch.object(acl, 'require_permission'):
            work_models.save(self.c, 1, {'user_id': 2, 'valid_from': '2026-01-01', 'mode': 'weekly', 'hours': 40, 'weekdays': [0,1,2,3,4], 'subdivision': 'SH'})
            company_master.save(self.c, 1, {'name': 'Firma', 'subdivision': 'HH', 'version': 0})
            self.assertEqual(company_master.default_region(self.c), 'HH')
            self.assertEqual(self.c.execute('SELECT subdivision FROM work_models WHERE user_id=2').fetchone()[0], 'SH')
            with self.assertRaises(ValueError):
                company_master.save(self.c, 1, {'name': 'Veraltet', 'subdivision': 'SH', 'version': 0})

    def test_unowned_is_distinct_from_unresolved_owner(self):
        identity = {'agent@example.test': {'employee_id': 2, 'employee_name': 'Person', 'employee_username': 'worker'}}
        self.assertTrue(zammad.ticket_employee({'owner': None, 'owner_id': None}, identity)['unowned'])
        self.assertTrue(zammad.ticket_employee({'owner': '-', 'owner_id': 1}, identity)['unowned'])
        self.assertFalse(zammad.ticket_employee({'owner_id': 55}, identity)['unowned'])
        self.assertFalse(zammad.ticket_employee({}, identity)['unowned'])
        employee = zammad.ticket_employee({'owner': {'email': ' Agent@Example.Test '}}, identity)
        self.assertEqual(employee['owner_display'], 'worker')
        self.assertEqual(employee['employee_id'], 2)
        self.assertFalse(employee['unowned'])

    def test_help_covers_every_registered_permission_and_policy(self):
        keys = {r[0] for r in self.c.execute('SELECT DISTINCT permission_key FROM role_permissions')}
        for key in keys:
            self.assertGreater(len(permission_help.permission(key)), 100, key)
        self.assertFalse(set(acl.POLICY_DEFAULTS) - permission_help.POLICIES.keys())

    def test_duty_rotation_can_be_deleted_with_retained_audit(self):
        rotation=duty_plan.save(self.c,1,{'name':'Woche A','from':'2026-09-14T08:00:00+02:00','to':'2026-09-28T08:00:00+02:00','members':[1,2],'period_days':7,'review_swaps':True})['id']
        self.assertEqual(duty_plan.listing(self.c,1,{'from':'2026-09-14','to':'2026-09-28'})['rotations'][0]['id'],rotation)
        duty_plan.delete(self.c,1,{'id':rotation})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM duty_rotations').fetchone()[0],0)
        event=self.c.execute("SELECT action,changes_json FROM audit_events WHERE entity_type='duty_plan' AND entity_id=? ORDER BY id DESC",(str(rotation),)).fetchone()
        self.assertEqual(event['action'],'deleted')
        self.assertEqual(json.loads(event['changes_json'])['slots'],2)

    def test_retroactive_work_model_respects_closed_month(self):
        self.c.execute("INSERT INTO staff_month_closures VALUES(2,'2026-08','{}',1,'2026-09-01T00:00:00+00:00')")
        body={'user_id':2,'valid_from':'2026-08-01','effective_mode':'retroactive','mode':'weekly','hours':40,'weekdays':[0,1,2,3,4],'subdivision':'SH'}
        with patch.object(work_models,'now',return_value=datetime(2026,9,14,12,tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ValueError,'wieder öffnen'):work_models.save(self.c,1,body)
            self.c.execute("DELETE FROM staff_month_closures WHERE user_id=2 AND month='2026-08'")
            ident=work_models.save(self.c,1,body)['id']
            now_id=work_models.save(self.c,1,{**body,'valid_from':'2020-01-01','effective_mode':'now'})['id']
        self.assertEqual(self.c.execute('SELECT valid_from FROM work_models WHERE id=?',(ident,)).fetchone()[0],'2026-08-01')
        self.assertEqual(self.c.execute('SELECT valid_from FROM work_models WHERE id=?',(now_id,)).fetchone()[0],'2026-09-14')

    def test_payroll_overview_reopen_and_safe_csv(self):
        staff_time.save_model(self.c,1,{'user_id':2,'valid_from':'2026-01-01','mode':'weekly','hours':40,'weights':[1,1,1,1,1,0,0],'subdivision':'SH'})
        report=staff_time.month_report(self.c,2,'2026-08')
        self.c.execute('INSERT INTO staff_month_closures VALUES(?,?,?,?,?)',(2,'2026-08',json.dumps(report),1,'2026-09-01T00:00:00+00:00'))
        self.c.execute("UPDATE users SET username='=formula' WHERE id=2")
        overview=staff_time.payroll_overview(self.c,1,{'month':'2026-08','user_id':2})
        self.assertEqual(overview['rows'][0]['status'],'closed')
        exported=staff_time.payroll_export(self.c,1,{'month':'2026-08','user_id':2})['content']
        self.assertIn("'=formula",exported)
        staff_time.reopen_month(self.c,1,{'month':'2026-08','user_id':2,'note':'Korrektur erforderlich'})
        self.assertFalse(self.c.execute("SELECT 1 FROM staff_month_closures WHERE user_id=2 AND month='2026-08'").fetchone())
        self.assertTrue(self.c.execute("SELECT 1 FROM audit_events WHERE entity_type='payroll_month' AND action='reopened'").fetchone())

    def test_password_history_and_email_template_are_enforced(self):
        old_salt,old_hash=app.hash_password('Older-password-123!')
        new_salt,new_hash=app.hash_password('Newer-password-456!')
        self.c.execute('UPDATE users SET password_salt=?,password_hash=? WHERE id=2',(new_salt,new_hash))
        acl.set_setting(self.c,'policy.password_history',3)
        collected.archive_password(self.c,2,old_salt,old_hash)
        with self.assertRaisesRegex(ValueError,'bereits verwendet'):
            collected.ensure_password_unused(self.c,2,'Older-password-123!',app.verify_password)
        with self.assertRaisesRegex(ValueError,'bereits verwendet'):
            collected.ensure_password_unused(self.c,2,'Newer-password-456!',app.verify_password)
        template=collected.validate_template({'company_name':'Beispiel GmbH','logo_url':'https://example.test/logo.png','primary_color':'#112233','accent_color':'#abcdef','footer_text':'Eigene Fußzeile'})
        rendered=email_runtime._mail_content('Test','Max','Inhalt','Öffnen','https://example.test',template=template)['html']
        self.assertIn('Beispiel GmbH',rendered)
        self.assertIn('background:#abcdef',rendered)
        self.assertIn('Eigene Fußzeile',rendered)
        self.assertIn('/projektzeit-logo.png',collected.preview(self.c)['html'])
        with self.assertRaises(ValueError):collected.validate_template({**template,'logo_url':'ftp://example.test/logo.png'})


if __name__ == '__main__':
    unittest.main()
