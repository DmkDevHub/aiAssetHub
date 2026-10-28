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
        if not isinstance(params,dict) or set(params) != {'library_id'} or not valid_id(params['library_id']):
            raise LibraryError('INVALID_PARAMS')
        row = self.db.execute('SELECT absolute_path FROM library_roots WHERE id=? AND enabled=1', (params['library_id'],)).fetchone()
        if not row:
            raise LibraryError('LIBRARY_NOT_FOUND')
        root = Path(registration_path(row[0])[0])
        found, failures = [], []
        def visit(directory):
            try:
                directory_info=directory.lstat()
                if directory.is_symlink() or getattr(directory_info,'st_file_attributes',0) & 0x400:
                    failures.append('REPARSE_POINT')
                    return
                if not directory.resolve(strict=True).is_relative_to(root):
                    failures.append('OUTSIDE_ROOT')
                    return
                with os.scandir(directory) as entries:
                    for entry in entries:
                        info = entry.stat(follow_symlinks=False)
                        if entry.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            visit(Path(entry.path))
                        elif stat.S_ISREG(info.st_mode):
                            path = Path(entry.path)
                            if not path.resolve(strict=True).is_relative_to(root):
                                failures.append('OUTSIDE_ROOT')
                                continue
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
            existing = {os.path.normcase(path): (file_id, asset_id, size, mtime, present) for file_id, asset_id, path, size, mtime, present in self.db.execute(
                'SELECT f.id,f.asset_id,f.absolute_path,f.size_bytes,f.mtime_ns,f.exists_flag FROM asset_files f JOIN assets a ON a.id=f.asset_id WHERE a.library_root_id=?', (params['library_id'],))}
            counts={'new':0,'changed':0,'missing':0}
            seen=set()
            def observation(file_id, change):
                self.db.execute("""INSERT INTO asset_observations(asset_file_id,metadata_json,scanned_at) VALUES (?,json_object('scan_change',?),strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    ON CONFLICT(asset_file_id) DO UPDATE SET metadata_json=json_set(metadata_json,'$.scan_change',?),scanned_at=excluded.scanned_at""", (file_id,change,change))
            if not failures:
                self.db.execute('UPDATE asset_files SET exists_flag=0 WHERE asset_id IN (SELECT id FROM assets WHERE library_root_id=?)', (params['library_id'],))
            for path, info in found:
                key = os.path.normcase(str(path))
                seen.add(key)
                if key in existing:
                    file_id, asset_id, size, mtime, present = existing[key]
                    change='changed' if (size,mtime,present)!=(info.st_size,info.st_mtime_ns,1) else 'unchanged'
                    self.db.execute('UPDATE asset_files SET size_bytes=?,mtime_ns=?,exists_flag=1 WHERE id=?', (info.st_size, info.st_mtime_ns, file_id))
                else:
                    change='new'
                    asset_id, file_id = str(uuid4()), str(uuid4())
                    self.db.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)', (asset_id, params['library_id'], path.name))
                    self.db.execute('INSERT INTO asset_files(id,asset_id,relative_path,absolute_path,extension,size_bytes,mtime_ns) VALUES (?,?,?,?,?,?,?)',
                        (file_id, asset_id, str(path.relative_to(root)), str(path), path.suffix.lower(), info.st_size, info.st_mtime_ns))
                observation(file_id,change)
                if change in counts: counts[change]+=1
            if not failures:
                for key, (file_id,asset_id,size,mtime,present) in existing.items():
                    if key not in seen:
                        observation(file_id,'missing')
                        counts['missing']+=int(bool(present))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return {'processed': len(found), 'errors': len(failures), 'complete': not failures, **counts}

    def list(self, params):
        if not isinstance(params,dict) or set(params) - {'after_id'} or (params.get('after_id') is not None and not valid_id(params['after_id'])):
            raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute('''SELECT a.id,coalesce(u.title_override,a.display_name),f.extension,a.library_root_id,f.relative_path,f.absolute_path,f.size_bytes,f.mtime_ns,f.exists_flag,json_extract(o.metadata_json,'$.scan_change')
            FROM assets a JOIN asset_files f ON f.asset_id=a.id JOIN library_roots l ON l.id=a.library_root_id
            LEFT JOIN asset_observations o ON o.asset_file_id=f.id
            LEFT JOIN asset_user_annotations u ON u.asset_id=a.id
            WHERE l.enabled=1 AND a.id>? ORDER BY a.id LIMIT 2''', (params.get('after_id') or '',)).fetchall()
        items = [dict(zip(('id','name','kind','libraryId','relativePath','path','size','mtimeNs','exists','scanChange'), row)) for row in rows[:1]]
        for item in items:
            item['hasActiveResult'] = bool(self.db.execute('SELECT 1 FROM asset_active_results WHERE asset_id=?', (item['id'],)).fetchone())
            attempt = self.db.execute('SELECT status FROM analysis_runs WHERE asset_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (item['id'],)).fetchone()
            item['lastAttemptState'] = attempt[0] if attempt else None
            active = self.db.execute('SELECT r.created_at FROM asset_active_results ar JOIN analysis_results r ON r.id=ar.analysis_result_id WHERE ar.asset_id=?', (item['id'],)).fetchone()
            item['lastAnalysisAt'] = active[0] if active else None
            item['userTags'] = [row[0] for row in self.db.execute("SELECT t.label FROM tags t JOIN asset_tags at ON at.tag_id=t.id WHERE at.asset_id=? AND at.source='user' ORDER BY t.normalized_label", (item['id'],))]
            item['kind'] = item['kind'].lstrip('.').upper() or 'FILE'
            item['exists'] = bool(item['exists'])
            item['mtimeNs'] = str(item['mtimeNs']) # Preserve nanoseconds across the JS integer boundary.
        return {'items': items, 'next_cursor': items[-1]['id'] if len(rows) > 1 else None}

    def get(self, params):
        if not isinstance(params,dict) or set(params) != {'asset_id'} or not valid_id(params['asset_id']): raise LibraryError('INVALID_PARAMS')
        row = self.db.execute('''SELECT f.absolute_path,l.absolute_path FROM asset_files f JOIN assets a ON a.id=f.asset_id
            JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''', (params['asset_id'],)).fetchone()
        if not row: return {'availability':'unavailable'}
        path, root = Path(row[0]), Path(row[1])
        try:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)): return {'availability':'unavailable'}
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0) & 0x400: return {'availability':'unavailable'}
            result = {'availability':'present','path':str(path),'size':info.st_size,'modified':info.st_mtime_ns // 1_000_000}
            if path.suffix.lower() in ('.png','.jpg','.jpeg'):
                from .thumbnails import thumbnail
                image = thumbnail(self.database, params)
                if image['status'] == 'ready': result.update(width=image['width'],height=image['height'])
            return result
        except FileNotFoundError: return {'availability':'missing','path':str(path)}
        except OSError: return {'availability':'unavailable'}
