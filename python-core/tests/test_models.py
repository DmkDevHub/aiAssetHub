from pathlib import Path
import tempfile
import unittest
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.models import ModelService
from ai_asset_hub_core.libraries import LibraryError


class ModelTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'.artifacts'/'model-tests';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.path=Path(self.temp.name)/'db.sqlite'
        self.db=Database(self.path);self.service=ModelService(self.db)

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def profile(self, **updates):
        return dict(provider_name='fixture provider',kind='local',model_id='fixture-model:version',modalities=['image'],**updates)

    def test_profiles_persist_off_and_duplicates_reuse_real_ids(self):
        profile=self.profile();first=self.service.register(profile)
        self.assertTrue(first['created']);self.assertEqual(self.service.register(profile),{'id':first['id'],'created':False})
        self.db.close();self.db=Database(self.path);self.service=ModelService(self.db)
        row=self.service.list({})['items'][0]
        self.assertEqual(row['id'],first['id']);self.assertFalse(row['enabled'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_invalid_registration_does_not_leave_provider_or_model(self):
        for key,value in [('kind','remote'),('provider_name',''),('model_id','x'*161),('modalities',['bad']),('modalities',[])]:
            profile=self.profile();profile[key]=value
            with self.assertRaises(LibraryError):self.service.register(profile)
        self.assertEqual(self.service.list({})['items'],[])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM model_providers').fetchone()[0],0)

    def test_pagination_returns_each_model_once(self):
        for n in range(12):
            profile=self.profile();profile['model_id']=f'fixture-{n}';self.service.register(profile)
        first=self.service.list({});second=self.service.list({'after_id':first['next_cursor']})
        self.assertEqual((len(first['items']),len(second['items'])),(10,2))
        self.assertIsNone(second['next_cursor'])
