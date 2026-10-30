import json
import shutil
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations as fixtures
from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.database import Database, DatabaseFailure, migration_directory
from ai_asset_hub_core.libraries import LibraryError, LibraryService
from ai_asset_hub_core.assets import AssetService


class CreatorTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown

    def value(self):
        return dict(name='  제작자 Ａ  ', kind='person', brand='브랜드',
                    homepageUrl='https://example.com/home', profileUrl='https://example.com/seller',
                    contact='private-contact@example.com', country='대한민국', description='제작 주체 설명')

    def call(self, method, **params):
        return CoreApplication(self.db).handle({'request_id': str(uuid4()), 'method': method, 'params': params})

    def test_types_normalization_persistence_and_no_asset_or_ai_effects(self):
        import test_analysis
        test_analysis.AnalysisTests.history(self, self.id, 'completed', active=True)
        tables = ('assets', 'asset_files', 'analysis_jobs', 'analysis_runs', 'analysis_results',
                  'asset_active_results', 'asset_embeddings', 'search_documents', 'asset_user_annotations')
        before = {t: self.db.connection.execute('SELECT * FROM ' + t).fetchall() for t in tables}
        with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')), patch('socket.create_connection', side_effect=AssertionError('Unexpected network')):
            records = []
            for kind in ('person', 'team', 'company'):
                value = self.value(); value['kind'] = kind
                result = self.call('creator.create', value=value)
                self.assertTrue(result['ok'], result)
                records.append(result['data'])
        self.assertEqual({r['kind'] for r in records}, {'person', 'team', 'company'})
        self.assertEqual(len({r['id'] for r in records}), 3)
        self.assertEqual(records[0]['name'], '제작자 A')
        self.assertTrue(records[0]['enabled'])
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        for record in records:
            self.assertEqual(self.call('creator.get', creator_id=record['id'])['data'], record)
        self.assertEqual(before, {t: self.db.connection.execute('SELECT * FROM ' + t).fetchall() for t in tables})
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_invalid_input_and_urls_are_rejected_without_records_or_private_errors(self):
        service = Creators(self.db)
        invalid = [('name', ''), ('name', ' '), ('name', 'x'*129), ('kind', 'brand'), ('kind', []),
                   ('name', '\ud800'), ('contact', 'a\nb'), ('description', '\x00'), ('brand', True),
                   ('contact', 'x'*257), ('country', 'x'*65), ('description', 'x'*513)]
        for field in ('homepageUrl', 'profileUrl'):
            invalid.extend((field, url) for url in ('http://example.com', 'javascript:alert(1)', 'file:///C:/private',
                'https://user:secret@example.com', 'https://example.com?token=secret', 'https://example.com#secret',
                'https://example.com?', 'https://example.com#', 'https://example.com\\evil', 'https://bad host',
                'https://example.com:99999', 'https://[bad]', 'https://%65xample.com', 'https://-bad.example', 'https://', 'x'*513))
        for field, bad in invalid:
            with self.subTest(field=field, bad=repr(bad)):
                value = self.value(); value[field] = bad
                response = self.call('creator.create', value=value)
                self.assertEqual(response['error']['code'], 'INVALID_PARAMS')
                self.assertNotIn('private-contact', json.dumps(response))
        for value in (None, {}, {**self.value(), 'extra': 'secret'}):
            with self.assertRaises(LibraryError): service.create({'value': value})
        for url in ('', 'https://예시.한국/판매자', 'https://example.com:443/a', 'https://[::1]/profile'):
            self.assertEqual(service.url(url), url)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM creators').fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM audit_events').fetchone()[0], 0)

    def test_revision_conflicts_between_connections_preserve_current_values(self):
        service = Creators(self.db); original = service.create({'value': self.value()})
        other = Database(self.base / 'db.sqlite'); self.addCleanup(other.close)
        stale = Creators(other).get({'creator_id': original['id']})
        value = self.value(); value.update(name='수정', contact='changed@example.com')
        current = service.update(dict(creator_id=original['id'], value=value, expected_revision=1))
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'):
            Creators(other).update(dict(creator_id=stale['id'], value=self.value(), expected_revision=stale['revision']))
        for revision in (True, '2', -1):
            with self.assertRaisesRegex(LibraryError, 'INVALID_PARAMS'):
                service.update(dict(creator_id=current['id'], value=self.value(), expected_revision=revision))
        self.assertEqual(service.get({'creator_id': current['id']}), current)
        self.assertEqual(current['revision'], 2)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM audit_events').fetchone()[0], 2)
        other.close()

    def test_disable_reenable_and_private_fields_do_not_leak_into_list_or_audit(self):
        service = Creators(self.db); record = service.create({'value': self.value()})
        disabled = service.set_enabled(dict(creator_id=record['id'], enabled=False, expected_revision=1))
        self.assertEqual(service.list(dict(after_id=None, include_disabled=False))['items'], [])
        summary = service.list(dict(after_id=None, include_disabled=True))['items'][0]
        self.assertFalse(summary['enabled']); self.assertEqual(summary['id'], record['id'])
        for key in ('contact', 'homepageUrl', 'profileUrl', 'description'):
            self.assertNotIn(key, summary)
        self.assertEqual(service.get({'creator_id': record['id']}), disabled)
        self.assertEqual(service.set_enabled(dict(creator_id=record['id'], enabled=False, expected_revision=2)), disabled)
        enabled = service.set_enabled(dict(creator_id=record['id'], enabled=True, expected_revision=2))
        self.assertEqual(enabled['revision'], 3)
        audit = self.db.connection.execute('SELECT details_redacted_json FROM audit_events').fetchall()
        self.assertEqual(len(audit), 3)
        text = json.dumps(audit)
        for private in ('private-contact@example.com', 'https://example.com', '제작 주체 설명'):
            self.assertNotIn(private, text)
        self.assertEqual(self.call('mcp.audit')['data']['items'], [])
        self.assertEqual(self.call('creator.delete', creator_id=record['id'])['error']['code'], 'METHOD_NOT_FOUND')
        self.assertEqual(self.call('creator.set_enabled', creator_id=record['id'], enabled=1, expected_revision=3)['error']['code'], 'INVALID_PARAMS')

    def test_bounded_keyset_pages_and_maximum_unicode_envelope(self):
        service = Creators(self.db); identifiers = []
        for _ in range(5):
            value = self.value(); value.update(name='😀'*128, brand='😀'*128, country='😀'*64,
                                              description='😀'*512, contact='😀'*256, homepageUrl='', profileUrl='')
            result = self.call('creator.create', value=value)
            self.assertLess(len(json.dumps(result, ensure_ascii=False).encode()), 16384)
            identifiers.append(result['data']['id'])
        seen = []; cursor = None
        while True:
            page = service.list(dict(after_id=cursor, include_disabled=False))
            self.assertLessEqual(len(page['items']), 2)
            seen.extend(row['id'] for row in page['items']); cursor = page['next_cursor']
            if cursor is None: break
        self.assertEqual(seen, sorted(identifiers))
        for params in (dict(after_id='bad', include_disabled=False), dict(after_id=str(uuid4()), include_disabled=True),
                       dict(after_id=None, include_disabled=1), {}):
            with self.assertRaises(LibraryError): service.list(params)

    def test_audit_failure_rolls_back_all_writes_and_returns_redacted_error(self):
        service = Creators(self.db); original = service.create({'value': self.value()})
        self.db.connection.execute("CREATE TRIGGER fixture_creator_failure BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'private-sensitive-failure'); END;")
        value = self.value(); value['name'] = 'changed'
        for method, params in (
            ('creator.create', dict(value=value)),
            ('creator.update', dict(creator_id=original['id'], value=value, expected_revision=1)),
            ('creator.set_enabled', dict(creator_id=original['id'], enabled=False, expected_revision=1))):
            response = self.call(method, **params)
            self.assertEqual(response['error']['code'], 'DB_UNAVAILABLE')
            self.assertNotIn('private-sensitive', json.dumps(response))
            self.assertEqual(service.creator(original['id']), original)
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM creators').fetchone()[0], 1)
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM audit_events').fetchone()[0], 1)

    def legacy(self):
        self.db.close()
        scripts = self.base / 'v6-migrations'; scripts.mkdir()
        for source in sorted(migration_directory().glob('*.sql'))[:6]: shutil.copyfile(source, scripts / source.name)
        self.db = Database(self.base / 'v6.sqlite', migrations=scripts)
        library = LibraryService(self.db).register({'path': str(self.source)})['library']['id']
        AssetService(self.db).scan({'library_id': library})
        self.id = AssetService(self.db).list({})['items'][0]['id']
        return scripts

    def test_v6_upgrade_backup_preserves_all_existing_tables_and_original(self):
        self.legacy()
        import test_analysis
        test_analysis.AnalysisTests.history(self, self.id, 'completed', active=True)
        tables = [r[0] for r in self.db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
        before = {t: self.db.connection.execute('SELECT * FROM ' + t).fetchall() for t in tables}
        self.db.close(); self.db = Database(self.base / 'v6.sqlite')
        self.assertEqual(self.db.health()['schema_version'], len(list(migration_directory().glob('*.sql'))))
        self.assertEqual(before, {t: self.db.connection.execute('SELECT * FROM ' + t).fetchall() for t in tables})
        backup = sqlite3.connect(self.db.backup_path)
        try: self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 6)
        finally: backup.close()
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_v7_migration_failure_rolls_back_without_partial_creator_table(self):
        scripts = self.legacy(); before = self.db.connection.execute('SELECT * FROM assets').fetchall()
        self.db.close()
        script = migration_directory() / '007_creators.sql'
        (scripts / script.name).write_text(script.read_text(encoding='utf-8') + '\nINVALID SQL;\n', encoding='utf-8')
        with self.assertRaises(DatabaseFailure): Database(self.base / 'v6.sqlite', migrations=scripts)
        connection = sqlite3.connect(self.base / 'v6.sqlite')
        try:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 6)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='creators'").fetchone())
            self.assertEqual(connection.execute('SELECT * FROM assets').fetchall(), before)
        finally: connection.close()

    def test_database_constraints_reject_invalid_kind_lengths_and_state(self):
        service = Creators(self.db); record = service.create({'value': self.value()})
        for column, value in (('kind', 'publisher'), ('enabled', 2), ('revision', 0), ('name', ''), ('contact', 'x'*257)):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.connection.execute('UPDATE creators SET ' + column + '=? WHERE id=?', (value, record['id']))
        self.assertEqual(service.creator(record['id']), record)
