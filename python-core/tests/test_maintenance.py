import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ai_asset_hub_core.runtime import CoreRuntime
from ai_asset_hub_core.database import DatabaseFailure
from ai_asset_hub_core.maintenance import Backups,restore,digest
from ai_asset_hub_core.libraries import LibraryError


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        folder=Path(__file__).resolve().parents[2]/'.artifacts/maintenance-tests';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.root=Path(self.temp.name)/'data';self.runtime=CoreRuntime(self.root,'development')
        self.db=self.runtime.database;self.service=Backups(self.db)

    def tearDown(self):self.runtime.close();self.temp.cleanup()

    def write(self,value):self.db.connection.execute("INSERT INTO settings VALUES ('fixture',?,'now') ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",(json.dumps(value),))

    def test_wal_backup_restore_preserves_snapshot_and_pre_restore_database(self):
        self.write(dict(note='private original'));backup=self.service.create(dict(confirmed=True));self.write(dict(note='newer'))
        self.assertEqual(self.service.list({})['items'][0]['id'],backup['id']);snapshot=self.root/'backups'/(backup['id']+'.sqlite');original=digest(snapshot)
        with self.assertRaisesRegex(DatabaseFailure,'DATA_IN_USE'):restore(self.root,'development',backup['id'],True)
        self.runtime.close();result=restore(self.root,'development',backup['id'],True)
        self.assertTrue(result['restored']);self.assertFalse(result['analysisResumed'])
        self.runtime=CoreRuntime(self.root,'development');self.db=self.runtime.database
        self.assertEqual(json.loads(self.db.connection.execute("SELECT value_json FROM settings WHERE key='fixture'").fetchone()[0]),dict(note='private original'))
        rollback=self.root/'backups'/result['rollbackId']/'asset_hub.sqlite';old=sqlite3.connect(rollback)
        try:self.assertEqual(json.loads(old.execute("SELECT value_json FROM settings WHERE key='fixture'").fetchone()[0]),dict(note='newer'))
        finally:old.close()
        self.assertEqual(digest(snapshot),original)

    def test_corrupt_hash_and_unapproved_restore_leave_current_bytes_unchanged(self):
        self.write('keep');backup=self.service.create(dict(confirmed=True));self.runtime.close();current=self.root/'asset_hub.sqlite';before=current.read_bytes()
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):restore(self.root,'development',backup['id'],False)
        (self.root/'backups'/(backup['id']+'.sqlite')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(LibraryError,'BACKUP_INVALID'):restore(self.root,'development',backup['id'],True)
        self.assertEqual(current.read_bytes(),before)

    def test_failed_atomic_replace_rolls_back_original_wal_and_shm(self):
        self.write('original');backup=self.service.create(dict(confirmed=True));self.runtime.close();current=self.root/'asset_hub.sqlite';before=current.read_bytes()
        wal=Path(str(current)+'-wal');wal.write_bytes(b'crash WAL fixture');shm=Path(str(current)+'-shm');shm.write_bytes(b'crash SHM fixture')
        real=os.replace
        def replace(source,target):
            if Path(source).name.startswith('.restore-'):raise OSError('PRIVATE')
            return real(source,target)
        with patch('ai_asset_hub_core.maintenance.os.replace',side_effect=replace):
            with self.assertRaisesRegex(LibraryError,'BACKUP_INVALID'):restore(self.root,'development',backup['id'],True)
        self.assertEqual(current.read_bytes(),before);self.assertEqual(wal.read_bytes(),b'crash WAL fixture');self.assertEqual(shm.read_bytes(),b'crash SHM fixture')
        wal.unlink();shm.unlink() # owned invalid fixture; prevents SQLite opening an intentionally bogus WAL at teardown

    def test_migration_backup_readonly_schema_and_path_validation(self):
        self.write('keep');backup=self.service.create(dict(confirmed=True));snapshot=self.root/'backups'/(backup['id']+'.sqlite')
        with patch('ai_asset_hub_core.maintenance.no_links',side_effect=ValueError('private path')):
            with self.assertRaises((ValueError,LibraryError)):self.service.create(dict(confirmed=True))
        self.assertTrue(snapshot.is_file())
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):self.service.create(dict(confirmed=1))

    def test_manifest_schema_mismatch_is_rejected_without_replacing_current_database(self):
        self.write('keep');backup=self.service.create(dict(confirmed=True));self.runtime.close()
        path=self.root/'backups'/(backup['id']+'.json');value=json.loads(path.read_text());value['schemaVersion']+=1;path.write_text(json.dumps(value))
        current=self.root/'asset_hub.sqlite';before=current.read_bytes()
        with self.assertRaisesRegex(LibraryError,'BACKUP_INVALID'):restore(self.root,'development',backup['id'],True)
        self.assertEqual(current.read_bytes(),before)

    def test_backups_are_newest_first_by_creation_time_across_pages_not_random_uuid(self):
        from datetime import datetime,timezone,timedelta
        from uuid import UUID
        identifiers=[]
        for index in range(12):
            with patch('ai_asset_hub_core.maintenance.uuid4',return_value=UUID(int=2**128-1-index)):
                value=self.service.create(dict(confirmed=True))
            identifiers.append(value['id']);path=self.root/'backups'/(value['id']+'.json')
            value['createdAt']=(datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(seconds=index)).isoformat();path.write_text(json.dumps(value))
        first=self.service.list({});second=self.service.list(dict(after_id=first['next_cursor']))
        self.assertEqual([v['id'] for v in first['items']+second['items']],list(reversed(identifiers)));self.assertIsNone(second['next_cursor'])
