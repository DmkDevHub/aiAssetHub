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
