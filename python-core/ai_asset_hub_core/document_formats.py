"""Bounded declarative inspection. No code execution, archive extraction or imports."""
import ast
import csv
import io
import json
import re
import struct
import zipfile
from pathlib import PurePosixPath
from .libraries import LibraryError

TEXT_EXTENSIONS=frozenset(('.txt','.md','.json','.csv','.py','.cs','.js','.ts','.shader','.hlsl','.glsl','.unity','.prefab','.vfx','.mat','.yaml','.yml'))


def text_observation(extension,raw):
    if len(raw)>32768:raise LibraryError('INPUT_TOO_LARGE')
    text=raw.decode('utf-8-sig')
    if any(ord(c)<32 and c not in '\n\r\t' for c in text):raise ValueError()
    value={'format':extension[1:].upper(),'encoding':'UTF-8','lineCount':len(text.splitlines()),
        'execution':'never','references':[],'engineCompatibility':None}
    if extension=='.json':
        from .transport import _unique_object
        document=json.loads(text,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        value.update(rootType=type(document).__name__,entryCount=len(document) if isinstance(document,(dict,list)) else None,
            keys=list(document)[:64] if isinstance(document,dict) else [])
    elif extension=='.csv':
        rows=list(csv.reader(io.StringIO(text),strict=True))
        value.update(rowCount=len(rows),columnCount=len(rows[0]) if rows else 0)
    elif extension=='.py':
        tree=ast.parse(text)
        value['declarations']=[node.name[:128] for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))][:64]
        value['references']=[node.module[:128] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module][:64]
        value['references'] += [name.name[:128] for node in ast.walk(tree) if isinstance(node,ast.Import) for name in node.names][:64]
    elif extension in ('.unity','.prefab','.vfx','.mat'):
        if not text.startswith('%YAML') or not re.search(r'^--- !u!\d+',text,re.M):raise ValueError()
        value['declarationCount']=len(re.findall(r'^--- !u!\d+',text,re.M))
        value['references']=sorted(set(re.findall(r'\bguid:\s*([0-9a-fA-F]{32})\b',text)))[:128]
        value['referenceResolution']='not-opened';value['runtimeBehavior']='unknown'
    else:
        value['declarations']=re.findall(r'\b(?:class|interface|function|struct|enum)\s+([A-Za-z_]\w{0,127})',text)[:64]
    return value,text


def archive(raw):
    end=raw.rfind(b'PK\x05\x06',max(0,len(raw)-65557))
    if end<0 or end+22>len(raw):raise ValueError()
    disk,central_disk,local_count,total=struct.unpack_from('<4H',raw,end+4)
    if disk or central_disk or local_count!=total or total>128:raise LibraryError('INPUT_TOO_LARGE')
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        entries=source.infolist()
        if len(entries)>128:raise LibraryError('INPUT_TOO_LARGE')
        files=[]
        for item in entries:
            name=item.filename.replace('\\','/')
            unsafe=PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name or bool((item.external_attr>>16)&0o170000==0o120000)
            files.append({'name':name[:256],'compressedBytes':item.compress_size,'declaredBytes':item.file_size,
                'unsafePath':unsafe,'encrypted':bool(item.flag_bits&1)})
    return {'format':'ZIP','entries':files,'entryCount':len(files),'contentValidation':'not-decompressed',
        'extraction':'never','installation':'never','engineCompatibility':None}


def font(raw):
    if len(raw)<12 or raw[:4] not in (b'\x00\x01\x00\x00',b'OTTO'):raise ValueError()
    count=struct.unpack_from('>H',raw,4)[0]
    if not 1<=count<=128 or 12+16*count>len(raw):raise ValueError()
    tables={}
    for index in range(count):
        tag,checksum,offset,length=struct.unpack_from('>4sIII',raw,12+16*index)
        if tag in tables or offset>len(raw) or length>len(raw)-offset:raise ValueError()
        tables[tag]=(offset,length)
    units=glyphs=None
    if b'head' in tables:
        offset,length=tables[b'head']
        if length<54 or struct.unpack_from('>I',raw,offset+12)[0]!=0x5F0F3CF5:raise ValueError()
        units=struct.unpack_from('>H',raw,offset+18)[0]
        if not 16<=units<=16384:raise ValueError()
    if b'maxp' in tables:
        offset,length=tables[b'maxp']
        if length<6:raise ValueError()
        glyphs=struct.unpack_from('>H',raw,offset+4)[0]
    return {'format':'OTF' if raw[:4]==b'OTTO' else 'TTF','tableCount':count,
        'tableTags':[tag.decode('ascii',errors='replace') for tag in tables],
        'unitsPerEm':units,'declaredGlyphCount':glyphs,'glyphRendering':'unsupported','license':None}


def mp4(raw):
    duration=None;tracks=0;file_type=False;boxes=0
    def inspect(start,end,depth):
        nonlocal duration,tracks,file_type,boxes
        offset=start
        while offset<end:
            boxes+=1
            if boxes>4096 or depth>4 or end-offset<8:raise ValueError()
            size,kind=struct.unpack_from('>I4s',raw,offset);header=8
            if size==1:
                if end-offset<16:raise ValueError()
                size=struct.unpack_from('>Q',raw,offset+8)[0];header=16
            if size==0:size=end-offset
            if size<header or size>end-offset:raise ValueError()
            content=offset+header
            if kind==b'ftyp':file_type=True
            elif kind==b'trak':tracks+=1
            elif kind==b'mvhd':
                if offset+size-content<20:raise ValueError()
                version=raw[content]
                if version==0:rate,ticks=struct.unpack_from('>II',raw,content+12)
                elif version==1:
                    if offset+size-content<32:raise ValueError()
                    rate,ticks=struct.unpack_from('>IQ',raw,content+20)
                else:raise ValueError()
                if not rate:raise ValueError()
                duration=None if ticks in (0xFFFFFFFF,0xFFFFFFFFFFFFFFFF) else ticks/rate
            if kind==b'moov':inspect(content,offset+size,depth+1)
            offset+=size
    inspect(0,len(raw),0)
    if not file_type or duration is None:raise ValueError()
    return {'format':'MP4','declaredDurationSeconds':duration,'declaredTrackCount':tracks,
        'durationEvidence':'mvhd-header','frameDecode':'unsupported','fps':None,'videoInference':'unsupported'}


def inspect_format(extension,raw):
    try:
        if extension in TEXT_EXTENSIONS:return text_observation(extension,raw)[0]
        if extension=='.zip':return archive(raw)
        if extension in ('.ttf','.otf'):return font(raw)
        if extension in ('.mp4','.mov'):return mp4(raw)
        raise LibraryError('UNSUPPORTED_FORMAT')
    except LibraryError:raise
    except (ValueError,TypeError,KeyError,IndexError,UnicodeError,struct.error,zipfile.BadZipFile,csv.Error,SyntaxError,RecursionError):
        raise LibraryError('UNSUPPORTED_FORMAT') from None
