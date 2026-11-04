import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
import test_catalog_query
from ai_asset_hub_core.smart_groups import SmartGroups,SCHEMA
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.application import CoreApplication


class SmartGroupTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    extra_assets=test_catalog_query.CatalogQueryTests.extra_assets

    def create(self,query='',filters=None,refs=None):
        return SmartGroups(self.db).save(dict(group_id=None,name='저장 조건',description='',definition=dict(schema=SCHEMA,query=query,criteria=filters or {},include_groups=refs or []),expected_revision=0))

    def evaluate(self,id,**extra):return SmartGroups(self.db).evaluate(dict(group_id=id,query='',criteria={},sort='source',after_id=None,**extra))

    def test_dynamic_evaluation_intersection_is_read_only_and_no_inference_or_files(self):
        service=SmartGroups(self.db);a=self.create(filters={'tag':'숲'});b=self.create(query='나무',refs=[a['id']])
        self.assertEqual(self.evaluate(b['id'])['ids'],[])
        self.service.tags(dict(asset_id=self.id,add=['숲'],remove=[]))
        before='\n'.join(self.db.connection.iterdump());count=self.db.connection.total_changes
        with patch('builtins.open',side_effect=AssertionError('no file')),patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no model')),patch('ai_asset_hub_core.assets.AssetService.scan',side_effect=AssertionError('no scan')):
            result=self.evaluate(b['id'])
        self.assertEqual(result['ids'],[self.id]);self.assertFalse(result['inferenceCalled'])
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before);self.assertEqual(self.db.connection.total_changes,count)
        self.service.tags(dict(asset_id=self.id,add=[],remove=['숲']));self.assertEqual(self.evaluate(b['id'])['ids'],[])

    def test_cycles_missing_references_and_deleting_referenced_group_leave_data_unchanged(self):
        a=self.create();b=self.create(refs=[a['id']]);service=SmartGroups(self.db)
        before='\n'.join(self.db.connection.iterdump())
        request=dict(group_id=a['id'],name='순환',description='',definition={**a['definition'],'include_groups':[b['id']]},expected_revision=1)
        with self.assertRaises(LibraryError):service.save(request)
        with self.assertRaises(LibraryError):service.delete(dict(group_id=a['id'],expected_revision=1))
        with self.assertRaises(LibraryError):self.create(refs=[str(uuid4())])
        for filters in ({'group_ids':[str(uuid4())]},{'library_id':str(uuid4())},{'package_ids':[str(uuid4())]},{'types':['A99']},{'styles':['invented']}):
            with self.assertRaises(LibraryError):self.create(filters=filters)
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)
        service.delete(dict(group_id=b['id'],expected_revision=1));service.delete(dict(group_id=a['id'],expected_revision=1))
        self.assertEqual(service.list(dict(after_id=None))['items'],[])

    def test_versions_conflicts_reopen_and_late_sql_failure_preserve_history(self):
        row=self.create(query='나무');second=Database(self.base/'db.sqlite')
        try:
            request=dict(group_id=row['id'],name='바뀜',description='',definition=row['definition'],expected_revision=1)
            SmartGroups(second).save(request)
            with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):SmartGroups(self.db).save(request)
        finally:second.close()
        self.db.close();self.db=Database(self.base/'db.sqlite');service=SmartGroups(self.db)
        self.assertEqual(service.get(dict(group_id=row['id']))['name'],'바뀜')
        self.db.connection.execute("CREATE TRIGGER fixture_smart_failure BEFORE INSERT ON collection_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
        before='\n'.join(self.db.connection.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.create(query='failed')
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_pagination_stamps_filter_changes_and_graph_depth_are_bounded(self):
        self.extra_assets(201);row=self.create();service=SmartGroups(self.db)
        first=self.evaluate(row['id']);self.assertEqual(len(first['ids']),200)
        last=service.evaluate(dict(group_id=row['id'],query='',criteria={},sort='source',after_id=first['next_cursor']))
        self.assertEqual(len(last['ids']),2);self.assertIsNone(last['next_cursor'])
        self.service.tags(dict(asset_id=self.id,add=['changed'],remove=[]))
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.evaluate(dict(group_id=row['id'],query='',criteria={},sort='source',after_id=first['next_cursor']))
        for _ in range(7):row=self.create(refs=[row['id']])
        with self.assertRaises(LibraryError):self.create(refs=[row['id']])

    def test_core_dispatch_rejects_schema_and_preserves_original(self):
        app=CoreApplication(self.db)
        result=app.handle(dict(request_id=str(uuid4()),method='catalog.smart.list',params=dict(after_id=None)))
        self.assertTrue(result['ok'],result)
        for schema in ('future',1,None):
            with self.assertRaises(LibraryError):SmartGroups(self.db).save(dict(group_id=None,name='x',description='',expected_revision=0,definition=dict(schema=schema,query='',criteria={},include_groups=[])))
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
