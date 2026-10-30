import copy
import io
import json
import csv
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.metadata_exchange import MetadataExchange,SCHEMA,parse_document
from ai_asset_hub_core.bulk_metadata import BulkMetadata
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.assets import AssetService


class ImportTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def document(self,fields=None):
        return json.loads(MetadataExchange(self.db).export({'asset_ids':[self.id],'fields':fields or ['basic','tags','classification','groups','packages','creators','sources','relations'],'format':'json'})['content'])
    def params(self,document,rebase=False,format='json'):
        content=json.dumps(document,ensure_ascii=False) if not isinstance(document,str) else document
        return {'content':content,'format':format,'use_current_versions':rebase}
    def preview(self,params):return MetadataExchange(self.db).import_preview({**params,'after_id':None,'plan_token':None})

    def test_all_public_fields_roundtrip_is_a_read_only_noop_for_json_and_csv(self):
        service=MetadataExchange(self.db)
        for format in ('json','csv'):
            content=service.export({'asset_ids':[self.id],'fields':list(self.document()['fields']),'format':format})['content']
            before='\n'.join(self.db.connection.iterdump());count=self.db.connection.total_changes
            params=self.params(content,format=format)
            with patch('builtins.open',side_effect=AssertionError('no file reads')),patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):preview=self.preview(params)
            self.assertEqual(preview['changedCount'],0);self.assertEqual(preview['conflictCount'],0)
            self.assertEqual(self.db.connection.total_changes,count);self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_explicit_import_changes_user_values_and_conflict_rebase_is_also_reviewed(self):
        document=self.document(['tags']);document['assets'][0]['values']['tags']=['file value']
        self.service.tags({'asset_id':self.id,'add':['user value'],'remove':[]})
        service=MetadataExchange(self.db);params=self.params(document);preview=self.preview(params)
        self.assertEqual(preview['conflictCount'],1)
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.import_apply({**params,'plan_token':preview['planToken'],'confirmed':True})
        params=self.params(document,True);preview=self.preview(params)
        with self.assertRaises(LibraryError):service.import_apply({**params,'plan_token':preview['planToken'],'confirmed':False})
        result=service.import_apply({**params,'plan_token':preview['planToken'],'confirmed':True})
        self.assertEqual(result['updated'],1);self.assertEqual(self.service.get({'asset_id':self.id})['tags'],['file value'])
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM library_roots').fetchone()[0],1)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_import_rejects_schema_ids_paths_urls_duplicate_keys_and_size_before_writes(self):
        document=self.document(['tags']);cases=[]
        changed=copy.deepcopy(document);changed['schema_version']='future.v9';cases.append(changed)
        changed=copy.deepcopy(document);changed['assets'][0]['asset_id']=str(uuid4());cases.append(changed)
        changed=copy.deepcopy(document);changed['assets']*=2;cases.append(changed)
        changed=copy.deepcopy(document);changed['path']='D:/do-not-register';cases.append(changed)
        changed=copy.deepcopy(document);changed['assets'][0]['values']['downloadUrl']='https://do-not-fetch.invalid';cases.append(changed)
        changed=copy.deepcopy(document);changed['assets'][0]['versions']['tags']=True;cases.append(changed)
        before='\n'.join(self.db.connection.iterdump())
        with patch('ai_asset_hub_core.providers.metadata',side_effect=AssertionError('no network')):
            for case in cases:
                with self.subTest(case=case),self.assertRaises(LibraryError):self.preview(self.params(case))
            for text in ('{"schema_version":"x","schema_version":"y"}', '['*2000, 'x'*6001):
                with self.assertRaises(LibraryError):self.preview(self.params(text))
            with self.assertRaises(LibraryError):parse_document('asset_id,values\n=BAD(),{}','csv')
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_multi_target_failure_rolls_back_prior_nested_saves_and_history(self):
        (self.source/'second.png').write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        ids=[r[0] for r in self.db.connection.execute('SELECT id FROM assets ORDER BY id')]
        service=MetadataExchange(self.db);document=json.loads(service.export({'asset_ids':ids,'fields':['basic'],'format':'json'})['content'])
        for index,row in enumerate(document['assets']):row['values']['basic']['title']='import-'+str(index)
        params=self.params(document);preview=self.preview(params);before='\n'.join(self.db.connection.iterdump());calls=[]
        def fail(instance,target):
            BulkMetadata.apply_target(instance,target);calls.append(target['assetId'])
            if len(calls)==2:raise LibraryError('DB_UNAVAILABLE')
        with patch.object(MetadataExchange,'apply_target',new=fail):
            with self.assertRaises(LibraryError):service.import_apply({**params,'plan_token':preview['planToken'],'confirmed':True})
        self.assertEqual(len(calls),2);self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_combined_import_relation_cycle_is_rejected_without_writes(self):
        (self.source/'second.png').write_bytes(b'fixture');library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        ids=[r[0] for r in self.db.connection.execute('SELECT id FROM assets ORDER BY id')]
        doc=json.loads(MetadataExchange(self.db).export({'asset_ids':ids,'fields':['relations'],'format':'json'})['content'])
        for index,row in enumerate(doc['assets']):row['values']['relations']=[{'targetId':ids[1-index],'kind':'derived_from'}]
        with self.assertRaises(LibraryError):self.preview(self.params(doc))

    def test_import_public_source_update_preserves_private_purchase_urls_and_rights(self):
        from ai_asset_hub_core.source_records import Sources
        service=Sources(self.db);record=service.create_record({'subject':{'kind':'asset','id':self.id},'value':{'site':'old','productName':'product','originalUrl':'https://example.com/?key=PRIVATE','productUrl':'','downloadUrl':'','purchase':{'amount':'77','currency':'USD','purchasedOn':'','downloadedOn':''}}})
        document=self.document(['sources']);document['assets'][0]['values']['sources'][0]['site']='new'
        params=self.params(document);preview=self.preview(params)
        self.assertNotIn('PRIVATE',json.dumps(preview));self.assertNotIn('purchase',json.dumps(preview))
        MetadataExchange(self.db).import_apply({**params,'plan_token':preview['planToken'],'confirmed':True})
        after=service.record(record['id']);self.assertEqual(after['value']['site'],'new')
        self.assertEqual(after['value']['originalUrl'],'https://example.com/?key=PRIVATE');self.assertEqual(after['value']['purchase']['amount'],'77')
