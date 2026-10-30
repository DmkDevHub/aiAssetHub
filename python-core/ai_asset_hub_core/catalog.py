"""Bounded offline catalog navigation and editing contracts. No model/file actions."""
import json
from .metadata_values import MetadataError
from .taxonomy import TaxonomyError
from .collections import Collections
from .libraries import LibraryError, valid_id


class Catalog(Collections):
    def options(self, params):
        if not isinstance(params, dict) or set(params)-{'kind','after_id','version','include_inactive'} or {'kind','after_id'}-set(params): raise LibraryError('INVALID_PARAMS')
        kind, cursor = params['kind'], params['after_id']
        if type(params.get('include_inactive',False)) is not bool:raise LibraryError('INVALID_PARAMS')
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 128): raise LibraryError('INVALID_PARAMS')
        queries = {
            'formats': "SELECT DISTINCT coalesce(nullif(upper(ltrim(extension,'.')),''),'FILE'),coalesce(nullif(upper(ltrim(extension,'.')),''),'FILE'),NULL FROM asset_files WHERE coalesce(nullif(upper(ltrim(extension,'.')),''),'FILE')>? ORDER BY 1 LIMIT 21",
            'license_labels': "SELECT DISTINCT json_extract(value_json,'$.label'),json_extract(value_json,'$.label'),NULL FROM provenance_licenses WHERE enabled=1 AND json_extract(value_json,'$.label')>? ORDER BY 1 LIMIT 21",
            'groups': 'SELECT id,name,parent_id FROM asset_groups WHERE id>? ORDER BY id LIMIT 21',
            'packages': 'SELECT id,name,NULL FROM asset_packages WHERE enabled=1 AND id>? ORDER BY id LIMIT 21',
            'creators': 'SELECT id,name,NULL FROM creators WHERE enabled=1 AND deleted=0 AND id>? ORDER BY id LIMIT 21',
            'tags': 'SELECT id,label,NULL,enabled FROM tags WHERE id>? ORDER BY id LIMIT 21',
            'types': "SELECT code,ko,parent_code FROM classification_terms WHERE version=(SELECT version FROM classification_dictionaries WHERE kind='type' ORDER BY rowid DESC LIMIT 1) AND active=1 AND code>? ORDER BY code LIMIT 21",
        }
        if kind=='tags' and not params.get('include_inactive'):queries['tags']='SELECT id,label,NULL,enabled FROM tags WHERE enabled=1 AND id>? ORDER BY id LIMIT 21'
        if kind in ('types', 'facets'):
            dictionary = 'type' if kind == 'types' else 'facet'
            version = params.get('version')
            if version is None:
                version = self.db.execute('SELECT version FROM classification_dictionaries WHERE kind=? ORDER BY rowid DESC LIMIT 1', (dictionary,)).fetchone()[0]
            if not isinstance(version, str) or not self.db.execute('SELECT 1 FROM classification_dictionaries WHERE version=? AND kind=?', (version, dictionary)).fetchone(): raise LibraryError('INVALID_PARAMS')
            rows = self.db.execute('SELECT code,ko,parent_code,axis,active FROM classification_terms WHERE version=? AND (active=1 OR ?) AND code>? ORDER BY code LIMIT 21', (version, params.get('include_inactive',False), cursor or '')).fetchall()
            return {'version': version, 'items': [dict(id=r[0], name=r[1][:64], parentId=r[2], axis=r[3], enabled=bool(r[4])) for r in rows[:20]], 'next_cursor': rows[19][0] if len(rows)>20 else None}
        if not isinstance(kind, str) or kind not in queries: raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute(queries[kind], (cursor or '',)).fetchall()
        return {'items': [dict(id=r[0], name=r[1][:64], parentId=r[2],enabled=bool(r[3]) if len(r)>3 else True) for r in rows[:20]], 'next_cursor': rows[19][0] if len(rows) > 20 else None}

    def scope(self, params):
        self.keys(params, 'kind id after_id')
        kind, identifier, cursor = params['kind'], params['id'], params['after_id']
        if cursor is not None and not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
        if kind == 'groups':
            self.group(identifier)
            condition = 'EXISTS(SELECT 1 FROM asset_group_members m WHERE m.asset_id=a.id AND m.group_id=?)'; args = [identifier]
        elif kind == 'packages':
            if not valid_id(identifier) or not self.db.execute('SELECT 1 FROM asset_packages WHERE id=? AND enabled=1', (identifier,)).fetchone(): raise LibraryError('INVALID_PARAMS')
            condition = 'EXISTS(SELECT 1 FROM asset_package_members m WHERE m.asset_id=a.id AND m.package_id=?)'; args = [identifier]
        elif kind == 'types':
            if not isinstance(identifier, str) or not self.db.execute("SELECT 1 FROM classification_terms WHERE axis='type' AND code=?", (identifier,)).fetchone(): raise LibraryError('INVALID_PARAMS')
            condition = "(EXISTS(SELECT 1 FROM asset_classification_selections s WHERE s.asset_id=a.id AND (s.primary_code=? OR s.primary_code LIKE ?)) OR EXISTS(SELECT 1 FROM asset_classification_links m WHERE m.asset_id=a.id AND m.axis='type' AND (m.code=? OR m.code LIKE ?)))"
            args = [identifier, identifier + '.%', identifier, identifier + '.%']
        else: raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute('SELECT a.id FROM assets a JOIN library_roots l ON l.id=a.library_root_id '
                               f'WHERE l.enabled=1 AND a.id>? AND {condition} ORDER BY a.id LIMIT 201', (cursor or '', *args)).fetchall()
        ids = [r[0] for r in rows[:200]]
        return {'ids': ids, 'next_cursor': ids[-1] if len(rows) > 200 else None}

    def classification(self, params):
        self.keys(params, 'asset_id'); self.require_asset(params['asset_id']); state = self.metadata.effective(params['asset_id'], 'classification')
        value = state['value'] if isinstance(state.get('value'), dict) else None
        versions = {kind: self.db.execute('SELECT version FROM classification_dictionaries WHERE kind=? ORDER BY rowid DESC LIMIT 1', (kind,)).fetchone()[0] for kind in ('type','facet')}
        return dict(value={'primary': value['type']['primary'] if value else None, 'navigation': value['type']['navigation'] if value else [],
                           'facets': value['facets']['values'] if value else {}, 'type_version': value['type']['version'] if value else versions['type'],
                           'facet_version': value['facets']['version'] if value else versions['facet']}, revision=state['revision'], source=state['source'], status=state['status'])

    def save_classification(self, params):
        self.keys(params, 'asset_id value expected_revision confirmed'); value=params['value']
        self.keys(value, 'primary navigation facets type_version facet_version')
        try:
            self.metadata.classify(params['asset_id'], **value, expected_revision=params['expected_revision'], confirmed=params['confirmed'])
        except (MetadataError, TaxonomyError) as error:
            raise LibraryError('METADATA_CONFLICT' if str(error)=='METADATA_CONFLICT' else 'INVALID_PARAMS') from None
        return self.classification({'asset_id':params['asset_id']})

    def evidence_candidates(self, params):
        from .provenance import Provenance
        self.keys(params, 'subject after_id'); kind, owner=Provenance(self.database).subject(params['subject'])
        cursor=params['after_id']
        if cursor is not None and not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
        scope='m.asset_id=?' if kind=='asset' else 'EXISTS(SELECT 1 FROM asset_package_members p WHERE p.package_id=? AND p.asset_id=m.asset_id)'
        rows=self.db.execute('SELECT DISTINCT f.id,f.relative_path,f.exists_flag FROM asset_file_members m JOIN asset_files f ON f.id=m.file_id '
            'JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id '
            f'WHERE l.enabled=1 AND {scope} AND f.id>? ORDER BY f.id LIMIT 21',(owner,cursor or '')).fetchall()
        return {'items':[dict(id=r[0],name=r[1][-64:],available=bool(r[2])) for r in rows[:20]],'next_cursor':rows[19][0] if len(rows)>20 else None}
