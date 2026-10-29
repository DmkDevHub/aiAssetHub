import copy
import unittest
import test_annotations as fixtures
from ai_asset_hub_core.asset_management import AssetManagement
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.assets import AssetService


class ManagementTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown

    def service_and_value(self):
        service = AssetManagement(self.db)
        return service, service.read({'asset_id': self.id})['value']

    def test_management_roundtrip_conflict_and_rescan(self):
        service, value = self.service_and_value()
        self.assertIsNone(value['rating'])
        value.update(favorite=True, rating=5, status='approved', notes='사용자 메모', assetVersion='v1', createdDate='2024-02-29', modifiedDate='2026-10-29')
        params = dict(asset_id=self.id, value=value, expected_revision=0)
        saved = service.save_management(params)
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'): service.save_management(params)
        library = self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id': library})
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        self.assertEqual(AssetManagement(self.db).read({'asset_id': self.id}), saved)
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')
        for table in ('analysis_jobs', 'asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)

    def test_invalid_management_is_atomic(self):
        service, value = self.service_and_value()
        for field, invalids in {'rating':[0,6,True,'1'], 'favorite':[1,None], 'status':['fake'], 'notes':['x'*1025], 'createdDate':['2025-02-29','2026-1-01',None], 'modifiedDate':['2023-01-01']}.items():
            for invalid in invalids:
                attempt = copy.deepcopy(value); attempt['createdDate']='2024-01-01'; attempt[field]=invalid
                with self.subTest(field=field, value=invalid), self.assertRaises(LibraryError):
                    service.save_management(dict(asset_id=self.id, value=attempt, expected_revision=0))
        self.assertEqual(service.read({'asset_id':self.id})['revision'],0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM metadata_decision_history').fetchone()[0],0)

    def test_composition_links_actual_files_and_retains_missing_identity(self):
        service = AssetManagement(self.db)
        library = self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        (self.source/'dependency.wav').write_bytes(b'fixture dependency')
        AssetService(self.db).scan({'library_id':library})
        other = self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id!=?', (self.id,)).fetchone()[0]
        value = service.composition({'asset_id':self.id})['value']
        value['files'].append({'fileId':other,'role':'dependency'})
        saved = service.save_composition(dict(asset_id=self.id,value=value,expected_revision=0))
        self.assertEqual(saved['availability'],'available')
        # Only test-owned fixture is removed, to exercise a missing external file.
        (self.source/'dependency.wav').unlink()
        AssetService(self.db).scan({'library_id':library})
        current=service.composition({'asset_id':self.id})
        self.assertEqual(current['availability'],'partial')
        self.assertEqual(current['value'],saved['value'])
        self.assertEqual(current['revision'],1)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):
            service.save_composition(dict(asset_id=self.id,value=value,expected_revision=0))
        for bad in ({'files':[],'components':[]}, {'files':[{'fileId':other,'role':'dependency'}],'components':[]}):
            with self.assertRaises(LibraryError): service.save_composition(dict(asset_id=self.id,value=bad,expected_revision=1))

    def test_components_require_actual_registered_fresh_file_evidence(self):
        import json
        from uuid import uuid4
        from ai_asset_hub_core.asset_composition import component
        service=AssetManagement(self.db)
        value=service.composition({'asset_id':self.id})['value']; file=value['files'][0]['fileId']
        c=component(file,'a'*64,'mesh',['fixture-mesh'])
        self.db.connection.execute('UPDATE asset_files SET sha256=? WHERE id=?',('a'*64,file))
        self.db.connection.execute('INSERT INTO asset_components VALUES (?,?,?,?,?,?)',(c['id'],file,'a'*64,'mesh',json.dumps(c['locator']),1))
        value['components']=[str(uuid4())]
        with self.assertRaises(LibraryError): service.save_composition(dict(asset_id=self.id,value=value,expected_revision=0))
        value['components']=[c['id']]
        service.save_composition(dict(asset_id=self.id,value=value,expected_revision=0))
        self.db.connection.execute('UPDATE asset_files SET sha256=NULL WHERE id=?',(file,))
        self.assertTrue(service.composition({'asset_id':self.id})['components'][0]['stale'])
        with self.assertRaises(LibraryError): service.save_composition(dict(asset_id=self.id,value=value,expected_revision=1))
        self.assertEqual(service.composition({'asset_id':self.id})['revision'],1)

    def test_candidates_are_bounded_paged_and_use_only_real_enabled_ids(self):
        service=AssetManagement(self.db)
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        for n in range(4): (self.source/f'fixture-{n}.wav').write_bytes(b'fixture')
        AssetService(self.db).scan({'library_id':library})
        cursor=None;ids=[]
        while True:
            page=service.candidates(dict(asset_id=self.id,kind='file',after_id=cursor))
            self.assertLessEqual(len(page['items']),2);ids.extend(i['id'] for i in page['items']);cursor=page['next_cursor']
            if cursor is None: break
        self.assertEqual(len(set(ids)),5)
        self.assertEqual(service.candidates(dict(asset_id=self.id,kind='component',after_id=None))['items'],[])
        with self.assertRaises(LibraryError): service.candidates(dict(asset_id=self.id,kind='file',after_id='made-up'))
