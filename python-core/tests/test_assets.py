from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryService

class AssetTests(unittest.TestCase):
    def test_thumbnail_is_derived_cached_and_source_stays_unchanged(self):
        from PIL import Image
        from ai_asset_hub_core.thumbnails import thumbnail
        root = Path(__file__).resolve().parents[2] / '.artifacts' / 'scan-tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            base = Path(directory)
            source = base / 'images'
            source.mkdir()
            image = source / 'real.png'
            Image.new('RGB',(200,120),'red').save(image)
            before = image.read_bytes()
            database = Database(base / 'data.sqlite')
            try:
                library = LibraryService(database).register({'path':str(source)})['library']['id']
                service = AssetService(database)
                service.scan({'library_id':library})
                asset = service.list({})['items'][0]['id']
                first = thumbnail(database, {'asset_id':asset})
                self.assertEqual(first['status'],'ready')
                self.assertEqual((first['width'],first['height']),(200,120))
                metadata=service.get({'asset_id':asset})
                self.assertEqual(metadata['size'],len(before))
                self.assertEqual(metadata['width'],200)
                self.assertEqual(metadata['availability'],'present')
                self.assertEqual(thumbnail(database,{'asset_id':asset}), first)
                self.assertEqual(image.read_bytes(),before)
                self.assertEqual(len(list((base/'thumbnails').glob('*.jpg'))),1)
            finally: database.close()

    def test_recursive_scan_is_explicit_stable_and_preserves_sources(self):
        root = Path(__file__).resolve().parents[2] / '.artifacts' / 'scan-tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            base = Path(directory)
            source = base / '한글 원본'
            (source / 'nested').mkdir(parents=True)
            (source / 'nested' / 'a.txt').write_text('original', encoding='utf-8')
            database = Database(base / 'data.sqlite')
            try:
                identifier = LibraryService(database).register({'path':str(source)})['library']['id']
                service = AssetService(database)
                self.assertEqual(service.list({})['items'], [])
                with patch('socket.socket', side_effect=AssertionError('network forbidden')):
                    self.assertEqual(service.scan({'library_id':identifier})['processed'], 1)
                item = service.list({})['items'][0]
                self.assertEqual(item['name'], 'a.txt')
                self.assertEqual(item['size'], 8)
                service.scan({'library_id':identifier})
                self.assertEqual(service.list({})['items'][0]['id'], item['id'])
                self.assertEqual((source / 'nested' / 'a.txt').read_text(), 'original')
                self.assertEqual(database.connection.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0], 0)
            finally:
                database.close()
