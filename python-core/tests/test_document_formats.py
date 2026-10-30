import io
import struct
import unittest
import zipfile
from unittest.mock import patch
from ai_asset_hub_core.document_formats import inspect_format
from ai_asset_hub_core.libraries import LibraryError


def font_fixture():
    head=bytearray(54);struct.pack_into('>I',head,12,0x5F0F3CF5);struct.pack_into('>H',head,18,1024)
    return b'\0\1\0\0'+struct.pack('>4H',2,0,0,0)+struct.pack('>4sIII',b'head',0,44,54)+struct.pack('>4sIII',b'maxp',0,98,6)+head+struct.pack('>IH',0x10000,12)


def mp4_fixture():
    def box(kind,data):return struct.pack('>I4s',8+len(data),kind)+data
    mvhd=b'\0'*12+struct.pack('>II',1000,2500)
    return box(b'ftyp',b'isom\0\0\0\0isom')+box(b'moov',box(b'mvhd',mvhd)+box(b'trak',b''))


class DocumentFormatTests(unittest.TestCase):
    def test_code_data_scene_and_vfx_declarations_never_execute_or_open_references(self):
        with patch('builtins.exec',side_effect=AssertionError('no execution')):
            value=inspect_format('.py',b'import os\ndef thing():\n  raise RuntimeError()\n')
        self.assertEqual(value['declarations'],['thing']);self.assertEqual(value['references'],['os'])
        self.assertEqual(inspect_format('.json',b'{"items":[1,2]}')['keys'],['items'])
        self.assertEqual(inspect_format('.csv',b'name,value\nx,=DANGEROUS()\n')['rowCount'],2)
        for extension in ('.unity','.prefab','.vfx','.mat'):
            value=inspect_format(extension,b'%YAML 1.1\n--- !u!1 &1\nref: {guid: 0123456789abcdef0123456789abcdef}\n')
            self.assertEqual(value['declarationCount'],1);self.assertEqual(len(value['references']),1)
            self.assertEqual(value['runtimeBehavior'],'unknown')

    def test_zip_lists_unsafe_members_without_decompression_or_extraction(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:archive.writestr('../outside.py',b'raise RuntimeError()')
        with patch('zipfile.ZipFile.open',side_effect=AssertionError('no decompression')):
            value=inspect_format('.zip',output.getvalue())
        self.assertTrue(value['entries'][0]['unsafePath']);self.assertEqual(value['extraction'],'never')

    def test_font_and_video_header_values_are_not_claimed_as_decoded_content(self):
        value=inspect_format('.ttf',font_fixture())
        self.assertEqual(value['unitsPerEm'],1024);self.assertEqual(value['declaredGlyphCount'],12)
        self.assertEqual(value['glyphRendering'],'unsupported')
        value=inspect_format('.mp4',mp4_fixture())
        self.assertEqual(value['declaredDurationSeconds'],2.5);self.assertEqual(value['declaredTrackCount'],1)
        self.assertEqual(value['frameDecode'],'unsupported');self.assertIsNone(value['fps'])

    def test_bad_formats_limits_and_duplicate_json_fail_closed(self):
        for extension,raw in (('.json',b'{"a":1,"a":2}'),('.py',b'def ???'),('.zip',b'bad'),('.ttf',font_fixture()[:-1]),('.mp4',mp4_fixture()[:-1]),('.vfx',b'not YAML'),('.unitypackage',b'archive'),('.txt',b'\0')):
            with self.subTest(extension=extension),self.assertRaises(LibraryError):inspect_format(extension,raw)
        with self.assertRaisesRegex(LibraryError,'INPUT_TOO_LARGE'):inspect_format('.txt',b'x'*32769)
