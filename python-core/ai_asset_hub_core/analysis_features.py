"""Validate bounded AI suggestions independently from measured parser observations."""
from .libraries import LibraryError
from .taxonomy import default_taxonomy, TaxonomyError
from .classification_axes import default_facets

VERSION = 'asset-description.v4'


def audio_suggestions(value):
    if not isinstance(value,dict) or set(value)-{'soundClass','mood','transcript'}:raise LibraryError('INVALID_MODEL_OUTPUT')
    kind=value.get('soundClass')
    if kind not in (None,'music','effect','voice','ambience','unknown'):raise LibraryError('INVALID_MODEL_OUTPUT')
    mood=value.get('mood',[]);transcript=value.get('transcript')
    if not isinstance(mood,list) or len(mood)>8 or any(not isinstance(v,str) or not 1<=len(v)<=64 or any(ord(c)<32 for c in v) for v in mood):raise LibraryError('INVALID_MODEL_OUTPUT')
    if transcript is not None and (not isinstance(transcript,str) or len(transcript)>2048 or any(ord(c)<32 and c not in '\n\t' for c in transcript)):raise LibraryError('INVALID_MODEL_OUTPUT')
    return {'soundClass':kind,'mood':mood,'transcript':transcript}


def suggestions(value):
    if not isinstance(value, dict) or set(value)-{'primary', 'roles', 'styles', 'colors', 'material','action','loopRecommended'}:
        raise LibraryError('INVALID_MODEL_OUTPUT')
    if any(not isinstance(value.get(key,[]),list) or len(value.get(key,[]))>8 for key in ('roles','styles')):raise LibraryError('INVALID_MODEL_OUTPUT')
    result = {}
    if 'action' in value:
        if not isinstance(value['action'],str) or not 1<=len(value['action'])<=128 or any(ord(c)<32 for c in value['action']):raise LibraryError('INVALID_MODEL_OUTPUT')
        result['action']=value['action']
    if 'loopRecommended' in value:
        if type(value['loopRecommended']) is not bool:raise LibraryError('INVALID_MODEL_OUTPUT')
        result['loopRecommended']=value['loopRecommended']
    try:
        if value.get('primary') is not None:
            result['primary'] = default_taxonomy().resolve(value['primary'])
        axes = default_facets().assignment(
            {axis: value.get(key, []) for key, axis in (('roles', 'role'), ('styles', 'style'))},
            version=default_facets().version)['values']
        result.update(roles=axes['role'], styles=axes['style'])
    except (TaxonomyError, TypeError):
        raise LibraryError('INVALID_MODEL_OUTPUT') from None
    for key, limit in (('colors', 8), ('material', 8)):
        items = value.get(key, [])
        if not isinstance(items, list) or len(items)>limit or any(
            not isinstance(v, str) or not 1<=len(v.strip())<=64 or any(ord(c)<32 for c in v) for v in items):
            raise LibraryError('INVALID_MODEL_OUTPUT')
        result[key] = list(dict.fromkeys(v.strip() for v in items))
    return result
