import json
import unittest
from unittest.mock import patch
import test_annotations
from ai_asset_hub_core.bulk_metadata import BulkMetadata
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.source_records import Sources
from ai_asset_hub_core.libraries import LibraryError


class BulkTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def request(self,changes):return {'asset_ids':[self.id],'changes':changes}
    def preview(self,request):return BulkMetadata(self.db).preview({'request':request,'after_id':None,'plan_token':None})

    def test_all_five_fields_preview_actual_before_after_without_writes_files_or_ai(self):
        service=BulkMetadata(self.db);group=service.group_create({'value':{'name':'그룹','description':''}})
        creator=Creators(self.db).create({'value':dict(name='회사',kind='company',brand='',homepageUrl='',profileUrl='',contact='PRIVATE',country='',description='')})
        changes={'groups':{'add':[group['id']],'remove':[]},'tags':{'add':['태그'],'remove':[]},'classification':{'primary':'A01'},
            'creators':{'add':[{'creator_id':creator['id'],'role':'creator'}],'remove':[]},'sources':{'append':[{'site':'상점','productName':'상품'}]}}
        before='\n'.join(self.db.connection.iterdump());count=self.db.connection.total_changes
        with patch('builtins.open',side_effect=AssertionError('no original reads')),patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):
            result=self.preview(self.request(changes))
        self.assertEqual(self.db.connection.total_changes,count);self.assertEqual('\n'.join(self.db.connection.iterdump()),before)
        row=result['items'][0];self.assertEqual(row['assetId'],self.id);self.assertEqual(row['after']['classification']['primary'],'A01')
        self.assertEqual(row['after']['groups'],[group['id']]);self.assertTrue(row['after']['sources'][0]['new']);self.assertNotIn('id',row['after']['sources'][0])
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual(result['changedCount'],1)

    def test_conflicts_and_changes_to_shared_references_invalidate_a_plan(self):
        service=BulkMetadata(self.db);group=service.group_create({'value':{'name':'그룹','description':''}})
        request=self.request({'groups':{'add':[group['id']],'remove':[]}});first=self.preview(request)
        request['expected']={self.id:{'groups':1}}
        self.assertEqual(self.preview(request)['items'][0]['conflicts'],['groups'])
        del request['expected'];service.group_update({'group_id':group['id'],'value':{'name':'바뀜','description':''},'expected_revision':1})
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.preview({'request':request,'after_id':None,'plan_token':first['planToken']})

    def test_invalid_fields_missing_ids_disabled_creators_and_limits_fail_closed(self):
        for request in ({'asset_ids':[],'changes':{'tags':{'set':[]}}},self.request({'unknown':{}}),self.request({'groups':{'set':['fake']}}),self.request({'classification':{'primary':'A99'}}),self.request({'sources':{'append':[{'site':'s','productName':'p','downloadUrl':'https://no-fetch.invalid'}]}})):
            with self.subTest(request=request),self.assertRaises(LibraryError):self.preview(request)
