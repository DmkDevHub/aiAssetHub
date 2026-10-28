"""Bounded, read-only inputs restricted to active registered roots."""
from pathlib import Path
import stat
from .libraries import LibraryError


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
    except FileNotFoundError:raise LibraryError('FILE_MISSING') from None
    except OSError:raise LibraryError('FILE_UNAVAILABLE') from None
