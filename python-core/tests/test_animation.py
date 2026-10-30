import base64
import io
import json
import struct
import threading
import unittest
from PIL import Image
from test_geometry import gltf_fixture
from ai_asset_hub_core.animation import image_animation
from ai_asset_hub_core.geometry import geometry
from ai_asset_hub_core.libraries import LibraryError


def gif():
    output=io.BytesIO()
    Image.new('RGBA',(16,16),'red').save(output,format='GIF',save_all=True,
        append_images=[Image.new('RGBA',(16,16),'blue')],duration=[100,200],loop=0)
    return output.getvalue()


class AnimationTests(unittest.TestCase):
    def test_gif_measures_frames_durations_loop_and_contact_sheet(self):
        value,encoded=image_animation(gif(),True)
        self.assertEqual(value['frameCount'],2);self.assertEqual(value['durationSeconds'],.3)
        self.assertEqual(value['frameDurationsMs'],[100,200]);self.assertEqual(value['loopCount'],0)
        self.assertIsNone(value['fps']);self.assertIsNone(value['rig']);self.assertEqual(value['previewFrames'],2)
        image=Image.open(io.BytesIO(base64.b64decode(encoded)));self.assertEqual(image.size,(512,256))
        self.assertGreater(image.getpixel((5,5))[0],200);self.assertGreater(image.getpixel((133,5))[2],200)

    def test_static_unknown_timing_limit_and_cancel_are_not_animation_success(self):
        output=io.BytesIO();Image.new('RGB',(2,2)).save(output,format='PNG')
        self.assertIsNone(image_animation(output.getvalue())[0]['durationSeconds'])
        with self.assertRaises(LibraryError):image_animation(output.getvalue(),True)
        canceled=threading.Event();canceled.set()
        with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):image_animation(gif(),True,canceled)
        with self.assertRaises(LibraryError):image_animation(b'not a GIF',True)

    def test_gltf_clip_uses_actual_times_and_root_track_without_guessing_loop_or_fps(self):
        document=gltf_fixture();raw=base64.b64decode(document['buffers'][0]['uri'].split(',')[1])
        raw+=struct.pack('<2f',0,2)+struct.pack('<6f',0,0,0,1,0,0)
        document['buffers'][0]={'uri':'data:application/octet-stream;base64,'+base64.b64encode(raw).decode(),'byteLength':len(raw)}
        document['bufferViews'] += [{'buffer':0,'byteOffset':36,'byteLength':8},{'buffer':0,'byteOffset':44,'byteLength':24}]
        document['accessors'] += [{'bufferView':1,'componentType':5126,'count':2,'type':'SCALAR'}, {'bufferView':2,'componentType':5126,'count':2,'type':'VEC3'}]
        document['animations']=[{'name':'clip','samplers':[{'input':1,'output':2}], 'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]
        clip=geometry('.gltf',json.dumps(document).encode())[0]['clips'][0]
        self.assertEqual(clip['durationSeconds'],2);self.assertIsNone(clip['loop']);self.assertIsNone(clip['fps'])
        self.assertEqual(clip['rootTranslation'][0]['localTranslationDelta'],[1,0,0])
