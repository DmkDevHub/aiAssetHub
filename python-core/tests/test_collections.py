import unittest
import json
import sqlite3
import test_annotations as fixtures
from ai_asset_hub_core.collections import Collections
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryError


class CollectionTests(unittest.TestCase):
    setUp=fixtures.AnnotationTests.setUp
    tearDown=fixtures.AnnotationTests.tearDown

    def group(self,name='fixture'):
        return Collections(self.db).group_create({'value':{'name':name,'description':'설명'}})

    def test_group_crud_multiple_membership_delete_preserves_assets_and_results(self):
        import test_analysis
        service=Collections(self.db);a=self.group(' 숲 ');b=self.group('effects')
        self.assertEqual(a['name'],'숲')
        test_analysis.AnalysisTests.history(self,self.id,'completed',active=True)
        before=self.db.connection.execute('SELECT * FROM asset_active_results').fetchall()
        saved=service.group_assign(dict(asset_id=self.id,group_ids=[a['id'],b['id']],expected_revision=0))
        self.assertEqual(set(saved['ids']),{a['id'],b['id']})
        service.group_update(dict(group_id=a['id'],value={'name':'new','description':''},expected_revision=1))
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.group_delete(dict(group_id=a['id'],expected_revision=1))
        service.group_delete(dict(group_id=a['id'],expected_revision=2))
        current=service.group_membership({'asset_id':self.id});self.assertEqual(current['ids'],[b['id']]);self.assertEqual(current['revision'],2)
        self.assertEqual(self.db.connection.execute('SELECT * FROM asset_active_results').fetchall(),before)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
        self.db.close();self.db=Database(self.base/'db.sqlite')
        self.assertEqual(Collections(self.db).group_membership({'asset_id':self.id}),current)

    def test_bad_ids_duplicate_membership_conflicts_and_rollback(self):
        from uuid import uuid4
        service=Collections(self.db);g=self.group()
        for ids in ([g['id'],g['id']],[str(uuid4())],['invented']):
            with self.assertRaises(LibraryError):service.group_assign(dict(asset_id=self.id,group_ids=ids,expected_revision=0))
        service.group_assign(dict(asset_id=self.id,group_ids=[g['id']],expected_revision=0))
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.group_assign(dict(asset_id=self.id,group_ids=[],expected_revision=0))
        self.db.connection.execute("CREATE TRIGGER fixture_fail_history BEFORE INSERT ON collection_history BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        with self.assertRaises(sqlite3.IntegrityError):service.group_assign(dict(asset_id=self.id,group_ids=[],expected_revision=1))
        self.assertEqual(service.group_membership({'asset_id':self.id})['ids'],[g['id']])
        self.assertEqual(service.group_membership({'asset_id':self.id})['revision'],1)

    def test_pages_validation_and_no_jobs(self):
        service=Collections(self.db)
        for i in range(5):self.group(str(i))
        cursor=None;ids=[]
        while True:
            page=service.group_list({'after_id':cursor});self.assertLessEqual(len(page['items']),2)
            ids.extend(g['id'] for g in page['items']);cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len(set(ids)),5)
        for value in ('','x'*129,'bad\nname'):
            with self.assertRaises(LibraryError):self.group(value)
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_v4_upgrade_preserves_assets_metadata_and_has_backup(self):
        import shutil
        from ai_asset_hub_core.database import migration_directory
        root=self.base/'v4';root.mkdir()
        for file in migration_directory().glob('*.sql'):
            if int(file.name[:3])<=4:shutil.copyfile(file,root/file.name)
        path=self.base/'legacy.sqlite';legacy=Database(path,migrations=root)
        legacy.connection.execute("INSERT INTO settings VALUES ('fixture','123','fixture')");legacy.close()
        upgraded=Database(path)
        try:
            self.assertTrue(upgraded.backup_path.is_file())
            self.assertEqual(upgraded.connection.execute("SELECT value_json FROM settings WHERE key='fixture'").fetchone()[0],'123')
            self.assertEqual(upgraded.connection.execute('SELECT count(*) FROM asset_groups').fetchone()[0],0)
        finally:upgraded.close()

    def test_hierarchy_moves_reject_self_cycle_and_promote_children_on_delete(self):
        service=Collections(self.db);a,b,c=[self.group(n) for n in ('a','b','c')]
        move=lambda g,p,r:service.group_move(dict(group_id=g,parent_id=p,expected_revision=r))
        move(b['id'],a['id'],1);move(c['id'],b['id'],1)
        for target in (a['id'],c['id']):
            with self.assertRaises(LibraryError):move(a['id'],target,1)
        self.assertIsNone(service.group(a['id'])['parentId'])
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):move(c['id'],None,1)
        result=service.group_delete(dict(group_id=b['id'],expected_revision=2))
        self.assertEqual(result['promotedChildren'],1)
        self.assertIsNone(service.group(c['id'])['parentId']);self.assertEqual(service.group(c['id'])['revision'],3)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_failed_hierarchy_change_rolls_back_tree_and_history(self):
        service=Collections(self.db);a=self.group();b=self.group('b')
        self.db.connection.execute("CREATE TRIGGER fixture_move_failure BEFORE INSERT ON collection_history WHEN NEW.action='move' BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        with self.assertRaises(sqlite3.IntegrityError):service.group_move(dict(group_id=b['id'],parent_id=a['id'],expected_revision=1))
        self.assertIsNone(service.group(b['id'])['parentId']);self.assertEqual(service.group(b['id'])['revision'],1)
