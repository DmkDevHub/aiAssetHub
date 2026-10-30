"""Validate bounded AI suggestions independently from measured parser observations."""
from .libraries import LibraryError
from .taxonomy import default_taxonomy, TaxonomyError
from .classification_axes import default_facets

VERSION = 'asset-description.v3'


def suggestions(value):
    if not isinstance(value, dict) or set(value)-{'primary', 'roles', 'styles', 'colors', 'material'}:
        raise LibraryError('INVALID_MODEL_OUTPUT')
    result = {}
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
