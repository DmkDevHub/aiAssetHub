import unittest
from unittest.mock import patch
import test_annotations
from ai_asset_hub_core.embeddings import Embeddings,vector
from ai_asset_hub_core.libraries import LibraryError


class EmbeddingTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def configure(self,dimension=3):
        with patch('ai_asset_hub_core.embeddings.metadata',return_value={'capabilities':['embedding'],'model_info':{'fixture.embedding_length':dimension}}) as request:
            result=Embeddings(self.db).configure({'model_name':'fixture-embedding','prefix_scheme':'plain'})
            request.assert_called_once_with('http://127.0.0.1:11434/api/show',{'model':'fixture-embedding'})
        return result['profile']

    def test_configuration_persists_real_dimensions_and_status_never_calls_model(self):
        from ai_asset_hub_core.database import Database
        first=self.configure();self.db.close();self.db=Database(self.base/'db.sqlite')
        with patch('ai_asset_hub_core.embeddings.metadata',side_effect=AssertionError('no calls')):
            status=Embeddings(self.db).status({});self.assertEqual(status['profile'],first);self.assertEqual(status['readyCount'],0)
        second=self.configure(4);self.assertNotEqual(first['version'],second['version'])
        for bad in ([0,0,0],[1,float('nan'),0],[1,2],[True,0,1]):
            with self.assertRaises(LibraryError):vector(bad,3)
        self.assertAlmostEqual(sum(v*v for v in vector([1,2,3],3)),1)

    def add_result(self):
        import test_analysis
        test_analysis.AnalysisTests.history(self,self.id,'completed',True)
        self.db.connection.execute("UPDATE asset_files SET sha256='fixture'")
        return self.db.connection.execute('SELECT id FROM analysis_results').fetchone()[0]

    def test_selected_current_results_generate_versioned_vectors_without_automatic_calls(self):
        import time
        from ai_asset_hub_core.embedding_engine import EmbeddingEngine,work_status
        profile=self.configure();result=self.add_result();engine=EmbeddingEngine(self.db)
        with patch('ai_asset_hub_core.embeddings.inspect',return_value=(profile['dimension'],profile['metadataVersion'])),patch('ai_asset_hub_core.embedding_engine.embed',return_value=[1,0,0]) as call:
            self.assertEqual(Embeddings(self.db).status({})['readyCount'],0);call.assert_not_called()
            job=engine.start(self.db,{'selected':[{'asset_id':self.id,'result_id':result}],'confirmed':True})['jobId']
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close();self.assertEqual(call.call_count,1)
        self.assertEqual(work_status(self.db,{'job_id':job})['status'],'completed')
        self.assertEqual(Embeddings(self.db).status({})['readyCount'],1)
        self.db.connection.execute('UPDATE asset_files SET sha256=NULL')
        self.assertEqual(Embeddings(self.db).status({})['readyCount'],0)

    def test_korean_query_explicitly_embeds_once_and_returns_cosine_order(self):
        import struct,time
        from ai_asset_hub_core.embedding_engine import EmbeddingEngine,work_status
        profile=self.configure();result=self.add_result()
        doc=Embeddings(self.db).documents()[self.id]
        self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?,'fixture')",(self.id,result,profile['version'],3,struct.pack('<fff',1,0,0),doc['fingerprint']))
        engine=EmbeddingEngine(self.db)
        with patch('ai_asset_hub_core.embeddings.inspect',return_value=(3,profile['metadataVersion'])),patch('ai_asset_hub_core.semantic_search.embed',return_value=[.8,.6,0]) as call:
            call.assert_not_called()
            job=engine.query(self.db,{'query':'중세 마을 횃불','mode':'semantic','confirmed':True})['jobId']
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close();self.assertEqual(call.call_count,1)
        status=work_status(self.db,{'job_id':job});self.assertEqual(status['status'],'completed')
        self.assertNotIn('중세 마을 횃불',self.db.connection.execute('SELECT value_json FROM settings WHERE key=?',('embedding.work.'+job,)).fetchone()[0])
        self.assertEqual(status['results'][0]['id'],self.id);self.assertAlmostEqual(status['results'][0]['score'],.8)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0],1)

    def test_hybrid_without_vectors_is_keyword_only_and_filters_before_limit(self):
        import time
        from ai_asset_hub_core.embedding_engine import EmbeddingEngine,work_status
        self.add_result();engine=EmbeddingEngine(self.db)
        with patch('ai_asset_hub_core.semantic_search.embed',side_effect=AssertionError('no query embedding')):
            job=engine.query(self.db,{'query':'successful','mode':'hybrid','confirmed':True,'criteria':{}})['jobId']
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
        rows=work_status(self.db,{'job_id':job})['results'];self.assertEqual(rows[0]['id'],self.id);self.assertEqual(rows[0]['reason'],'keyword');self.assertIsNone(rows[0]['semanticScore'])
        from ai_asset_hub_core.semantic_search import keywords,criteria
        self.assertEqual(keywords(self.db,'successful',criteria({'tag':'no-such-tag'})),[])
        with self.assertRaises(LibraryError):criteria({'folder_parts':['..']})

    def test_cosine_order_and_pre_ranking_tag_filter_use_actual_candidate_ids(self):
        import struct,threading,test_analysis
        from ai_asset_hub_core.assets import AssetService
        from ai_asset_hub_core.semantic_search import search
        profile=self.configure();self.add_result()
        (self.source/'other.png').write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        other=self.db.connection.execute('SELECT id FROM assets WHERE id!=?',(self.id,)).fetchone()[0]
        test_analysis.AnalysisTests.history(self,other,'completed',True)
        self.db.connection.execute("UPDATE asset_files SET sha256='fixture'")
        self.service.tags({'asset_id':self.id,'add':['selected-tag'],'remove':[]})
        from ai_asset_hub_core.metadata_store import MetadataStore
        MetadataStore(self.db).classify(self.id,facets={'style':['style.pixel']},expected_revision=0,confirmed=True)
        for doc in Embeddings(self.db).documents().values():
            values=[1,0,0] if doc['id']==self.id else [0,1,0]
            self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?,'fixture')",(doc['id'],doc['resultId'],profile['version'],3,struct.pack('<fff',*values),doc['fingerprint']))
        control={'cancel':threading.Event()};job={'profile':profile,'query':'한국어','mode':'semantic'}
        with patch('ai_asset_hub_core.embeddings.inspect',return_value=(3,profile['metadataVersion'])),patch('ai_asset_hub_core.semantic_search.embed',return_value=[.6,.8,0]):
            rows=search(self.db,job,control)
            self.assertEqual([r['id'] for r in rows],[other,self.id])
            self.assertAlmostEqual(rows[0]['score'],.8)
            job['criteria']={'tag':'selected-tag'}
            self.assertEqual([r['id'] for r in search(self.db,job,control)],[self.id])
            job['criteria']={'styles':['style.pixel']}
            self.assertEqual([r['id'] for r in search(self.db,job,control)],[self.id])

    def test_model_switch_and_atomic_rebuild_never_mix_spaces_or_drop_old_data_on_failure(self):
        import struct,time
        from ai_asset_hub_core.embedding_engine import EmbeddingEngine,work_status
        old=self.configure();result=self.add_result();doc=Embeddings(self.db).documents()[self.id]
        self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?,'fixture')",(self.id,result,old['version'],3,struct.pack('<fff',1,0,0),doc['fingerprint']))
        new=self.configure(4);self.assertEqual(Embeddings(self.db).status({})['readyCount'],0)
        engine=EmbeddingEngine(self.db)
        def wait(job):
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
        with patch('ai_asset_hub_core.embeddings.inspect',return_value=(4,new['metadataVersion'])),patch('ai_asset_hub_core.embedding_engine.embed',return_value=[1,0,0,0]):
            job=engine.rebuild(self.db,{'confirmed':True})['jobId'];wait(job)
        self.assertEqual(work_status(self.db,{'job_id':job})['status'],'completed')
        self.assertEqual(Embeddings(self.db).status({})['readyCount'],1)
        before=self.db.connection.execute('SELECT embedding_model,vector_blob FROM asset_embeddings ORDER BY embedding_model').fetchall()
        with patch('ai_asset_hub_core.embeddings.inspect',return_value=(4,new['metadataVersion'])),patch('ai_asset_hub_core.embedding_engine.embed',side_effect=LibraryError('EMBEDDING_FAILED')):
            job=engine.rebuild(self.db,{'confirmed':True})['jobId'];wait(job);engine.close()
        self.assertEqual(work_status(self.db,{'job_id':job})['status'],'failed')
        self.assertEqual(before,self.db.connection.execute('SELECT embedding_model,vector_blob FROM asset_embeddings ORDER BY embedding_model').fetchall())
        self.assertEqual(len(before),2)
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")

    def test_local_transport_prefix_model_identity_and_cancellation(self):
        import json,threading
        from unittest.mock import MagicMock
        from ai_asset_hub_core.embeddings import embed
        profile={'modelName':'fixture-embedding','dimension':3,'prefixScheme':'embeddinggemma'}
        cancel=threading.Event();connection=MagicMock();response=connection.getresponse.return_value
        response.status=200;response.read.return_value=json.dumps({'model':'fixture-embedding','embeddings':[[3,4,0]]}).encode()
        with patch('http.client.HTTPConnection',return_value=connection) as transport:
            self.assertEqual(embed(profile,'한국어 질의',True,cancel,lambda c:None),[.6,.8,0])
            transport.assert_called_once_with('127.0.0.1',11434,timeout=3)
            payload=json.loads(connection.request.call_args.args[2])
            self.assertEqual(payload['input'],'task: search result | query: 한국어 질의')
            self.assertFalse(payload['truncate']);connection.close.assert_called_once()
            response.read.return_value=b'{"model":"wrong-model","embeddings":[[3,4,0]]}'
            with self.assertRaisesRegex(LibraryError,'EMBEDDING_INVALID_VECTOR'):embed(profile,'text',False,cancel,lambda c:None)
            response.status=302
            with self.assertRaisesRegex(LibraryError,'EMBEDDING_FAILED'):embed(profile,'text',False,cancel,lambda c:None)
            cancel.set();transport.reset_mock()
            with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):embed(profile,'text',False,cancel,lambda c:None)
            transport.assert_not_called()
