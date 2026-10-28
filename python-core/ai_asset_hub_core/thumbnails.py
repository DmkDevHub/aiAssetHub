import base64
import hashlib
import io
import os
from pathlib import Path
import warnings
from uuid import uuid4
from .libraries import LibraryError, valid_id

def thumbnail(database, params):
    if not isinstance(params, dict) or set(params) != {'asset_id'} or not valid_id(params['asset_id']):
        raise LibraryError('INVALID_PARAMS')
    row = database.connection.execute('''SELECT f.absolute_path,l.absolute_path FROM asset_files f JOIN assets a ON a.id=f.asset_id
        JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''', (params['asset_id'],)).fetchone()
    if not row: return {'status':'unavailable'}
    path, root = Path(row[0]), Path(row[1])
    try:
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or path.is_symlink(): return {'status':'unavailable'}
        for parent in path.parents:
            if parent == root: break
            if parent.is_symlink() or getattr(parent.stat(), 'st_file_attributes', 0) & 0x400: return {'status':'unavailable'}
        if path.suffix.lower() not in ('.png','.jpg','.jpeg'): return {'status':'unsupported'}
        info = path.stat()
        if info.st_size > 50_000_000: return {'status':'too_large'}
        from PIL import Image, ImageOps
        cache = database.path.parent / 'thumbnails'
        cache.mkdir(exist_ok=True)
        target = cache / (hashlib.sha256(f'{params["asset_id"]}:{info.st_size}:{info.st_mtime_ns}:v1'.encode()).hexdigest() + '.jpg')
        if cache.is_symlink() or target.is_symlink(): return {'status':'unavailable'}
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in ('PNG','JPEG') or image.width * image.height > 16_000_000: return {'status':'too_large'}
                width,height = image.size
                if not target.exists():
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((96,96))
                    output = io.BytesIO()
                    image.convert('RGB').save(output, format='JPEG', quality=50)
                    payload = output.getvalue()
                    if len(payload) > 6500: return {'status':'too_large'}
                    temporary = target.with_suffix('.' + str(uuid4()) + '.tmp')
                    try:
                        temporary.write_bytes(payload)
                        os.replace(temporary,target)
                    finally: temporary.unlink(missing_ok=True)
        payload = target.read_bytes()
        if len(payload) > 6500: return {'status':'unavailable'}
        return {'status':'ready','width':width,'height':height,'url':'data:image/jpeg;base64,' + base64.b64encode(payload).decode('ascii')}
    except FileNotFoundError: return {'status':'missing'}
    except Exception: return {'status':'unavailable'}
