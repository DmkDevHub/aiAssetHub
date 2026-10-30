import json
import struct
import unittest
from unittest.mock import patch
import test_annotations
import test_analysis
import test_embeddings
from ai_asset_hub_core.analysis_review import AnalysisReview
from ai_asset_hub_core.catalog import Catalog
from ai_asset_hub_core.embeddings import Embeddings
from ai_asset_hub_core.libraries import LibraryError


class ReviewTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def result(self):
        from uuid import uuid4
        job,run,result=[str(uuid4()) for _ in range(3)];db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,'completed','fixture','fixture')",(job,str(uuid4())))
        db.execute("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'completed')",(job,self.id))
        db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,'{}','fixture','completed','fixture')",(run,job,self.id))
        db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,'fixture','[]',?,'fixture')",(result,run,self.id,json.dumps({'suggestions':{'primary':'A01','roles':['role.item'],'styles':['style.pixel']}})))
        db.execute("INSERT INTO asset_active_results VALUES (?,?,'fixture')",(self.id,result))
        return result

    def test_actual_result_requires_review_and_explicit_apply_with_revision_conflicts(self):
        result=self.result();service=AnalysisReview(self.db);params={'asset_id':self.id,'result_id':result}
        before=Catalog(self.db).classification({'asset_id':self.id})
        with patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):
            preview=service.preview(params)
        self.assertEqual(Catalog(self.db).classification({'asset_id':self.id}),before)
        request={**params,'plan_token':preview['planToken'],'expected_revision':preview['expectedRevision'],'confirmed':False}
        with self.assertRaises(LibraryError):service.apply(request)
        request['confirmed']=True;applied=service.apply(request)
        self.assertEqual(applied['value']['primary'],'A01');self.assertEqual(applied['source'],'user')
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.apply(request)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM metadata_decision_history WHERE field=?',('classification',)).fetchone()[0],1)

    def test_public_metadata_change_marks_vector_stale_without_embedding_or_deleting_it(self):
        result=self.result();self.db.connection.execute("UPDATE asset_files SET sha256='fixture'")
        profile=test_embeddings.EmbeddingTests.configure(self)
        doc=Embeddings(self.db).documents()[self.id]
        self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?,'fixture')",(self.id,result,profile['version'],3,struct.pack('<fff',1,0,0),doc['fingerprint']))
        self.assertEqual(Embeddings(self.db).status({})['readyCount'],1)
        service=AnalysisReview(self.db);params={'asset_id':self.id,'result_id':result};preview=service.preview(params)
        with patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no embedding')):
            service.apply({**params,'plan_token':preview['planToken'],'expected_revision':preview['expectedRevision'],'confirmed':True})
            status=Embeddings(self.db).status({})
        self.assertEqual((status['readyCount'],status['staleCount']),(0,1))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0],1)
