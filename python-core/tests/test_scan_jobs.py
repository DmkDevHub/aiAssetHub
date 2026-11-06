import threading
import time
import unittest
from unittest.mock import patch
import test_annotations
from ai_asset_hub_core.scan_jobs import ScanJobs
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryError


class ScanJobTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def test_explicit_async_start_keeps_database_readable_and_preserves_result(self):
        service=ScanJobs();release=threading.Event();entered=threading.Event();original=AssetService.scan
        library=self.db.connection.execute('SELECT id FROM library_roots').fetchone()[0]
        def delayed(worker,params,cancel=None):entered.set();release.wait(2);return original(worker,params,cancel)
        try:
            with patch.object(AssetService,'scan',delayed):
                started=time.perf_counter();job=service.start(self.db,dict(library_id=library));self.assertLess(time.perf_counter()-started,.5)
                self.assertTrue(entered.wait(2));self.assertEqual(self.db.health()['status'],'ready')
                self.assertEqual(service.status(self.db,dict(job_id=job['jobId']))['status'],'running')
                self.assertTrue(service.start(self.db,dict(library_id=library))['reused']);release.set();service.thread.join(3)
            result=service.status(self.db,dict(job_id=job['jobId']));self.assertEqual(result['status'],'completed');self.assertEqual(result['result']['processed'],1)
            self.assertEqual(ScanJobs().status(self.db,dict(job_id=job['jobId'])),result)
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        finally:release.set();service.close()

    def test_cancelled_scan_rolls_back_and_orphaned_jobs_are_not_resumed(self):
        from ai_asset_hub_core.libraries import LibraryError
        library=self.db.connection.execute('SELECT id FROM library_roots').fetchone()[0];before='\n'.join(self.db.connection.iterdump());cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(LibraryError,'SCAN_CANCELLED'):AssetService(self.db).scan(dict(library_id=library),cancel)
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)
        service=ScanJobs();from uuid import uuid4
        job=str(uuid4());service.write(self.db,job,dict(jobId=job,status='running',result=None))
        self.assertEqual(service.status(self.db,dict(job_id=job))['status'],'interrupted');self.assertIsNone(service.thread)
