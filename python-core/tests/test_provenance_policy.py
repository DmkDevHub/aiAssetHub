import json
from pathlib import Path
import shutil
import sqlite3
import unittest
import test_annotations as fixtures
import test_creators as creator_fixtures
import test_licenses as license_fixtures
from ai_asset_hub_core.database import Database, DatabaseFailure, migration_directory
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.provenance import Provenance
from ai_asset_hub_core.provenance_policy import ProvenancePolicy
from ai_asset_hub_core.source_records import Sources
from ai_asset_hub_core.license_records import Licenses
from ai_asset_hub_core.libraries import LibraryError, LibraryService
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.mcp_queries import McpQueries


class ProvenancePolicyTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown
    subject = license_fixtures.LicenseTests.subject
    call = license_fixtures.LicenseTests.call
    source_value = license_fixtures.LicenseTests.source_value
    license_value = license_fixtures.LicenseTests.license_value
    creator_value = creator_fixtures.CreatorTests.value
    package = license_fixtures.LicenseTests.package

    def seed(self):
        creator = Creators(self.db).create({'value': self.creator_value()})
        Provenance(self.db).save_links(dict(subject=self.subject(), links=[dict(creator_id=creator['id'], role='creator')], expected_revision=0))
        value = self.source_value(); value['purchase'].update(amount='12345.6789', currency='KRW', purchasedOn='2024-02-29')
        source = Sources(self.db).create_record(dict(subject=self.subject(), value=value))
        value = self.license_value(); value['source_id'] = source['id']
        license = Licenses(self.db).create_record(dict(subject=self.subject(), value=value, confirmed=True))
        file_id = self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id=?', (self.id,)).fetchone()[0]
        license = Licenses(self.db).save_evidence(dict(record_id=license['id'], files=[dict(file_id=file_id, label='PRIVATE-PROOF')], expected_revision=1, confirmed=True))
        return creator, source, license

    def test_public_reads_exports_history_mcp_and_audit_exclude_all_private_fields(self):
        creator, source, license = self.seed(); policy = ProvenancePolicy(self.db)
        created = self.call('creator.create', value=self.creator_value())
        updated = self.call('creator.update', creator_id=created['data']['id'], value=self.creator_value(), expected_revision=1)
        disabled = self.call('creator.set_enabled', creator_id=created['data']['id'], enabled=False, expected_revision=2)
        outputs = [created, updated, disabled, self.call('creator.get', creator_id=creator['id']),
                   self.call('source.get', record_id=source['id']), self.call('license.get', record_id=license['id']),
                   McpQueries(self.db).detail({'asset_id': self.id}), self.db.connection.execute('SELECT details_redacted_json FROM audit_events').fetchall()]
        for kind in ('creators', 'sources', 'licenses'):
            outputs.append(policy.export(dict(subject=self.subject(), kind=kind, after_id=None)))
        for subject in (self.subject(), dict(kind='creator', id=creator['id'])):
            cursor = None
            while True:
                page = policy.history(dict(subject=subject, after_id=cursor)); outputs.append(page); cursor = page['next_cursor']
                if cursor is None: break
        for secret in ('private-contact@example.com', 'PRIVATE-TOKEN', 'PRIVATE-PROOF', 'PRIVATE-RECEIPT', '12345.6789', '2024-02-29'):
            self.assertNotIn(secret, json.dumps(outputs))
        for method, params in [('creator.get', dict(creator_id=creator['id'])), ('source.get', dict(record_id=source['id'])),
                               ('provenance.history', dict(subject=self.subject(), after_id=None)),
                               ('provenance.export', dict(subject=self.subject(), kind='sources', after_id=None))]:
            self.assertEqual(self.call(method, **params, include_private=True)['error']['code'], 'INVALID_PARAMS')
            self.assertEqual(self.call(method, **params, include_private=1, confirmed=True)['error']['code'], 'INVALID_PARAMS')
        full = policy.export(dict(subject=self.subject(), kind='sources', after_id=None, include_private=True, confirmed=True))
        self.assertIn('PRIVATE-TOKEN', json.dumps(full))
        self.assertEqual(self.call('creator.get', creator_id=creator['id'], include_private=True, confirmed=True)['data']['contact'], self.creator_value()['contact'])

    def test_history_pages_preserve_before_after_revisions_and_private_state_across_reopen(self):
        _, source, _ = self.seed(); value = self.source_value(); value['purchase'].update(amount='5', currency='KRW')
        Sources(self.db).update_record(dict(record_id=source['id'], value=value, expected_revision=1))
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        page = ProvenancePolicy(self.db).history(dict(subject=self.subject(), after_id=None, include_private=True, confirmed=True))
        event = page['items'][0]
        self.assertEqual(event['revision'], 2); self.assertEqual(event['actor'], 'user')
        self.assertEqual(event['before']['value']['value']['purchase']['amount'], '12345.6789')
        self.assertEqual(event['after']['value']['value']['purchase']['amount'], '5')
        self.assertIsNotNone(page['next_cursor'])
        for statement in ('DELETE FROM provenance_history', "UPDATE provenance_history SET action='fake'"):
            with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute(statement)

    def test_creator_delete_requires_fresh_review_unlink_and_cannot_resurrect(self):
        creator, _, _ = self.seed(); policy = ProvenancePolicy(self.db)
        plan = policy.delete_creator_preview({'creator_id': creator['id']}); self.assertFalse(plan['canDelete'])
        with self.assertRaises(LibraryError): policy.delete_creator(dict(plan=plan, confirmed=True))
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute('UPDATE creators SET deleted=1 WHERE id=?', (creator['id'],))
        Provenance(self.db).save_links(dict(subject=self.subject(), links=[], expected_revision=1))
        plan = policy.delete_creator_preview({'creator_id': creator['id']})
        value = self.creator_value(); value['name'] = 'changed'
        Creators(self.db).update(dict(creator_id=creator['id'], value=value, expected_revision=1))
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'): policy.delete_creator(dict(plan=plan, confirmed=True))
        plan = policy.delete_creator_preview({'creator_id': creator['id']})
        result = policy.delete_creator(dict(plan=plan, confirmed=True)); self.assertTrue(result['deleted'])
        with self.assertRaises(LibraryError): Creators(self.db).set_enabled(dict(creator_id=creator['id'], enabled=True, expected_revision=result['revision']))
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute('DELETE FROM creators WHERE id=?', (creator['id'],))
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_source_license_delete_reviews_refs_and_retains_fk_history_and_evidence(self):
        _, source, license = self.seed(); sources, licenses = Sources(self.db), Licenses(self.db)
        preview = sources.delete_preview({'record_id': source['id']}); self.assertEqual(preview['references'], 1)
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'):
            sources.delete_record(dict(record_id=source['id'], expected_revision=1, confirmed=True))
        result = sources.delete_record(dict(record_id=source['id'], expected_revision=1, expected_references=1, confirmed=True))
        self.assertFalse(result['enabled']); self.assertEqual(licenses.record(license['id'])['value']['source_id'], source['id'])
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'):
            licenses.delete_record(dict(record_id=license['id'], expected_revision=2, confirmed=True))
        result = licenses.delete_record(dict(record_id=license['id'], expected_revision=2, expected_references=1, confirmed=True))
        self.assertFalse(result['enabled']); self.assertEqual(len(licenses.record(license['id'])['evidence']), 1)
        for table in ('provenance_sources', 'provenance_licenses'):
            with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute('DELETE FROM ' + table)
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("UPDATE license_evidence SET label='tampered'")
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_delete_review_race_and_late_history_failure_roll_back_tombstone(self):
        creator = Creators(self.db).create({'value': self.creator_value()}); policy = ProvenancePolicy(self.db)
        plan = policy.delete_creator_preview({'creator_id': creator['id']})
        Provenance(self.db).save_links(dict(subject=self.subject(), links=[dict(creator_id=creator['id'], role='creator')], expected_revision=0))
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'): policy.delete_creator(dict(plan=plan, confirmed=True))
        Provenance(self.db).save_links(dict(subject=self.subject(), links=[], expected_revision=1))
        plan = policy.delete_creator_preview({'creator_id': creator['id']})
        before = Creators(self.db).creator(creator['id'])
        self.db.connection.execute("CREATE TRIGGER fixture_policy_failure BEFORE INSERT ON provenance_history BEGIN SELECT RAISE(ABORT,'private-fixture'); END;")
        response = self.call('creator.delete', plan=plan, confirmed=True)
        self.assertEqual(response['error']['code'], 'DB_UNAVAILABLE')
        self.assertEqual(Creators(self.db).creator(creator['id']), before)

    def test_archived_package_retains_links_until_explicit_unlink_and_blocks_new_links(self):
        from ai_asset_hub_core.packages import Packages
        creator = Creators(self.db).create({'value': self.creator_value()}); package = self.package()
        subject = dict(kind='package', id=package['id']); service = Provenance(self.db)
        link = dict(creator_id=creator['id'], role='creator')
        service.save_links(dict(subject=subject, links=[link], expected_revision=0))
        Packages(self.db).package_delete(dict(package_id=package['id'], expected_revision=1))
        self.assertEqual(service.links({'subject': subject})['links'], [link])
        with self.assertRaises(LibraryError):
            service.save_links(dict(subject=subject, links=[dict(creator_id=creator['id'], role='distributor')], expected_revision=1))
        service.save_links(dict(subject=subject, links=[], expected_revision=1))
        self.assertTrue(ProvenancePolicy(self.db).delete_creator_preview({'creator_id': creator['id']})['canDelete'])

    def legacy(self):
        self.db.close(); scripts = self.base / 'v7-migrations'; scripts.mkdir()
        for source in sorted(migration_directory().glob('*.sql'))[:7]: shutil.copyfile(source, scripts / source.name)
        self.db = Database(self.base / 'v7.sqlite', migrations=scripts)
        library = LibraryService(self.db).register({'path': str(self.source)})['library']['id']
        AssetService(self.db).scan({'library_id': library}); self.id = AssetService(self.db).list({})['items'][0]['id']
        self.db.connection.execute("INSERT INTO creators VALUES ('legacy-creator','legacy','person','','','','legacy-private','','',1,1)")
        import test_analysis
        test_analysis.AnalysisTests.history(self, self.id, 'completed', active=True)
        return scripts

    def test_v7_upgrade_preserves_all_old_columns_rows_backup_and_no_invented_history(self):
        self.legacy()
        tables = [r[0] for r in self.db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
        columns = {t: ','.join('"' + r[1] + '"' for r in self.db.connection.execute('PRAGMA table_info(' + t + ')')) for t in tables}
        before = {t: self.db.connection.execute('SELECT ' + columns[t] + ' FROM ' + t).fetchall() for t in tables}
        self.db.close(); self.db = Database(self.base / 'v7.sqlite')
        self.assertEqual(self.db.health()['schema_version'], 11)
        self.assertEqual(before, {t: self.db.connection.execute('SELECT ' + columns[t] + ' FROM ' + t).fetchall() for t in tables})
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM provenance_history').fetchone()[0], 0)
        backup = sqlite3.connect(self.db.backup_path)
        try: self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 7)
        finally: backup.close()
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')

    def test_failed_final_migration_restores_v7_without_partial_tables_or_deleted_column(self):
        scripts = self.legacy(); self.db.close()
        for source in sorted(migration_directory().glob('*.sql'))[7:]: shutil.copyfile(source, scripts / source.name)
        with (scripts / '011_provenance_policy.sql').open('a', encoding='utf-8') as handle: handle.write('\nINVALID SQL;\n')
        with self.assertRaises(DatabaseFailure): Database(self.base / 'v7.sqlite', migrations=scripts)
        connection = sqlite3.connect(self.base / 'v7.sqlite')
        try:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 7)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='provenance_sources'").fetchone())
            self.assertNotIn('deleted', [r[1] for r in connection.execute('PRAGMA table_info(creators)')])
        finally: connection.close()

    def test_private_history_and_export_stay_bounded_without_losing_db_original(self):
        value = self.source_value(); value.update(site='😀'*128, productName='😀'*256)
        for key in ('originalUrl', 'productUrl', 'downloadUrl'): value[key] = 'https://example.com/' + '😀'*490
        record = Sources(self.db).create_record(dict(subject=self.subject(), value=value))
        policy = ProvenancePolicy(self.db)
        history = self.call('provenance.history', subject=self.subject(), after_id=None, include_private=True, confirmed=True)
        self.assertTrue(history['data']['items'][0]['after']['truncated'])
        self.assertLess(len(json.dumps(history, ensure_ascii=False).encode()), 16384)
        export = self.call('provenance.export', subject=self.subject(), kind='sources', after_id=None, include_private=True, confirmed=True)
        self.assertLess(len(json.dumps(export, ensure_ascii=False).encode()), 16384)
        self.assertEqual(Sources(self.db).record(record['id'])['value'], value)
        for table in ('analysis_jobs', 'asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
