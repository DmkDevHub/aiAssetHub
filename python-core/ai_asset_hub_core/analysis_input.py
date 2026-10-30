"""Bounded, read-only inputs restricted to active registered roots."""
from pathlib import Path
import stat
from .libraries import LibraryError


def prepare_image(database, identifier, expected):
    import os
    import hashlib
    import io
    import base64
    from PIL import Image
    path,info=source_info(database,identifier)
    if path.suffix.lower() not in ('.png','.jpg','.jpeg'):raise LibraryError('UNSUPPORTED_FORMAT')
    if info.st_size>20_000_000:raise LibraryError('INPUT_TOO_LARGE')
    if expected.get('size')!=info.st_size or expected.get('mtimeNs')!=info.st_mtime_ns:raise LibraryError('FILE_CHANGED')
    with open(path,'rb') as source:
        opened=os.fstat(source.fileno())
        if os.name=='nt':
            import ctypes
            import msvcrt
            from ctypes import wintypes
            function=ctypes.WinDLL('kernel32',use_last_error=True).GetFinalPathNameByHandleW
            function.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];function.restype=wintypes.DWORD
            buffer=ctypes.create_unicode_buffer(32768)
            length=function(msvcrt.get_osfhandle(source.fileno()),buffer,len(buffer),0)
            if not 0<length<len(buffer):raise LibraryError('FILE_UNAVAILABLE')
            actual=buffer.value
            if actual.startswith('\\\\?\\'):actual=actual[4:]
            root=database.connection.execute('SELECT l.absolute_path FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1',(identifier,)).fetchone()
            if not root or not Path(actual).is_relative_to(Path(root[0])):raise LibraryError('FILE_UNAVAILABLE')
        if (opened.st_size,opened.st_mtime_ns)!=(info.st_size,info.st_mtime_ns):raise LibraryError('FILE_CHANGED')
        raw=source.read(20_000_001)
        after=os.fstat(source.fileno())
        if len(raw)>20_000_000:raise LibraryError('INPUT_TOO_LARGE')
        if (after.st_size,after.st_mtime_ns)!=(info.st_size,info.st_mtime_ns):raise LibraryError('FILE_CHANGED')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG'):raise LibraryError('UNSUPPORTED_FORMAT')
            if image.width*image.height>16_000_000:raise LibraryError('INPUT_TOO_LARGE')
            image.load()
            technical={'schema':'image-observation.v1','source':'parser','format':image.format,
                'width':image.width,'height':image.height,'channels':len(image.getbands()),
                'hasAlphaChannel':'A' in image.getbands() or 'transparency' in image.info,
                'hasTransparentPixels':image.convert('RGBA').getchannel('A').getextrema()[0]<255,
                'frameCount':getattr(image,'n_frames',1)}
            image.thumbnail((512,512));rgba=image.convert('RGBA');converted=Image.new('RGB',rgba.size,'white');converted.paste(rgba,mask=rgba.getchannel('A'))
            output=io.BytesIO();converted.save(output,format='JPEG',quality=80)
    except LibraryError:raise
    except Exception:raise LibraryError('INVALID_IMAGE') from None
    return {'image':base64.b64encode(output.getvalue()).decode('ascii'),'fingerprint':hashlib.sha256(raw).hexdigest(),
            'size':info.st_size,'mtimeNs':info.st_mtime_ns,'technical':technical}


def source_info(database, identifier):
    row=database.connection.execute('''SELECT f.absolute_path,l.absolute_path FROM asset_files f JOIN assets a ON a.id=f.asset_id
        JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''',(identifier,)).fetchone()
    if not row:raise LibraryError('FILE_UNAVAILABLE')
    path,root=map(Path,row)
    try:
        if root.is_symlink() or getattr(root.lstat(),'st_file_attributes',0)&0x400:raise LibraryError('FILE_UNAVAILABLE')
        base=root.resolve(strict=True);resolved=path.resolve(strict=True)
        if not resolved.is_relative_to(base):raise LibraryError('FILE_UNAVAILABLE')
        current=path
        while current!=root:
            info=current.lstat()
            if current.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:raise LibraryError('FILE_UNAVAILABLE')
            if current.parent==current:raise LibraryError('FILE_UNAVAILABLE')
            current=current.parent
        info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise LibraryError('FILE_UNAVAILABLE')
        return path,info
    except PermissionError:raise LibraryError('FILE_PERMISSION_DENIED') from None
    except FileNotFoundError:raise LibraryError('FILE_MISSING') from None
    except OSError:raise LibraryError('FILE_UNAVAILABLE') from None
