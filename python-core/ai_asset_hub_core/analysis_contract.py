"""Versioned, read-only description of implemented analysis paths.

Categories describe intent, never infer a classification or enable a decoder.
Content SHA-256 is computed only when the approved worker reads an input.
"""
import hashlib
import json
from pathlib import Path

VERSION = 'asset-analysis.v2'
INPUT_VERSION = 'bounded-multiformat.v1'
OUTPUT_VERSION = 'asset-description.v4'
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
_KNOWN_UNSUPPORTED = frozenset(('.wav', '.mp3', '.flac', '.ogg', '.m4a', '.fbx',
    '.obj', '.gltf', '.glb', '.blend', '.gif', '.webp', '.svg', '.mp4', '.mov',
    '.cs', '.py', '.json', '.csv', '.unity', '.prefab', '.zip', '.unitypackage',
    '.ttf', '.otf', '.anim', '.controller', '.shader', '.mat'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False).encode('utf-8')).hexdigest()


def input_support(path):
    extension = Path(path).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return 'supported'
    return 'unsupported' if extension in _KNOWN_UNSUPPORTED else 'unknown'


def contract(database):
    from .inference import SCHEMA, PROMPT, AUDIO_PROMPT, WIREFRAME_PROMPT, CONTACT_PROMPT,TEXT_PROMPT
    # Bind the actual persisted immutable dictionaries, including custom versions.
    dictionaries = [{'version': row[0], 'kind': row[1], 'sha256': digest(json.loads(row[2]))}
        for row in database.connection.execute(
            'SELECT version,kind,payload_json FROM classification_dictionaries ORDER BY kind,version')]
    paths={1:'PNG/JPEG/GIF/APNG',2:'OBJ/glTF2/GLB2',3:'GIF/APNG/glTF2-clips',4:'PNG/JPEG/material-declarations',
        5:'VFX/shader-declarations',6:'PCM-WAV',7:'PNG/JPEG',8:'images/geometry/scene-declarations',
        9:'images/geometry',10:'JSON/CSV',11:'SFNT/text',12:'UTF-8-code',13:'Unity-declarations',14:'ZIP-directory'}
    return {
        'version': VERSION,
        'inputSchema': INPUT_VERSION,
        'outputSchema': OUTPUT_VERSION,
        'outputSchemaSha256': digest(SCHEMA),
        'promptSha256': digest(PROMPT),
        'audioPromptSha256':digest(AUDIO_PROMPT),
        'textPromptSha256':digest(TEXT_PROMPT),
        'text':{'inputBytes':4096,'technicalBytes':32768,'encoding':'UTF-8','transmission':'full-reviewed-text-and-fixed-prompt','execution':'never'},
        'documents':{'ZIP':'directory-only;never-decompress','TTF/OTF':'SFNT-directory/head/maxp','MP4/MOV':'ftyp/mvhd-header-only','Unity/VFX':'declarations/guids-only','videoInference':'unsupported'},
        'animation':{'technical':['GIF','APNG','glTF2-clips'],'imagePreview':'first-8-contact-sheet','maxFrames':64,'maxDecodedPixels':32000000,'posed3DRender':'unsupported'},
        'contactPromptSha256':digest(CONTACT_PROMPT),
        'wireframePromptSha256':digest(WIREFRAME_PROMPT),
        'geometry':{'technical':['OBJ','glTF2','GLB2'],'preview':'mesh-local-XY-wireframe',
            'maxVertices':100000,'maxFaces':100000,'previewFaces':10000,'surfaceRender':'unsupported',
            'externalDependencies':'not-opened','FBX':'unsupported','BLEND':'unsupported'},
        'audio':{'technical':'PCM-WAV','semantic':'openrouter-audio-input','maxSeconds':60,
            'localInference':'unsupported','transmission':'original-pcm-wav-and-fixed-prompt',
            'output':'description,tags,audioSuggestions;v1'},
        'dictionaries': dictionaries,
        'supportMatrix': [
            {'typeCode': f'A{i:02}',
             'imageDescription': 'supported' if i in (1, 4, 7, 8, 9) else 'unsupported',
             'structuredClassification': 'image-proposals' if i in (1,4,7,8,9) else 'unsupported',
             'nativeFormatAnalysis': 'partial', 'observedPaths':paths[i]} for i in range(1, 15)],
        'supportedExtensions': list(IMAGE_EXTENSIONS),
        'requiredModelModality': 'image',
        'inputScope': 'single-registered-file',
        'multiFileAnalysis': 'unsupported',
        'reviewFingerprint': 'asset-id,size,mtime-ns,availability;sha256-manifest.v1',
        'executionFingerprint': 'original-bytes;sha256.v1',
        'transfer': {'media': 'derived-jpeg', 'maxEdge': 512, 'prompt': OUTPUT_VERSION,
                     'originalFile': False, 'metadata': False},
        'limits': {'inputBytes': 20_000_000, 'decodedPixels': 16_000_000},
        'decodeValidation': 'at-execution',
    }
