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
