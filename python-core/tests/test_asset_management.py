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
