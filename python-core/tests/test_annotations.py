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
        self.assertEqual(self.service.get({'asset_id':self.id}), {'tags':['숲']})
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_invalid_tags_are_atomic(self):
        for value in [[''], ['x'*65], ['line\nbreak'], ['x']*33, [None]]:
            with self.assertRaises(LibraryError):
                self.service.tags({'asset_id':self.id,'add':value,'remove':[]})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'], [])
