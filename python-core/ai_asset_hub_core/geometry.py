"""Bounded OBJ/glTF structure parsing. Never opens dependencies or executes content."""
import base64
import io
import json
import math
import struct
from .libraries import LibraryError

MAX_VERTICES=100_000
MAX_FACES=100_000


def finite(values):
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e12 for v in values):raise ValueError()
    return values


def obj(raw):
    points=[];faces=[];materials=set();dependencies=set();uv=0
    for line in raw.decode('utf-8-sig').splitlines():
        parts=line.split('#',1)[0].split()
        if not parts:continue
        if parts[0]=='v':
            if len(parts) not in (4,5):raise ValueError()
            point=finite([float(v) for v in parts[1:4]])
            if len(parts)==5 and float(parts[4])!=1:raise ValueError()
            points.append(point)
        elif parts[0]=='vt':uv+=1
        elif parts[0]=='f':
            if not 3<=len(parts)-1<=64:raise ValueError()
            indices=[]
            for value in parts[1:]:
                index=int(value.split('/')[0]);index=index-1 if index>0 else len(points)+index if index<0 else -1
                if not 0<=index<len(points):raise ValueError()
                indices.append(index)
            faces.append(indices)
        elif parts[0]=='usemtl':materials.add(' '.join(parts[1:])[:128])
        elif parts[0]=='mtllib':dependencies.update(parts[1:])
        if len(points)>MAX_VERTICES or len(faces)>MAX_FACES:raise LibraryError('INPUT_TOO_LARGE')
    if not points:raise ValueError()
    return {'format':'OBJ','meshCount':1,'vertexCount':len(points),'polygonCount':len(faces),
        'triangleCount':sum(len(f)-2 for f in faces),'materialNames':sorted(materials)[:128],
        'uvCoordinateCount':uv,'boneCount':None,'units':None,'dependencies':sorted(dependencies)[:128],
        'dependencyResolution':'not-opened','render':'wireframe' if faces else 'unsupported'},points,faces


def gltf_document(raw,extension):
    binary=None
    if extension=='.glb':
        if len(raw)<20:raise ValueError()
        magic,version,length=struct.unpack_from('<4sII',raw)
        if magic!=b'glTF' or version!=2 or length!=len(raw):raise ValueError()
        offset=12;chunks=[]
        while offset<len(raw):
            if offset+8>len(raw):raise ValueError()
            size,kind=struct.unpack_from('<II',raw,offset);offset+=8
            if size%4 or size>len(raw)-offset:raise ValueError()
            chunks.append((kind,raw[offset:offset+size]));offset+=size
        if not chunks or chunks[0][0]!=0x4E4F534A or len(chunks)>2:raise ValueError()
        raw=chunks[0][1]
        if len(chunks)==2:
            if chunks[1][0]!=0x004E4942:raise ValueError()
            binary=chunks[1][1]
    from .transport import _unique_object
    document=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    if not isinstance(document,dict) or document.get('asset',{}).get('version')!='2.0':raise ValueError()
    return document,binary


def gltf(raw,extension):
    doc,binary=gltf_document(raw,extension)
    for key in ('meshes','materials','nodes','skins','accessors','bufferViews','buffers','images','animations'):
        if not isinstance(doc.get(key,[]),list) or len(doc.get(key,[]))>10000:raise LibraryError('INPUT_TOO_LARGE')
    buffers=[];dependencies=[]
    for index,buffer in enumerate(doc.get('buffers',[])):
        size=buffer['byteLength']
        if type(size) is not int or not 0<=size<=20_000_000:raise ValueError()
        uri=buffer.get('uri');data=None
        if uri is None:
            if index!=0 or binary is None:raise ValueError()
            data=binary
        elif not isinstance(uri,str):raise ValueError()
        elif uri.startswith(('data:application/octet-stream;base64,','data:application/gltf-buffer;base64,')):
            data=base64.b64decode(uri.split(',',1)[1],validate=True)
        else:dependencies.append(uri[:256])
        if data is not None and len(data)<size:raise ValueError()
        buffers.append(data[:size] if data is not None else None)
    dependencies.extend(i['uri'][:256] for i in doc.get('images',[]) if isinstance(i.get('uri'),str) and not i['uri'].startswith('data:'))
    decoded_scalars=0
    def accessor(index,expected):
        nonlocal decoded_scalars
        if type(index) is not int or not 0<=index<len(doc.get('accessors',[])):raise ValueError()
        entry=doc['accessors'][index]
        if entry.get('sparse') or entry.get('type')!=expected:raise LibraryError('UNSUPPORTED_FORMAT')
        count=entry['count'];ctype=entry['componentType']
        if type(count) is not int or not 0<=count<=MAX_VERTICES*3:raise LibraryError('INPUT_TOO_LARGE')
        widths={5121:('B',1),5123:('H',2),5125:('I',4),5126:('f',4)}
        if ctype not in widths:raise LibraryError('UNSUPPORTED_FORMAT')
        fmt,width=widths[ctype];components=3 if expected=='VEC3' else 1
        decoded_scalars+=count*components
        if decoded_scalars>1_000_000:raise LibraryError('INPUT_TOO_LARGE')
        if expected=='VEC3' and ctype!=5126:raise ValueError()
        view_index=entry['bufferView']
        if type(view_index) is not int or not 0<=view_index<len(doc.get('bufferViews',[])):raise ValueError()
        view=doc['bufferViews'][view_index];buffer_index=view['buffer']
        if type(buffer_index) is not int or not 0<=buffer_index<len(buffers):raise ValueError()
        data=buffers[buffer_index]
        offset=view.get('byteOffset',0);local=entry.get('byteOffset',0);length=view['byteLength'];stride=view.get('byteStride',width*components)
        if any(type(v) is not int or v<0 for v in (offset,local,length,stride)) or stride<width*components or (count and local+(count-1)*stride+width*components>length):raise ValueError()
        if data is None:return None,count
        if offset+length>len(data):raise ValueError()
        return [finite(list(struct.unpack_from('<'+fmt*components,data,offset+local+i*stride))) for i in range(count)],count
    points=[];faces=[];declared=0;uv=0
    for mesh in doc.get('meshes',[]):
        primitives=mesh.get('primitives',[])
        if not isinstance(primitives,list) or len(primitives)>10000:raise ValueError()
        for primitive in primitives:
            attributes=primitive['attributes'];uv+=sum(k.startswith('TEXCOORD_') for k in attributes)
            values,count=accessor(attributes['POSITION'],'VEC3');declared+=count
            if declared>MAX_VERTICES:raise LibraryError('INPUT_TOO_LARGE')
            if primitive.get('mode',4)!=4:continue
            if 'indices' in primitive:
                indices,_=accessor(primitive['indices'],'SCALAR')
                if indices is not None:indices=[v[0] for v in indices]
            else:indices=list(range(count)) if values is not None else None
            if values is None or indices is None:continue
            if len(indices)%3 or any(type(i) is not int or not 0<=i<count for i in indices):raise ValueError()
            base=len(points);points.extend(values)
            faces.extend([[base+i for i in indices[n:n+3]] for n in range(0,len(indices),3)])
            if len(points)>MAX_VERTICES or len(faces)>MAX_FACES:raise LibraryError('INPUT_TOO_LARGE')
    joints=set()
    for skin in doc.get('skins',[]):
        if not isinstance(skin.get('joints'),list):raise ValueError()
        for node in skin['joints']:
            if type(node) is not int or not 0<=node<len(doc.get('nodes',[])):raise ValueError()
            joints.add(node)
    result={'format':'glTF2','meshCount':len(doc.get('meshes',[])),
        'materialCount':len(doc.get('materials',[])),'boneCount':len(joints),'skinCount':len(doc.get('skins',[])),
        'declaredVertexCount':declared,'decodedVertexCount':len(points),'decodedTriangleCount':len(faces),
        'uvAttributeCount':uv,'units':'meter (glTF convention)','boundsSpace':'mesh-local; node transforms not applied',
        'dependencies':sorted(set(dependencies))[:128],'dependencyResolution':'not-opened',
        'render':'wireframe' if points and faces else 'unsupported'}
    clips=[];children=set()
    for node in doc.get('nodes',[]):
        for child in node.get('children',[]):
            if type(child) is not int or not 0<=child<len(doc.get('nodes',[])):raise ValueError()
            children.add(child)
    if len(doc.get('animations',[]))>32:raise LibraryError('INPUT_TOO_LARGE')
    for index,animation in enumerate(doc.get('animations',[])):
        samplers=animation.get('samplers',[]);channels=animation.get('channels',[])
        if not isinstance(samplers,list) or not isinstance(channels,list) or max(len(samplers),len(channels))>128:raise LibraryError('INPUT_TOO_LARGE')
        starts=[];ends=[];known=True;root=[];keyframes=0
        for sampler in samplers:
            times,count=accessor(sampler['input'],'SCALAR');keyframes+=count
            if times is None:known=False;continue
            times=[t[0] for t in times]
            if not times or any(t<0 for t in times) or any(a>=b for a,b in zip(times,times[1:])):raise ValueError()
            starts.append(times[0]);ends.append(times[-1])
        for channel in channels:
            target=channel['target'];node=target.get('node');sampler_index=channel['sampler']
            if type(sampler_index) is not int or not 0<=sampler_index<len(samplers):raise ValueError()
            if type(node) is not int or not 0<=node<len(doc.get('nodes',[])):raise ValueError()
            if target['path']=='translation' and node not in children:
                sampler=samplers[sampler_index]
                if sampler.get('interpolation','LINEAR') not in ('LINEAR','STEP'):continue
                values,count=accessor(sampler['output'],'VEC3')
                times,time_count=accessor(sampler['input'],'SCALAR')
                if count!=time_count:raise ValueError()
                if values:root.append({'node':node,'localTranslationDelta':[values[-1][i]-values[0][i] for i in range(3)]})
        name=animation.get('name',f'animation-{index}')
        if not isinstance(name,str):raise ValueError()
        clips.append({'index':index,'name':name[:128],'channels':len(channels),'sampleKeyframes':keyframes,
            'durationSeconds':max(ends)-min(starts) if known and starts else None,
            'rootTranslation':root[:16],'rootMotionEvidence':'decoded-local-track' if root else 'unknown',
            'loop':None,'fps':None,'engineCompatibility':None})
    result['clips']=clips;result['animationCount']=len(clips)
    return result,points,faces


def geometry(extension,raw):
    try:
        result,points,faces=obj(raw) if extension=='.obj' else gltf(raw,extension)
        if points:result['decodedBounds']={'min':[min(p[i] for p in points) for i in range(3)],'max':[max(p[i] for p in points) for i in range(3)]}
        result['surfacePreview']='unsupported';result['engineCompatibility']=None
        return result,points,faces
    except LibraryError:raise
    except (ValueError,TypeError,KeyError,IndexError,UnicodeError,struct.error,RecursionError):
        raise LibraryError('UNSUPPORTED_FORMAT') from None


def wireframe(points,faces):
    from PIL import Image,ImageDraw
    if not points or not faces:raise LibraryError('UNSUPPORTED_FORMAT')
    # Orthographic X/Y projection: no textures, materials, scene transforms or scripts.
    low=[min(p[i] for p in points) for i in (0,1)];high=[max(p[i] for p in points) for i in (0,1)]
    scale=460/max(high[0]-low[0],high[1]-low[1],1e-12)
    projected=[(26+(p[0]-low[0])*scale,486-(p[1]-low[1])*scale) for p in points]
    image=Image.new('RGB',(512,512),'white');draw=ImageDraw.Draw(image)
    for face in faces[:10000]:draw.line([projected[i] for i in face]+[projected[face[0]]],fill='black',width=1)
    output=io.BytesIO();image.save(output,format='JPEG',quality=80)
    return base64.b64encode(output.getvalue()).decode('ascii')
