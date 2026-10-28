"""Explicit, read-only source collection. All mutations target the Core database."""
import os
from pathlib import Path
import stat
from uuid import uuid4
from .libraries import LibraryError, valid_id, registration_path


class AssetService:
    def __init__(self, database):
        if database is None or getattr(database, 'connection', None) is None:
            raise LibraryError('DB_UNAVAILABLE')
        self.db = database.connection
        self.database = database

    def scan(self, params):
        if set(params) != {'library_id'} or not valid_id(params['library_id']):
            raise LibraryError('INVALID_PARAMS')
        row = self.db.execute('SELECT absolute_path FROM library_roots WHERE id=? AND enabled=1', (params['library_id'],)).fetchone()
        if not row:
            raise LibraryError('LIBRARY_NOT_FOUND')
        root = Path(registration_path(row[0])[0])
        found, failures = [], []
        def visit(directory):
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        info = entry.stat(follow_symlinks=False)
                        if entry.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            visit(Path(entry.path))
                        elif stat.S_ISREG(info.st_mode):
                            path = Path(entry.path)
                            if len(str(path).encode('utf-8')) > 3000:
                                failures.append('PATH_TOO_LONG')
                                continue
                            found.append((path, info))
            except OSError:
                failures.append('FOLDER_UNAVAILABLE')
        visit(root)
        # Never mark unseen files missing when a subtree could not be read.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = {os.path.normcase(path): (file_id, asset_id) for file_id, asset_id, path in self.db.execute(
                'SELECT f.id,f.asset_id,f.absolute_path FROM asset_files f JOIN assets a ON a.id=f.asset_id WHERE a.library_root_id=?', (params['library_id'],))}
            if not failures:
                self.db.execute('UPDATE asset_files SET exists_flag=0 WHERE asset_id IN (SELECT id FROM assets WHERE library_root_id=?)', (params['library_id'],))
            for path, info in found:
                key = os.path.normcase(str(path))
                if key in existing:
                    file_id, asset_id = existing[key]
                    self.db.execute('UPDATE asset_files SET size_bytes=?,mtime_ns=?,exists_flag=1 WHERE id=?', (info.st_size, info.st_mtime_ns, file_id))
                else:
                    asset_id, file_id = str(uuid4()), str(uuid4())
                    self.db.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)', (asset_id, params['library_id'], path.name))
                    self.db.execute('INSERT INTO asset_files(id,asset_id,relative_path,absolute_path,extension,size_bytes,mtime_ns) VALUES (?,?,?,?,?,?,?)',
                        (file_id, asset_id, str(path.relative_to(root)), str(path), path.suffix.lower(), info.st_size, info.st_mtime_ns))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return {'processed': len(found), 'errors': len(failures), 'complete': not failures}

    def list(self, params):
        if set(params) - {'after_id'} or (params.get('after_id') is not None and not valid_id(params['after_id'])):
            raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute('''SELECT a.id,a.display_name,f.extension,a.library_root_id,f.relative_path,f.absolute_path,f.size_bytes,f.mtime_ns,f.exists_flag
            FROM assets a JOIN asset_files f ON f.asset_id=a.id JOIN library_roots l ON l.id=a.library_root_id
            WHERE l.enabled=1 AND a.id>? ORDER BY a.id LIMIT 2''', (params.get('after_id') or '',)).fetchall()
        items = [dict(zip(('id','name','kind','libraryId','relativePath','path','size','mtimeNs','exists'), row)) for row in rows[:1]]
        for item in items:
            item['kind'] = item['kind'].lstrip('.').upper() or 'FILE'
            item['exists'] = bool(item['exists'])
        return {'items': items, 'next_cursor': items[-1]['id'] if len(rows) > 1 else None}

    def get(self, params):
        if set(params) != {'asset_id'} or not valid_id(params['asset_id']): raise LibraryError('INVALID_PARAMS')
        row = self.db.execute('''SELECT f.absolute_path,l.absolute_path FROM asset_files f JOIN assets a ON a.id=f.asset_id
            JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''', (params['asset_id'],)).fetchone()
        if not row: return {'availability':'unavailable'}
        path, root = Path(row[0]), Path(row[1])
        try:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)): return {'availability':'unavailable'}
            info = path.stat()
            result = {'availability':'present','path':str(path),'size':info.st_size,'modified':info.st_mtime_ns // 1_000_000}
            if path.suffix.lower() in ('.png','.jpg','.jpeg'):
                from .thumbnails import thumbnail
                image = thumbnail(self.database, params)
                if image['status'] == 'ready': result.update(width=image['width'],height=image['height'])
            return result
        except FileNotFoundError: return {'availability':'missing','path':str(path)}
        except OSError: return {'availability':'unavailable'}
