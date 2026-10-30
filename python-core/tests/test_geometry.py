import base64
import io
import json
import struct
import unittest
from PIL import Image
from unittest.mock import patch
import test_annotations
import test_technical
from ai_asset_hub_core.geometry import geometry,wireframe
from ai_asset_hub_core.technical import Technical
from ai_asset_hub_core.libraries import LibraryError

OBJ=b'mtllib ../never-open.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl sample\nf 1 2 3\n'


def gltf_fixture(external=False):
    binary=struct.pack('<9f',0,0,0,1,0,0,0,1,0)
    return {'asset':{'version':'2.0'},'buffers':[{'uri':'https://example.invalid/no-open' if external else 'data:application/octet-stream;base64,'+base64.b64encode(binary).decode(),'byteLength':len(binary)}],
        'bufferViews':[{'buffer':0,'byteLength':36}], 'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}], 'nodes':[{}], 'skins':[{'joints':[0]}],'materials':[{}]}


class GeometryTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    register=test_technical.TechnicalTests.register

    def test_obj_counts_preview_components_and_source_preservation(self):
        asset=self.register('한글.obj',OBJ)
        with patch('builtins.open',wraps=open) as opened:
            value=Technical(self.db).collect({'asset_id':asset,'confirmed':True})['observation']['value']
            self.assertEqual(len(opened.call_args_list),1)
        self.assertEqual((value['vertexCount'],value['triangleCount']),(3,1))
        self.assertEqual(value['dependencies'],['../never-open.mtl'])
        self.assertIsNone(value['units']);self.assertIsNone(value['boneCount'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_components').fetchone()[0],1)
        Technical(self.db).collect({'asset_id':asset,'confirmed':True})
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_components').fetchone()[0],1)
        result,points,faces=geometry('.obj',OBJ)
        image=Image.open(io.BytesIO(base64.b64decode(wireframe(points,faces))))
        self.assertEqual(image.size,(512,512));self.assertEqual((self.source/'한글.obj').read_bytes(),OBJ)

    def test_embedded_gltf_and_glb_decode_geometry_and_external_references_never_open(self):
        document=gltf_fixture();result,points,faces=geometry('.gltf',json.dumps(document).encode())
        self.assertEqual((result['decodedVertexCount'],result['decodedTriangleCount'],result['boneCount']),(3,1,1))
        self.assertEqual(result['decodedBounds']['max'],[1,1,0])
        external=geometry('.gltf',json.dumps(gltf_fixture(True)).encode())[0]
        self.assertEqual(external['render'],'unsupported');self.assertEqual(external['decodedVertexCount'],0)
        data=base64.b64decode(document['buffers'][0].pop('uri').split(',')[1]);raw=json.dumps(document).encode();raw+=b' '*((-len(raw))%4)
        glb=struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(data))+struct.pack('<II',len(raw),0x4E4F534A)+raw+struct.pack('<II',len(data),0x004E4942)+data
        self.assertEqual(geometry('.glb',glb)[0]['decodedVertexCount'],3)

    def test_malformed_indices_nonfinite_and_limits_fail_closed(self):
        for raw in (b'v nan 0 0',b'v 0 0 0\nf 1 2 3',b'v 0 0 0\nf 0 0 0'):
            with self.assertRaises(LibraryError):geometry('.obj',raw)
        document=gltf_fixture();document['accessors'][0]['count']=100001
        with self.assertRaises(LibraryError):geometry('.gltf',json.dumps(document).encode())
        document=gltf_fixture();document['bufferViews'][0]['byteLength']=35
        with self.assertRaises(LibraryError):geometry('.gltf',json.dumps(document).encode())
        with self.assertRaises(LibraryError):geometry('.glb',b'glTF')
