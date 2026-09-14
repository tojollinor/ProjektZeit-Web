"""Shared customers, provider identities and company defaults regression."""
import unittest
from unittest.mock import patch
import test_company_services as fixtures
import admin_controls as acl
import company_master
import customer_data
import customer_access_runtime as access
import permission_help
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
        self.assertFalse(set(acl.POLICY_DEFAULTS) - {'two_factor_admin_required'} - permission_help.POLICIES.keys())


if __name__ == '__main__':
    unittest.main()
