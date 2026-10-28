from pathlib import Path
import tempfile
import unittest
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryService, LibraryError
from ai_asset_hub_core.annotations import AnnotationService


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / '.artifacts' / 'annotation-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'; self.source.mkdir()
        (self.source / '나무.png').write_bytes(b'original')
        self.db = Database(self.base / 'db.sqlite')
        library = LibraryService(self.db).register({'path':str(self.source)})['library']['id']
        AssetService(self.db).scan({'library_id':library})
        self.id = AssetService(self.db).list({})['items'][0]['id']
        self.service = AnnotationService(self.db)

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_tags_normalize_delete_persist_without_jobs_or_source_writes(self):
        edit = lambda add, remove: self.service.tags({'asset_id':self.id,'add':add,'remove':remove})
        self.assertEqual(edit([' 숲 ', 'Forest', 'forest'], [])['tags'], ['forest','숲'])
        self.assertEqual(edit([], ['FOREST'])['tags'], ['숲'])
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        self.service = AnnotationService(self.db)
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'], ['숲'])
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_invalid_tags_are_atomic(self):
        for value in [[''], ['x'*65], ['line\nbreak'], ['x']*33, [None]]:
            with self.assertRaises(LibraryError):
                self.service.tags({'asset_id':self.id,'add':value,'remove':[]})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'], [])

    def test_user_description_title_override_and_restore_preserve_source(self):
        self.service.save({'asset_id':self.id,'title':'별칭','description':'숲 설명'})
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'별칭')
        self.db.close(); self.db = Database(self.base / 'db.sqlite'); self.service = AnnotationService(self.db)
        self.assertEqual(self.service.get({'asset_id':self.id})['description'],'숲 설명')
        self.service.save({'asset_id':self.id,'title':'','description':''})
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'나무.png')
        with self.assertRaises(LibraryError): self.service.save({'asset_id':self.id,'title':'a'*129,'description':''})
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_batch_tags_are_atomic_and_keep_unrelated_tags(self):
        from uuid import uuid4
        other=str(uuid4()); library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        self.db.connection.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)',(other,library,'other'))
        self.service.tags({'asset_id':self.id,'add':['keep'],'remove':[]})
        result=self.service.batch({'asset_ids':[self.id,other],'add':['숲'],'remove':[]})
        self.assertEqual(result,{'updated':2})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'],['keep','숲'])
        with self.assertRaises(LibraryError):
            self.service.batch({'asset_ids':[self.id,str(uuid4())],'add':['rollback'],'remove':['keep']})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'],['keep','숲'])
        self.service.batch({'asset_ids':[self.id,other],'add':[],'remove':['숲']})
        self.assertEqual(self.service.get({'asset_id':other})['tags'],[])
