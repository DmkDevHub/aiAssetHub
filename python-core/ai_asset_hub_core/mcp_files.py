"""Public composition projection. Only registered paths are stat'ed; no content reads."""
import json
import math
from pathlib import Path, PurePosixPath
from .libraries import LibraryError, valid_id


NUMBERS=frozenset(('width','height','channels','frameCount','durationSeconds','sampleRate','sampleWidthBytes',
    'sampleFrames','meshCount','vertexCount','polygonCount','triangleCount','decodedVertexCount','decodedTriangleCount','declaredVertexCount',
    'materialCount','skinCount','boneCount','uvCoordinateCount','uvAttributeCount','animationCount','lineCount',
    'entryCount','rowCount','columnCount','declarationCount','tableCount','unitsPerEm','declaredGlyphCount',
    'declaredDurationSeconds','declaredTrackCount','fps','loopCount'))
FORMATS=frozenset(('PNG','JPEG','GIF','WAV','OBJ','glTF2','GLTF','GLB','JSON','CSV','PY','CS','JS','TS','TXT','MD',
    'SHADER','HLSL','GLSL','UNITY','PREFAB','VFX','MAT','YAML','YML','ZIP','TTF','OTF','MP4','MOV'))


class McpFiles:
    def __init__(self,database,safe_path):self.db=database.connection;self.safe_path=safe_path

    def file(self,identifier):
        row=self.db.execute('''SELECT f.id,f.absolute_path,f.relative_path,f.extension,l.absolute_path,f.asset_id,l.enabled,
            o.width,o.height,o.duration_ms FROM asset_files f JOIN assets a ON a.id=f.asset_id
            JOIN library_roots l ON l.id=a.library_root_id LEFT JOIN asset_observations o ON o.asset_file_id=f.id WHERE f.id=?''',(identifier,)).fetchone()
        if not row or not row[6]:return {'id':identifier,'availability':'unavailable'},None
        path=self.safe_path(row[1],row[4],row[2]) if row[6] else None
        item=dict(id=row[0],ownerAssetId=row[5],relativePath=row[2] if path else None,
            kind=row[3].lstrip('.').upper() or 'FILE',availability='unavailable',width=row[7],height=row[8],durationMs=row[9],
            previewSupported=row[3].lower() in ('.png','.jpg','.jpeg'))
        info=None
        if path:
            try:
                info=path.stat()
                import stat
                if not stat.S_ISREG(info.st_mode):raise ValueError()
                item.update(path=str(path),availability='present',size=info.st_size,mtimeNs=str(info.st_mtime_ns))
            except FileNotFoundError:item.update(path=str(path),availability='missing');info=None
            except (OSError,ValueError):info=None;item['relativePath']=None
        return item,info

    def observation(self,file,info):
        row=self.db.execute("SELECT value_json,schema_version FROM metadata_claims WHERE field='technical' AND source='parser' AND evidence_file_id=? ORDER BY rowid DESC LIMIT 1",(file['id'],)).fetchone()
        if not row:return dict(observation=None,stale=None),None
        raw=json.loads(row[0]);value=raw.get('value',{})
        if row[1]!='technical-observation.v1' or not isinstance(value,dict):return dict(observation=None,stale=None),None
        stale=info is None or (info.st_size,info.st_mtime_ns)!=(raw.get('inputSize'),raw.get('inputMtimeNs'))
        projected={key:v for key,v in value.items() if key in NUMBERS and (v is None or type(v) in (int,float) and math.isfinite(v))}
        projected.update({key:value[key] for key in ('hasAlphaChannel','hasTransparentPixels','defaultImage') if type(value.get(key)) is bool})
        if value.get('format') in FORMATS:projected['format']=value['format']
        return dict(observation=dict(schema=row[1],source='parser',value=projected,inputFingerprint=raw.get('inputFingerprint')),stale=stale),raw

    def dependencies(self,file,raw):
        value=raw.get('value',{}) if raw else {};items=[]
        for index,reference in enumerate(value.get('dependencies',[])[:128]):
            item=dict(index=index,status='unresolved',fileId=None)
            # Reject URL/absolute/drive/parent/encoded references without probing them.
            if not isinstance(reference,str) or not reference or len(reference)>256 or any(c in reference for c in ':\\%?#') or any(ord(c)<32 for c in reference):
                item['status']='blocked'
            else:
                relative=PurePosixPath(reference)
                if relative.is_absolute() or '..' in relative.parts:item['status']='blocked'
                elif file.get('path'):
                    target=str(Path(file['path']).parent.joinpath(*relative.parts))
                    rows=self.db.execute('''SELECT f.id FROM asset_files f JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id
                        WHERE f.absolute_path=? AND l.enabled=1 ORDER BY f.id LIMIT 2''',(target,)).fetchall()
                    if len(rows)==1:
                        dependency,_=self.file(rows[0][0]);item.update(fileId=dependency['id'],status=dependency['availability'])
                        if dependency.get('path'):item.update(path=dependency['path'],relativePath=dependency['relativePath'])
            items.append(item)
        # Module names/Unity GUIDs are declarations, not proven catalog file IDs.
        references=value.get('references',[])
        return dict(items=items,unresolvedDeclarationCount=len(references) if isinstance(references,list) else 0,resolution='registered-files-only')

    def get(self,asset,cursor=None):
        if cursor is not None and not valid_id(cursor):raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute("SELECT file_id,role FROM asset_file_members WHERE asset_id=? AND role!='evidence' ORDER BY file_id,role",(asset,)).fetchall()
        roles={}
        for file,role in rows:roles.setdefault(file,[]).append(role)
        if len(roles)>20:raise LibraryError('MCP_SEARCH_LIMIT')
        files=[];fresh={}
        for identifier,values in roles.items():
            file,info=self.file(identifier);file['roles']=values
            # Disabled roots keep only reference IDs and an unavailable status.
            enabled=self.db.execute('SELECT l.enabled FROM asset_files f JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id WHERE f.id=?',(identifier,)).fetchone()
            technical,raw=self.observation(file,info) if enabled and enabled[0] else (dict(observation=None,stale=None),None)
            file['technical']=technical;file['dependencies']=self.dependencies(file,raw)
            fresh[identifier]=(raw.get('inputFingerprint') if raw else None,True if file['availability']!='present' else technical['stale'])
            files.append(file)
        selected=self.db.execute("SELECT value_json FROM metadata_decisions WHERE asset_id=? AND field='composition'",(asset,)).fetchone()
        decision=json.loads(selected[0]) if selected else None
        selected=decision.get('components',[]) if isinstance(decision,dict) else []
        component_rows=self.db.execute('''SELECT c.id,c.file_id,c.kind,c.locator_json,c.input_fingerprint FROM asset_components c
            WHERE c.file_id IN (SELECT m.file_id FROM asset_file_members m JOIN asset_files f ON f.id=m.file_id
                JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id
                WHERE m.asset_id=? AND m.role!='evidence' AND l.enabled=1) AND c.id>? ORDER BY c.id LIMIT 51''',(asset,cursor or '')).fetchall()
        components=[dict(id=r[0],fileId=r[1],kind=r[2],locator=json.loads(r[3]),selected=r[0] in selected,
            stale=True if fresh.get(r[1],(None,None))[1] is True else None if fresh.get(r[1],(None,None))[0] is None else r[4]!=fresh[r[1]][0]) for r in component_rows[:50]]
        return dict(assetId=asset,files=files,components=components,next_component_cursor=component_rows[49][0] if len(component_rows)>50 else None,
            availability='available' if files and all(f['availability']=='present' for f in files) else 'partial' if any(f['availability']=='present' for f in files) else 'unavailable' if any(f['availability']=='unavailable' for f in files) else 'missing',
            modelCalled=False,evidenceExcluded=True,contentRead=False)
