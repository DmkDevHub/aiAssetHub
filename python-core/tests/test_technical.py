import hashlib
import io
import threading
import unittest
import wave
from unittest.mock import patch
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.technical import Technical,parse


def wav():
    output=io.BytesIO()
    with wave.open(output,'wb') as writer:
        writer.setparams((2,2,8000,8000,'NONE','not compressed'))
        writer.writeframes(b'\0'*32000)
    return output.getvalue()


class TechnicalTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def register(self,name,raw):
        (self.source/name).write_bytes(raw)
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        return self.db.connection.execute('SELECT a.id FROM assets a JOIN asset_files f ON f.asset_id=a.id WHERE f.relative_path=?',(name,)).fetchone()[0]

    def test_pcm_wav_is_measured_without_inference_and_survives_reopen(self):
        raw=wav();asset=self.register('소리.wav',raw);service=Technical(self.db)
        with patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):
            self.assertIsNone(service.get({'asset_id':asset})['observation'])
            result=service.collect({'asset_id':asset,'confirmed':True})['observation']
        self.assertEqual(result['value']['durationSeconds'],1)
        self.assertEqual(result['value']['channels'],2)
        self.assertEqual(result['value']['sampleRate'],8000)
        self.assertEqual(self.db.connection.execute('SELECT duration_ms FROM asset_observations o JOIN asset_files f ON f.id=o.asset_file_id WHERE f.asset_id=?',(asset,)).fetchone()[0],1000)
        self.assertIsNone(result['value']['transcript'])
        self.assertEqual(result['inputFingerprint'],hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.source/'소리.wav').read_bytes(),raw)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        from ai_asset_hub_core.database import Database
        self.db.close();self.db=Database(self.base/'db.sqlite')
        self.assertEqual(Technical(self.db).get({'asset_id':asset})['observation'],result)
        self.assertFalse(Technical(self.db).get({'asset_id':asset})['stale'])
        (self.source/'소리.wav').write_bytes(raw+b'changed')
        self.assertTrue(Technical(self.db).get({'asset_id':asset})['stale'])

    def test_corrupt_truncated_unsupported_cancel_and_confirmation_are_not_successes(self):
        for extension,raw in (('.wav',b'bad'),('.wav',wav()[:-1]),('.mp3',b'ID3')):
            with self.subTest(extension=extension),self.assertRaises(LibraryError):parse(extension,raw)
        canceled=threading.Event();canceled.set()
        with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):parse('.wav',wav(),canceled)
        service=Technical(self.db)
        for params in ({'asset_id':self.id,'confirmed':False},{'asset_id':str(uuid4()),'confirmed':True}):
            with self.assertRaises(LibraryError):service.collect(params)
        self.assertIsNone(service.get({'asset_id':self.id})['observation'])

    def test_core_dispatch_rejects_unapproved_collection_and_redacts_parser_errors(self):
        from ai_asset_hub_core.application import CoreApplication
        app=CoreApplication(self.db)
        call=lambda method,params:app.handle({'request_id':str(uuid4()),'method':method,'params':params})
        self.assertTrue(call('asset.technical',{'asset_id':self.id})['ok'])
        result=call('asset.technical.collect',{'asset_id':self.id,'confirmed':False})
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'INVALID_PARAMS')
        result=call('asset.technical.collect',{'asset_id':self.id,'confirmed':True})
        self.assertFalse(result['ok']);self.assertNotIn(str(self.source),str(result))
