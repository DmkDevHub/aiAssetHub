import json
import unittest
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.diagnostics import Diagnostics
from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.libraries import LibraryError


class DiagnosticTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def test_real_runs_paging_private_fields_redacted_and_unknown_cost_preserved(self):
        job=str(uuid4());db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,'completed','now','user')",(job,str(uuid4())))
        db.execute("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'completed')",(job,self.id))
        usage=dict(providerRequestAttempted=True,prompt_tokens=4,completion_tokens=2,providerReportedCostUsd='0.0123',api_key='PRIVATE-KEY',responseModel='PRIVATE-MODEL',path='PRIVATE-PATH')
        for _ in range(12):db.execute("INSERT INTO analysis_runs VALUES (?,?,?,'{\"private\":\"PRIVATE\"}','input','failed',?,'{\"code\":\"PRIVATE-ERROR\"}','now')",(str(uuid4()),job,self.id,json.dumps(usage)))
        before='\n'.join(db.iterdump());service=Diagnostics(self.db)
        first=service.read(dict(kind='analysis'));self.assertEqual(len(first['items']),10)
        second=service.read(dict(kind='analysis',after_id=first['next_cursor']));self.assertEqual(len(second['items']),2);self.assertIsNone(second['next_cursor'])
        self.assertEqual(first['items'][0]['usage']['providerReportedCostUsd'],'0.0123');self.assertEqual(first['items'][0]['errorCode'],'INTERNAL_ERROR')
        self.assertNotIn('PRIVATE',json.dumps(first));self.assertEqual('\n'.join(db.iterdump()),before)
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.read(dict(kind='arbitrary_table'))
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.read(dict(kind='analysis',after_id=str(uuid4())))
        app=CoreApplication(self.db);result=app.handle(dict(request_id=str(uuid4()),method='diagnostics.read',params=dict(kind='analysis')))
        self.assertTrue(result['ok']);self.assertLess(len(json.dumps(result).encode()),16384)

    def test_budget_is_reservation_not_claimed_invoice_and_unity_json_never_exported(self):
        db=self.db.connection;identifier=str(uuid4())
        db.execute("INSERT INTO settings VALUES (?,?,'now')",('model.policy.'+identifier,json.dumps(dict(budgetUsd='10',reservedUsd='1.25',requestsUsed=3,token='PRIVATE'))))
        service=Diagnostics(self.db);budget=service.budget({})
        self.assertEqual(budget['items'][0]['reservedUpperBoundUsd'],'1.25');self.assertNotIn('PRIVATE',json.dumps(budget));self.assertIn('not-invoice',budget['costMeaning'])
        db.execute("INSERT INTO unity_operations VALUES (?,?,?,?,'import','failed',?,'now')",(str(uuid4()),str(uuid4()),self.id,'PRIVATE-PATH',json.dumps(dict(plan=dict(token='PRIVATE'),result=dict(errorCode='PRIVATE',items=[dict(copied=True,sourcePath='PRIVATE')])))))
        rows=service.read(dict(kind='unity'));self.assertEqual(rows['items'][0]['copiedCount'],1);self.assertNotIn('PRIVATE',json.dumps(rows))
