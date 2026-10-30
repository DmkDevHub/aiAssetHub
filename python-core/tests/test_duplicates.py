import hashlib
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.duplicates import DuplicateJobs,hash_file,save,read
from ai_asset_hub_core.libraries import LibraryError


class DuplicateTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def scan(self):
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        return [r[0] for r in self.db.connection.execute('SELECT id FROM assets ORDER BY id')]
    def wait(self,manager,job):
        deadline=time.monotonic()+5
        while manager.active(job) and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(manager.active(job))
        return manager.status(self.db,{'job_id':job,'after_id':None})
    def item(self):
        row=self.db.connection.execute('SELECT id,asset_id,size_bytes,mtime_ns FROM asset_files WHERE asset_id=?',(self.id,)).fetchone()
        return dict(zip(('fileId','ownerId','size','mtimeNs'),row))

    def test_explicit_streaming_hash_and_candidates_are_not_logical_or_rights_merges(self):
        for name in ('same.png','different.png'):(self.source/name).write_bytes(b'original' if name=='same.png' else b'different')
        ids=self.scan();manager=DuplicateJobs()
        with patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no AI')):
            self.assertEqual(manager.list(self.db,{})['items'],[])
            with self.assertRaises(LibraryError):manager.start(self.db,{'asset_ids':ids,'confirmed':False})
            job=manager.start(self.db,{'asset_ids':ids,'confirmed':True})['jobId'];status=self.wait(manager,job)
            self.assertEqual((status['hashed'],status['failed']),(3,0))
            with patch('builtins.open',side_effect=AssertionError('comparison cannot rehash')):
                groups=manager.candidates(self.db,{'job_id':job,'after_hash':None,'after_file_id':None})['items']
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['fileCount'],2)
        self.assertEqual(groups[0]['sha256'],hashlib.sha256(b'original').hexdigest())
        self.assertEqual(groups[0]['rightsEquivalence'],'not-determined');self.assertEqual(len({f['fileId'] for f in groups[0]['files']}),2)
        self.assertEqual((self.source/'same.png').read_bytes(),b'original')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM assets').fetchone()[0],3)
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        manager.close()

    def test_file_change_permission_cancel_and_size_limit_never_store_a_success_hash(self):
        item=self.item();canceled=threading.Event();canceled.set()
        with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):hash_file(self.db,item,canceled)
        canceled.clear()
        with patch('builtins.open',side_effect=PermissionError('PRIVATE-PATH')):
            with self.assertRaisesRegex(LibraryError,'FILE_PERMISSION_DENIED'):hash_file(self.db,item,canceled)
        with patch('ai_asset_hub_core.duplicates.MAX_BYTES',1):
            with self.assertRaisesRegex(LibraryError,'INPUT_TOO_LARGE'):hash_file(self.db,item,canceled)
        (self.source/'나무.png').write_bytes(b'changed')
        with self.assertRaisesRegex(LibraryError,'FILE_CHANGED'):hash_file(self.db,item,canceled)
        self.assertIsNone(self.db.connection.execute('SELECT sha256 FROM asset_files WHERE id=?',(item['fileId'],)).fetchone()[0])

    def test_cancel_running_job_stops_following_files_and_preserves_completed_hashes(self):
        for name in ('second.png','third.png'):(self.source/name).write_bytes(b'original')
        ids=self.scan();manager=DuplicateJobs();entered=threading.Event();release=threading.Event();calls=[]
        def slow(database,item,cancel):
            calls.append(item['fileId'])
            if len(calls)==1:return hash_file(database,item,cancel)
            entered.set();release.wait(3)
            if cancel.is_set():raise LibraryError('USER_CANCELED')
            return hash_file(database,item,cancel)
        with patch('ai_asset_hub_core.duplicates.hash_file',side_effect=slow):
            job=manager.start(self.db,{'asset_ids':ids,'confirmed':True})['jobId'];self.assertTrue(entered.wait(3))
            manager.cancel(self.db,{'job_id':job});release.set();status=self.wait(manager,job)
        self.assertEqual(status['status'],'canceled');self.assertEqual(status['hashed'],1);self.assertEqual(len(calls),2)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_files WHERE sha256 IS NOT NULL').fetchone()[0],1);manager.close()

    def test_candidate_stale_exclusion_and_file_pagination_and_orphan_recovery(self):
        for index in range(5):(self.source/f'copy{index}.png').write_bytes(b'original')
        ids=self.scan();manager=DuplicateJobs();job=manager.start(self.db,{'asset_ids':ids,'confirmed':True})['jobId'];self.wait(manager,job)
        first=manager.candidates(self.db,{'job_id':job,'after_hash':None,'after_file_id':None});self.assertEqual(len(first['items'][0]['files']),4)
        more=manager.candidates(self.db,{'job_id':job,'after_hash':None,'after_file_id':first['next_file_cursor']});self.assertEqual(len(more['items'][0]['files']),2)
        (self.source/'copy0.png').write_bytes(b'changed')
        self.assertEqual(manager.candidates(self.db,{'job_id':job,'after_hash':None,'after_file_id':None})['staleCount'],1)
        orphan=str(uuid4());save(self.db,orphan,{'status':'running','items':[{**self.item(),'status':'running','sha256':None,'errorCode':None}]})
        restored=DuplicateJobs();self.assertTrue(restored.status(self.db,{'job_id':orphan,'after_id':None})['needsRecovery'])
        with self.assertRaisesRegex(LibraryError,'HASH_BUSY'):restored.start(self.db,{'asset_ids':ids,'confirmed':True})
        restored.cancel(self.db,{'job_id':orphan});self.assertEqual(read(self.db,orphan)['status'],'canceled');restored.close();manager.close()

    def test_modification_while_reading_is_detected_before_hash_commit(self):
        item=self.item();digest=hashlib.sha256();path=self.source/'나무.png'
        class MutatingDigest:
            def update(inner,chunk):digest.update(chunk);path.write_bytes(b'changed-during-read')
            def hexdigest(inner):return digest.hexdigest()
        with patch('ai_asset_hub_core.duplicates.hashlib.sha256',return_value=MutatingDigest()):
            with self.assertRaisesRegex(LibraryError,'FILE_CHANGED'):hash_file(self.db,item,threading.Event())
        self.assertIsNone(self.db.connection.execute('SELECT sha256 FROM asset_files WHERE id=?',(item['fileId'],)).fetchone()[0])

    def test_replaced_file_with_preserved_size_and_timestamp_is_excluded_by_identity(self):
        import os
        (self.source/'copy.png').write_bytes(b'original');ids=self.scan();manager=DuplicateJobs()
        job=manager.start(self.db,{'asset_ids':ids,'confirmed':True})['jobId'];self.wait(manager,job)
        path=self.source/'copy.png';before=path.stat();replacement=self.source/'replacement.tmp';replacement.write_bytes(b'changed!')
        os.utime(replacement,ns=(before.st_atime_ns,before.st_mtime_ns));os.replace(replacement,path)
        result=manager.candidates(self.db,{'job_id':job,'after_hash':None,'after_file_id':None})
        self.assertEqual(result['staleCount'],1);self.assertEqual(result['items'],[]);manager.close()

    def test_cancel_completion_race_cannot_overwrite_a_newly_completed_job(self):
        job=str(uuid4());item={**self.item(),'status':'hashed','sha256':hashlib.sha256(b'original').hexdigest(),'errorCode':None}
        complete={'status':'completed','items':[item]};save(self.db,job,complete)
        manager=DuplicateJobs()
        with patch('ai_asset_hub_core.duplicates.read',side_effect=[{'status':'running','items':[]},complete]):
            result=manager.cancel(self.db,{'job_id':job})
        self.assertFalse(result['cancelRequested']);self.assertEqual(read(self.db,job),complete);manager.close()
