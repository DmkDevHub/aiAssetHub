"""Explicit bounded parser observations. Never invokes inference or schedules jobs."""
import hashlib
import io
import wave
from .analysis_input import read_source
from .annotations import AnnotationService
from .libraries import LibraryError
from .metadata_store import MetadataStore

VERSION = 'technical-observation.v1'


def parse_audio(raw):
    try:
        with wave.open(io.BytesIO(raw), 'rb') as source:
            frames, channels, rate, width = source.getnframes(), source.getnchannels(), source.getframerate(), source.getsampwidth()
            if not 1<=channels<=32 or not 1<=rate<=384000 or not 1<=width<=4:
                raise ValueError()
            # A header claiming absent samples is not a successful extraction.
            if len(source.readframes(frames)) != frames*channels*width:
                raise ValueError()
        return {'format':'WAV','codec':'PCM','durationSeconds':frames/rate,
            'channels':channels,'sampleRate':rate,'sampleWidthBytes':width,'sampleFrames':frames,
            'soundClass':None,'mood':None,'transcript':None,'localAudioInference':'unsupported'}
    except (wave.Error, EOFError, ValueError, OverflowError):
        raise LibraryError('UNSUPPORTED_FORMAT') from None


def parse(extension, raw, canceled=None):
    if canceled is not None and canceled.is_set():raise LibraryError('USER_CANCELED')
    if extension=='.wav':result=parse_audio(raw)
    elif extension in ('.obj','.gltf','.glb'):
        from .geometry import geometry
        result=geometry(extension,raw)[0]
    elif extension in ('.gif','.png','.jpg','.jpeg'):
        from .animation import image_animation
        result=image_animation(raw,canceled=canceled)[0]
    else:
        from .document_formats import inspect_format
        result=inspect_format(extension,raw)
    if canceled is not None and canceled.is_set():raise LibraryError('USER_CANCELED')
    return {'schema':VERSION,'source':'parser','value':result,'inputFingerprint':hashlib.sha256(raw).hexdigest(),
        'semanticAnalysis':'unsupported','inferenceCalled':False}


class Technical(AnnotationService):
    def get(self,params):
        if not isinstance(params,dict) or set(params)!={'asset_id'}:raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        state=self.metadata.effective(params['asset_id'],'technical')
        stale=False
        if state['value']:
            from .analysis_input import source_info
            try:
                _,info=source_info(self._database,params['asset_id'])
                stale=(info.st_size,info.st_mtime_ns)!=(state['value'].get('inputSize'),state['value'].get('inputMtimeNs'))
            except LibraryError:stale=True
        return {'observation':state['value'],'stale':stale,'inferenceCalled':False}

    def collect(self,params):
        if not isinstance(params,dict) or set(params)!={'asset_id','confirmed'} or params['confirmed'] is not True:
            raise LibraryError('INVALID_PARAMS')
        asset=params['asset_id'];self.require_asset(asset)
        path,info,raw=read_source(self._database,asset)
        observed=parse(path.suffix.lower(),raw)
        observed.update(inputSize=info.st_size,inputMtimeNs=info.st_mtime_ns)
        from .analysis_input import source_info
        _,after=source_info(self._database,asset)
        if (after.st_size,after.st_mtime_ns)!=(info.st_size,info.st_mtime_ns):raise LibraryError('FILE_CHANGED')
        import json
        if len(json.dumps(observed,ensure_ascii=False).encode('utf-8'))>16000:raise LibraryError('INPUT_TOO_LARGE')
        file=self.db.execute('SELECT id FROM asset_files WHERE asset_id=?',(asset,)).fetchone()[0]
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.metadata.propose(asset,'technical','parser',observed,file,VERSION)
            from .asset_composition import component
            import json
            value=observed['value']
            duration=value.get('durationSeconds')
            duration_ms=round(duration*1000) if type(duration) in (int,float) else None
            self.db.execute("""INSERT INTO asset_observations(asset_file_id,width,height,duration_ms,metadata_json,scanned_at)
                VALUES (?,?,?,?,json_object('technical_schema',?),strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(asset_file_id) DO UPDATE SET width=excluded.width,height=excluded.height,duration_ms=excluded.duration_ms,
                metadata_json=json_set(asset_observations.metadata_json,'$.technical_schema',?),scanned_at=excluded.scanned_at""",
                (file,value.get('width'),value.get('height'),duration_ms,VERSION,VERSION))
            for kind,key in (('mesh','meshCount'),('material','materialCount'),('skeleton','skinCount')):
                for index in range(min(value.get(key,0),128)):
                    item=component(file,observed['inputFingerprint'],kind,[kind,str(index)])
                    self.db.execute('INSERT OR IGNORE INTO asset_components(id,file_id,input_fingerprint,kind,locator_json,identity_version) VALUES (?,?,?,?,?,1)',
                        (item['id'],file,observed['inputFingerprint'],kind,json.dumps(item['locator'])))
            for kind,count in (('animation',value.get('animationCount',0)),('sprite_frame',value.get('frameCount',0))):
                for index in range(min(count,64)):
                    item=component(file,observed['inputFingerprint'],kind,[kind,str(index)])
                    self.db.execute('INSERT OR IGNORE INTO asset_components VALUES (?,?,?,?,?,1)',(item['id'],file,observed['inputFingerprint'],kind,json.dumps(item['locator'])))
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
        return self.get({'asset_id':asset})

    def __init__(self,database):
        super().__init__(database)
        self._database=database
