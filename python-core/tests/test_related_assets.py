import json
import struct
import unittest
from unittest.mock import patch
import test_annotations
import test_catalog_query
import test_embeddings
import test_analysis
from ai_asset_hub_core.related_assets import RelatedAssets
from ai_asset_hub_core.embeddings import Embeddings
from ai_asset_hub_core.asset_management import AssetManagement
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.database import Database


class RelatedAssetTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    extra_assets=test_catalog_query.CatalogQueryTests.extra_assets
    configure=test_embeddings.EmbeddingTests.configure

    def query(self,mode='metadata',filters=None):return RelatedAssets(self.db).query(dict(asset_id=self.id,mode=mode,criteria=filters or {},limit=20))

    def tagged(self):
        other,unrelated=self.extra_assets(2)
        for asset in (self.id,other):self.service.tags(dict(asset_id=asset,add=['공유'],remove=[]))
        return other,unrelated

    def vectors(self,values):
        profile=self.configure()
        for asset in values:test_analysis.AnalysisTests.history(self,asset,'completed',True)
        self.db.connection.execute("UPDATE asset_files SET sha256='fixture'")
        documents=Embeddings(self.db).documents()
        for asset,vector in values.items():
            doc=documents[asset]
            self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?, 'fixture')",(asset,doc['resultId'],profile['version'],3,struct.pack('<fff',*vector),doc['fingerprint']))
        return profile

    def test_public_metadata_recommendations_are_real_not_confirmed_and_read_only(self):
        other,unrelated=self.tagged();before='\n'.join(self.db.connection.iterdump());changes=self.db.connection.total_changes
        with patch('builtins.open',side_effect=AssertionError('no original reads')),patch('ai_asset_hub_core.embeddings.inspect',side_effect=AssertionError('no metadata network')),patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no inference')):
            result=self.query()
        self.assertEqual([r['id'] for r in result['items']],[other]);self.assertEqual(result['items'][0]['reasons'],[dict(kind='shared_tag',count=1)])
        self.assertFalse(result['items'][0]['confirmed']);self.assertFalse(result['relationshipCreated']);self.assertFalse(result['inferenceCalled'])
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before);self.assertEqual(self.db.connection.total_changes,changes)
        self.assertEqual(self.query(filters={'kind':'PNG'})['items'],[])

    def test_current_stored_vectors_exclude_stale_dimensions_profiles_and_negative_scores(self):
        a,b=self.extra_assets(2);profile=self.vectors({self.id:[1,0,0],a:[.9,.1,0],b:[-1,0,0]})
        before=self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0]
        with patch('ai_asset_hub_core.embeddings.inspect',side_effect=AssertionError('no network')),patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no inference')):
            result=self.query('stored_vectors')
        self.assertEqual([r['id'] for r in result['items']],[a]);self.assertEqual(result['vectorStatus'],'ready');self.assertEqual(result['profileVersion'],profile['version'])
        self.service.tags(dict(asset_id=a,add=['changed'],remove=[]));self.assertEqual(self.query('stored_vectors')['items'],[])
        self.db.connection.execute('UPDATE asset_embeddings SET dimension=4 WHERE asset_id=?',(b,));self.assertEqual(self.query('stored_vectors')['items'],[])
        self.service.tags(dict(asset_id=self.id,add=['source-changed'],remove=[]));self.assertEqual(self.query('stored_vectors')['vectorStatus'],'source-vector-unavailable')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],before)

    def test_unavailable_vectors_hybrid_fallback_and_reopen_never_create_jobs(self):
        other,_=self.tagged();result=self.query('hybrid')
        self.assertEqual(result['vectorStatus'],'source-vector-unavailable');self.assertEqual(result['items'][0]['id'],other)
        self.assertIsNone(result['items'][0]['semanticScore']);self.assertEqual(self.query('stored_vectors')['items'],[])
        self.db.close();self.db=Database(self.base/'db.sqlite');self.assertEqual(self.query()['items'][0]['id'],other)
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_only_explicit_relation_save_confirms_and_stale_revision_preserves_user_decisions(self):
        other,unrelated=self.tagged();self.assertEqual(self.query()['items'][0]['id'],other)
        service=AssetManagement(self.db);self.assertEqual(service.relations(dict(asset_id=self.id))['value'],[])
        links=[dict(targetId=other,kind='related')];service.save_relations(dict(asset_id=self.id,value=links,expected_revision=0))
        self.assertEqual(self.query()['items'],[])
        before='\n'.join(self.db.connection.iterdump())
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.save_relations(dict(asset_id=self.id,value=[],expected_revision=0))
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before);self.assertEqual(service.relations(dict(asset_id=self.id))['value'],links)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_invalid_modes_limits_criteria_and_missing_indexed_targets_fail_closed(self):
        other,_=self.tagged()
        for extra in ({'mode':'new_inference'},{'limit':True},{'limit':0},{'limit':21},{'criteria':{'min_size':-1}}):
            with self.assertRaises(LibraryError):RelatedAssets(self.db).query({**dict(asset_id=self.id,mode='metadata',criteria={},limit=10),**extra})
        self.db.connection.execute('UPDATE asset_files SET exists_flag=0 WHERE asset_id=?',(other,));self.assertEqual(self.query()['items'],[])
        self.assertNotIn('contact',json.dumps(self.query()))

    def test_large_unicode_response_fails_within_the_protocol_and_lower_limit_can_retry(self):
        from ai_asset_hub_core.application import CoreApplication
        from uuid import uuid4
        ids=self.extra_assets(20)
        for asset in [self.id,*ids]:self.service.tags(dict(asset_id=asset,add=['공유'],remove=[]))
        self.db.connection.execute('UPDATE assets SET display_name=?',('😀'*160,))
        app=CoreApplication(self.db);params=dict(asset_id=self.id,mode='metadata',criteria={},limit=20)
        response=app.handle(dict(request_id=str(uuid4()),method='catalog.related',params=params))
        self.assertFalse(response['ok']);self.assertEqual(response['error']['code'],'CATALOG_LIMIT')
        params['limit']=1;response=app.handle(dict(request_id=str(uuid4()),method='catalog.related',params=params))
        self.assertTrue(response['ok']);self.assertLess(len(json.dumps(response,ensure_ascii=False).encode()),16384)
