from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.database import Database, DatabaseFailure, migration_directory


LATEST=len(list(migration_directory().glob('*.sql')))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[2] / '.artifacts' / 'core-tests'
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '한글 데이터' / 'asset_hub.sqlite'

    def open(self, **kwargs):
        database = Database(self.path, **kwargs)
        self.addCleanup(database.close)
        return database

    def test_initial_schema_is_empty_measured_and_idempotent(self):
        database = self.open()
        health = database.health()
        self.assertEqual(health['status'], 'ready')
        self.assertEqual(health['schema_version'], LATEST)
        self.assertEqual(health['sqlite_version'], sqlite3.sqlite_version)
        self.assertEqual(health['journal_mode'], 'wal')
        tables = [row[0] for row in database.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertEqual(len(tables), 57)
        for table in tables:
            if table not in ('schema_migrations','classification_dictionaries','classification_terms') and not table.startswith(('asset_fts','catalog_fts')):
                self.assertEqual(database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        self.assertEqual(database.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        database.close()
        reopened = self.open()
        self.assertEqual(reopened.connection.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0], LATEST)
        self.assertIsNone(reopened.backup_path)

    def test_python_writes_persist_after_reopen_with_unicode(self):
        database = self.open()
        database.connection.execute("INSERT INTO settings VALUES (?, ?, ?)", ('fixture-theme', '{"이름":"숲"}', 'fixture-time'))
        database.close()
        reopened = self.open()
        self.assertEqual(reopened.connection.execute('SELECT value_json FROM settings WHERE key=?', ('fixture-theme',)).fetchone()[0], '{"이름":"숲"}')

    def test_foreign_keys_json_and_model_default_off(self):
        database = self.open()
        with self.assertRaises(sqlite3.IntegrityError):
            database.connection.execute("INSERT INTO assets(id,library_root_id,display_name) VALUES ('fixture-a','missing','fixture')")
        with self.assertRaises(sqlite3.IntegrityError):
            database.connection.execute("INSERT INTO settings VALUES ('fixture','invalid-json','fixture-time')")
        database.connection.execute("INSERT INTO model_providers VALUES ('fixture-provider','fixture','external')")
        database.connection.execute("INSERT INTO model_registry(id,provider_id,model_id,modalities_json,capabilities_json) VALUES ('fixture-model','fixture-provider','fixture','[]','{}')")
        self.assertEqual(database.connection.execute('SELECT enabled FROM model_registry').fetchone()[0], 0)

    def test_failed_migration_rolls_back_and_keeps_pre_migration_backup(self):
        database = self.open()
        database.connection.execute("INSERT INTO settings VALUES ('fixture','123','fixture-time')")
        database.close()
        migrations = Path(self.temp.name) / 'migrations'
        shutil.copytree(migration_directory(), migrations)
        (migrations / f'{LATEST+1:03}_broken.sql').write_text('CREATE TABLE should_rollback (id TEXT);\nINVALID SQL;\n', encoding='utf-8')
        with self.assertRaises(DatabaseFailure):
            self.open(migrations=migrations)
        reopened = self.open()
        self.assertEqual(reopened.health()['schema_version'], LATEST)
        self.assertEqual(reopened.connection.execute("SELECT value_json FROM settings WHERE key='fixture'").fetchone()[0], '123')
        self.assertFalse(reopened.connection.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchall())
        backups = list((self.path.parent / 'backups').glob('*.sqlite'))
        self.assertEqual(len(backups), 1)
        backup = sqlite3.connect(backups[0])
        try:
            self.assertEqual(backup.execute("SELECT value_json FROM settings WHERE key='fixture'").fetchone()[0], '123')
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], LATEST)
        finally:
            backup.close()

    def test_successful_upgrade_preserves_data_and_records_checksum(self):
        self.open().close()
        migrations = Path(self.temp.name) / 'migrations'
        shutil.copytree(migration_directory(), migrations)
        (migrations / f'{LATEST+1:03}_addition.sql').write_text('CREATE TABLE fixture_upgrade (id TEXT PRIMARY KEY);\n', encoding='utf-8')
        database = self.open(migrations=migrations)
        self.assertEqual(database.health()['schema_version'], LATEST+1)
        self.assertTrue(database.backup_path.is_file())
        self.assertEqual(len(database.connection.execute('SELECT checksum FROM schema_migrations WHERE version=(SELECT max(version) FROM schema_migrations)').fetchone()[0]), 64)

    def test_corrupt_foreign_and_incompatible_databases_are_not_replaced(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'fixture-non-sqlite-private-data')
        before = self.path.read_bytes()
        with self.assertRaises(DatabaseFailure):
            self.open()
        self.assertEqual(self.path.read_bytes(), before)
        self.path.unlink() # Only a test-owned temporary fixture.
        connection = sqlite3.connect(self.path)
        connection.execute('CREATE TABLE unrelated (id TEXT)')
        connection.close()
        with self.assertRaises(DatabaseFailure) as failure:
            self.open()
        self.assertEqual(failure.exception.code, 'DB_SCHEMA_UNKNOWN')

    def test_checksum_change_is_rejected_without_migration(self):
        self.open().close()
        migrations = Path(self.temp.name) / 'migrations'
        shutil.copytree(migration_directory(), migrations)
        with (migrations / '001_initial.sql').open('a', encoding='utf-8') as file:
            file.write('-- fixture changed migration\n')
        with self.assertRaises(DatabaseFailure) as failure:
            self.open(migrations=migrations)
        self.assertEqual(failure.exception.code, 'DB_SCHEMA_INCOMPATIBLE')
        self.assertEqual(self.open().health()['schema_version'], LATEST)

    def test_database_health_failure_is_not_disguised_as_ready(self):
        database = self.open()
        application = CoreApplication(database)
        self.assertEqual(application.health()['database']['status'], 'ready')
        database.close()
        self.assertEqual(application.health()['database'], {'status': 'error', 'error_code': 'DB_UNAVAILABLE'})
        with self.assertRaises(DatabaseFailure):
            Database('relative-fixture.sqlite')

    def test_failed_reanalysis_keeps_success_and_user_annotations(self):
        db = self.open().connection
        db.execute("INSERT INTO library_roots(id,display_name,absolute_path) VALUES ('fixture-root','fixture','fixture-path')")
        for asset in ['fixture-a', 'fixture-b']:
            db.execute("INSERT INTO assets(id,library_root_id,display_name) VALUES (?,'fixture-root','fixture')", (asset,))
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES ('fixture-job','fixture-request','{}','{}',1,'running','fixture-time','fixture-user')")
        db.execute("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES ('fixture-job','fixture-a','running')")
        for run, status in [('fixture-success','completed'), ('fixture-failure','failed')]:
            db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,'fixture-job','fixture-a','{}','fixture-fingerprint',?,'fixture-time')", (run, status))
        db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES ('fixture-result','fixture-success','fixture-a','fixture-result','[]','{}','fixture-time')")
        db.execute("INSERT INTO asset_active_results VALUES ('fixture-a','fixture-result','fixture-time')")
        db.execute("INSERT INTO asset_user_annotations VALUES ('fixture-a','내 이름','내 설명','fixture-time')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES ('fixture-invalid','fixture-failure','fixture-a','fixture','[]','{}','fixture-time')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO asset_active_results VALUES ('fixture-b','fixture-result','fixture-time')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE analysis_results SET description='changed'")
        self.assertEqual(db.execute('SELECT analysis_result_id FROM asset_active_results').fetchone()[0], 'fixture-result')
        self.assertEqual(db.execute('SELECT description_override FROM asset_user_annotations').fetchone()[0], '내 설명')
        text=db.execute("SELECT searchable_text FROM search_documents WHERE asset_id='fixture-a'").fetchone()[0]
        self.assertIn('fixture-result',text)
        self.assertIn('내 설명',text)
        db.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")


if __name__ == '__main__':
    unittest.main()
