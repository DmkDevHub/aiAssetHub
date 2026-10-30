import json
import sqlite3
import unittest
from unittest.mock import patch
import test_annotations as fixtures
import test_sources as source_fixtures
from ai_asset_hub_core.source_records import Sources
from ai_asset_hub_core.license_records import Licenses
from ai_asset_hub_core.packages import Packages
from ai_asset_hub_core.libraries import LibraryError


class LicenseTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown
    subject = source_fixtures.SourceTests.subject
    package = source_fixtures.SourceTests.package
    call = source_fixtures.SourceTests.call
    source_value = source_fixtures.SourceTests.source_value

    def license_value(self):
        return dict(label='Declared fixture license', terms='条件\n조건', attribution='제작자 표시문',
                    reviewStatus='unknown', scope='선택 에셋', note='PRIVATE-RECEIPT-NOTE', source_id=None)

    def test_explicit_user_review_never_means_permission_and_source_scope_is_enforced(self):
        service = Licenses(self.db)
        for status in ('unknown', 'needs_review', 'user_reviewed'):
            value = self.license_value(); value['reviewStatus'] = status
            with patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
                record = service.create_record(dict(subject=self.subject(), value=value, confirmed=True))
            self.assertEqual(record['permission'], 'unknown'); self.assertEqual(record['declaredBy'], 'user')
            self.assertNotIn('terms', record['value']); self.assertNotIn('PRIVATE-RECEIPT', json.dumps(record))
        self.assertEqual(self.call('license.create', subject=self.subject(), value=self.license_value(), confirmed=False)['error']['code'], 'INVALID_PARAMS')
        value = self.license_value(); value['actor'] = 'ai'
        self.assertEqual(self.call('license.create', subject=self.subject(), value=value, confirmed=True)['error']['code'], 'INVALID_PARAMS')
        package = self.package(); other = dict(kind='package', id=package['id'])
        source = Sources(self.db).create_record(dict(subject=other, value=self.source_value()))
        value = self.license_value(); value['source_id'] = source['id']
        with self.assertRaises(LibraryError): service.create_record(dict(subject=self.subject(), value=value, confirmed=True))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.connection.execute('INSERT INTO provenance_licenses VALUES (?,?,NULL,?,1,1)', ('fixture', self.id, json.dumps(value)))

    def test_registered_evidence_is_scoped_private_and_no_original_bytes_change(self):
        service = Licenses(self.db); package = self.package(); owner = dict(kind='package', id=package['id'])
        record = service.create_record(dict(subject=owner, value=self.license_value(), confirmed=True))
        file_id = self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id=?', (self.id,)).fetchone()[0]
        params = dict(record_id=record['id'], files=[dict(file_id=file_id, label='PRIVATE-PROOF')], expected_revision=1, confirmed=True)
        with self.assertRaises(LibraryError): service.save_evidence(params)
        Packages(self.db).package_assign(dict(asset_id=self.id, package_ids=[package['id']], expected_revision=0))
        result = service.save_evidence(params)
        self.assertEqual(result['evidenceCount'], 1); self.assertNotIn('PRIVATE-PROOF', json.dumps(result))
        full = service.get_record(dict(record_id=record['id'], include_private=True, confirmed=True))
        self.assertEqual(full['evidence'][0]['availability'], 'present')
        self.assertNotIn('path', full['evidence'][0])
        Packages(self.db).package_assign(dict(asset_id=self.id, package_ids=[], expected_revision=1))
        full = service.get_record(dict(record_id=record['id'], include_private=True, confirmed=True))
        self.assertEqual(full['evidence'][0]['availability'], 'unavailable')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM license_evidence').fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute('DELETE FROM asset_files WHERE id=?', (file_id,))
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_evidence_path_escape_missing_reparse_duplicate_and_stale_rejected(self):
        service = Licenses(self.db); record = service.create_record(dict(subject=self.subject(), value=self.license_value(), confirmed=True))
        file_id = self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id=?', (self.id,)).fetchone()[0]
        item = dict(file_id=file_id, label='proof'); params = dict(record_id=record['id'], files=[item], expected_revision=1, confirmed=True)
        with patch('ai_asset_hub_core.mcp_queries.no_links', side_effect=ValueError('fixture reparse')):
            with self.assertRaises(LibraryError): service.save_evidence(params)
        self.db.connection.execute('UPDATE asset_files SET absolute_path=? WHERE id=?', (str(self.base / 'outside.png'), file_id))
        with self.assertRaises(LibraryError): service.save_evidence(params)
        self.db.connection.execute('UPDATE asset_files SET absolute_path=? WHERE id=?', (str(self.source / '나무.png'), file_id))
        with self.assertRaises(LibraryError): service.save_evidence({**params, 'files': [item, item]})
        service.save_evidence(params)
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'): service.save_evidence(params)
        self.assertEqual(service.get_record({'record_id': record['id']})['revision'], 2)

    def test_atomic_failure_and_immutable_conditions_history_no_ai_jobs(self):
        service = Licenses(self.db); record = service.create_record(dict(subject=self.subject(), value=self.license_value(), confirmed=True))
        before = self.db.connection.execute('SELECT * FROM provenance_licenses').fetchall()
        self.db.connection.execute("CREATE TRIGGER fixture_license_fail BEFORE INSERT ON provenance_history BEGIN SELECT RAISE(ABORT,'PRIVATE-ERROR'); END;")
        value = self.license_value(); value['terms'] = 'changed'
        response = self.call('license.update', record_id=record['id'], value=value, expected_revision=1, confirmed=True)
        self.assertEqual(response['error']['code'], 'DB_UNAVAILABLE'); self.assertNotIn('PRIVATE-ERROR', json.dumps(response))
        self.assertEqual(self.db.connection.execute('SELECT * FROM provenance_licenses').fetchall(), before)
        for table in ('analysis_jobs', 'asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        self.assertNotIn('PRIVATE-RECEIPT', json.dumps(self.db.connection.execute('SELECT details_redacted_json FROM audit_events').fetchall()))

    def test_maximum_conditions_are_bounded_and_not_accepted_as_ai_verified(self):
        value = self.license_value(); value.update(label='😀'*128, terms='😀'*1024, attribution='😀'*256, scope='😀'*128, note='😀'*256)
        service = Licenses(self.db); record = service.create_record(dict(subject=self.subject(), value=value, confirmed=True))
        full = self.call('license.get', record_id=record['id'], include_private=True, confirmed=True)
        self.assertLess(len(json.dumps(full, ensure_ascii=False).encode()), 16384)
        for invalid in ('allowed', 'ai_verified', True):
            value = self.license_value(); value['reviewStatus'] = invalid
            with self.assertRaises(LibraryError): service.create_record(dict(subject=self.subject(), value=value, confirmed=True))
