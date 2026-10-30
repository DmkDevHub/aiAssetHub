import copy
import json
import unittest
from unittest.mock import patch
import test_annotations as fixtures
import test_provenance as provenance_fixtures
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.source_records import Sources
from ai_asset_hub_core.libraries import LibraryError


class SourceTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown
    subject = provenance_fixtures.ProvenanceTests.subject
    package = provenance_fixtures.ProvenanceTests.package
    call = provenance_fixtures.ProvenanceTests.call

    def source_value(self):
        return dict(site='fixture store', productName='상품', originalUrl='https://example.com/source',
                    productUrl='https://example.com/product', downloadUrl='https://example.com/download?token=PRIVATE-TOKEN',
                    purchase=dict(amount=None, currency='', purchasedOn='', downloadedOn=''))

    def test_unknown_free_paid_dates_and_no_network_or_model_actions(self):
        service = Sources(self.db)
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')), patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            for amount, state in ((None, 'unknown'), ('0', 'free'), ('0.0000', 'free'), ('12.3400', 'paid')):
                value = self.source_value(); value['purchase'].update(amount=amount, currency='KRW' if amount else '', purchasedOn='2024-02-29', downloadedOn='2026-10-30')
                record = service.create_record(dict(subject=self.subject(), value=value))
                full = service.get_record(dict(record_id=record['id'], include_private=True, confirmed=True))
                self.assertEqual(full['priceState'], state); self.assertEqual(full['value']['purchase']['amount'], amount)
        for table in ('analysis_jobs', 'asset_embeddings', 'model_registry'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_invalid_prices_urls_dates_and_missing_confirmation_are_safe(self):
        invalid = [('amount', 0), ('amount', True), ('amount', '-1'), ('amount', 'NaN'), ('amount', '01'),
                   ('amount', '1.12345'), ('currency', 'krw'), ('purchasedOn', '2025-02-29'), ('downloadedOn', '2026-13-01')]
        for field, bad in invalid:
            value = self.source_value(); value['purchase'][field] = bad
            result = self.call('source.create', subject=self.subject(), value=value)
            self.assertEqual(result['error']['code'], 'INVALID_PARAMS')
            self.assertNotIn('PRIVATE-TOKEN', json.dumps(result))
        for url in ('file:///C:/secret', 'http://example.com', 'https://u:p@example.com', 'https://bad host'):
            value = self.source_value(); value['originalUrl'] = url
            self.assertEqual(self.call('source.create', subject=self.subject(), value=value)['error']['code'], 'INVALID_PARAMS')
        record = Sources(self.db).create_record(dict(subject=self.subject(), value=self.source_value()))
        self.assertEqual(self.call('source.get', record_id=record['id'], include_private=True)['error']['code'], 'INVALID_PARAMS')

    def test_owner_pagination_private_projection_and_immutable_purchase_history(self):
        service = Sources(self.db); package = self.package(); owner = dict(kind='package', id=package['id'])
        records = [service.create_record(dict(subject=owner, value=self.source_value())) for _ in range(3)]
        page = service.list_records(dict(subject=owner, after_id=None))
        self.assertEqual(len(page['items']), 2)
        self.assertEqual(len(service.list_records(dict(subject=owner, after_id=page['next_cursor']))['items']), 1)
        for payload in (page, service.get_record({'record_id': records[0]['id']})):
            self.assertNotIn('PRIVATE-TOKEN', json.dumps(payload)); self.assertNotIn('purchase', payload.get('value', {}))
        with self.assertRaises(LibraryError): service.list_records(dict(subject=self.subject(), after_id=records[0]['id']))
        value = self.source_value(); value['purchase'].update(amount='500', currency='KRW')
        updated = service.update_record(dict(record_id=records[0]['id'], value=value, expected_revision=1))
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'):
            service.update_record(dict(record_id=records[0]['id'], value=self.source_value(), expected_revision=1))
        history = self.db.connection.execute("SELECT before_json FROM provenance_history WHERE entity_id=? AND action='update'", (records[0]['id'],)).fetchone()[0]
        self.assertIsNone(json.loads(history)['value']['purchase']['amount'])
        audit = json.dumps(self.db.connection.execute('SELECT details_redacted_json FROM audit_events').fetchall())
        self.assertNotIn('PRIVATE-TOKEN', audit)
        service.delete_record(dict(record_id=updated['id'], expected_revision=2, confirmed=True))
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        self.assertFalse(Sources(self.db).get_record({'record_id': updated['id']})['enabled'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM provenance_sources').fetchone()[0], 3)

    def test_late_history_failure_rolls_back_create_update_and_delete(self):
        service = Sources(self.db); original = service.create_record(dict(subject=self.subject(), value=self.source_value()))
        before = self.db.connection.execute('SELECT * FROM provenance_sources').fetchall()
        self.db.connection.execute("CREATE TRIGGER fixture_source_fail BEFORE INSERT ON provenance_history BEGIN SELECT RAISE(ABORT,'private-fixture'); END;")
        value = self.source_value(); value['productName'] = 'changed'
        for method, params in [('source.create', dict(subject=self.subject(), value=value)),
                               ('source.update', dict(record_id=original['id'], value=value, expected_revision=1)),
                               ('source.delete', dict(record_id=original['id'], expected_revision=1, confirmed=True))]:
            result = self.call(method, **params)
            self.assertEqual(result['error']['code'], 'DB_UNAVAILABLE')
            self.assertEqual(self.db.connection.execute('SELECT * FROM provenance_sources').fetchall(), before)
            self.assertNotIn('private-fixture', json.dumps(result))
