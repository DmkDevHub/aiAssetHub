import unittest
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.analysis_plan import AnalysisPlan
from ai_asset_hub_core.libraries import LibraryError


class AnalysisTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def params(self, **updates):
        result={'mode':'all','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[],'model_id':str(uuid4())}
        result.update(updates);return result

    def history(self, identifier, status, active=False, timestamp='2026-10-28T00:00:00Z'):
        job,run,result=[str(uuid4()) for _ in range(3)];db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,?,?,'fixture')",(job,str(uuid4()),status,timestamp))
        db.execute('INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,?)',(job,identifier,status))
        db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,'{}','fixture',?,?)",(run,job,identifier,status,timestamp))
        if active:
            db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,'fixture successful','[]','{}',?)",(result,run,identifier,timestamp))
            db.execute('INSERT INTO asset_active_results VALUES (?,?,?)',(identifier,result,timestamp))

    def test_modes_count_success_and_last_failure_independently_without_creating_jobs(self):
        (self.source/'other.txt').write_text('fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        other=self.db.connection.execute('SELECT id FROM assets WHERE id!=?',(self.id,)).fetchone()[0]
        self.history(self.id,'completed',True)
        self.history(self.id,'failed',timestamp='2026-10-28T00:00:01Z')
        plan=AnalysisPlan(self.db)
        for mode,count in [('all',2),('unanalyzed',1),('completed',1),('failed',1)]:
            self.assertEqual(plan.preview(self.params(mode=mode))['targetCount'],count)
        self.assertEqual(plan.preview(self.params(mode='selected',selected_ids=[other]))['targetCount'],1)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],2)
        with self.assertRaises(LibraryError):plan.preview(self.params(mode='selected',selected_ids=[str(uuid4())]))

    def test_folder_library_and_selection_scopes_intersect_without_prefix_collisions(self):
        for folder in ('tree','treehouse'):
            path=self.source/folder;path.mkdir();(path/'asset.png').write_bytes(b'fixture')
        nested=self.source/'tree'/'child';nested.mkdir();(nested/'nested.png').write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library});plan=AnalysisPlan(self.db)
        self.assertEqual(plan.preview(self.params(scope='folder',library_id=library,folder_parts=['tree']))['targetCount'],2)
        self.assertEqual(plan.preview(self.params(scope='library',library_id=library))['targetCount'],4)
        self.assertEqual(plan.preview(self.params(scope='folder',library_id=library,folder_parts=['tree'],mode='selected',selected_ids=[self.id]))['targetCount'],0)
        with self.assertRaises(LibraryError):plan.preview(self.params(scope='folder',library_id=library,folder_parts=['..']))
        with self.assertRaises(LibraryError):plan.preview(self.params(scope='library',library_id=str(uuid4())))
