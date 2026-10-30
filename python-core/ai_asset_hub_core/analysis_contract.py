"""Versioned, read-only description of implemented analysis paths.

Categories describe intent, never infer a classification or enable a decoder.
Content SHA-256 is computed only when the approved worker reads an input.
"""
import hashlib
import json
from pathlib import Path

VERSION = 'asset-analysis.v1'
INPUT_VERSION = 'bounded-image.v1'
OUTPUT_VERSION = 'asset-description.v2'
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
    from .inference import SCHEMA, PROMPT
    # Bind the actual persisted immutable dictionaries, including custom versions.
    dictionaries = [{'version': row[0], 'kind': row[1], 'sha256': digest(json.loads(row[2]))}
        for row in database.connection.execute(
            'SELECT version,kind,payload_json FROM classification_dictionaries ORDER BY kind,version')]
    return {
        'version': VERSION,
        'inputSchema': INPUT_VERSION,
        'outputSchema': OUTPUT_VERSION,
        'outputSchemaSha256': digest(SCHEMA),
        'promptSha256': digest(PROMPT),
        'dictionaries': dictionaries,
        'supportMatrix': [
            {'typeCode': f'A{i:02}',
             'imageDescription': 'supported' if i in (1, 4, 7, 8, 9) else 'unsupported',
             'structuredClassification': 'unsupported',
             'nativeFormatAnalysis': 'unsupported'} for i in range(1, 15)],
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
