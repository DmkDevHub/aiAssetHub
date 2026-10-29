"""User metadata only: never changes source files or analysis history."""
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id
from .metadata_store import MetadataStore
from .metadata_values import MetadataError


class AnnotationService:
    def __init__(self, database):
        self.db = database.connection
        self.metadata = MetadataStore(database)

    def require_asset(self, identifier):
        if not valid_id(identifier) or not self.db.execute('''SELECT 1 FROM assets a
            JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''', (identifier,)).fetchone():
            raise LibraryError('INVALID_PARAMS')

    def get(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        tags = [row[0] for row in self.db.execute('''SELECT t.label FROM tags t JOIN asset_tags at ON at.tag_id=t.id
            WHERE at.asset_id=? AND at.source='user' ORDER BY t.normalized_label''', (params['asset_id'],))]
        row = self.db.execute('SELECT title_override,description_override FROM asset_user_annotations WHERE asset_id=?', (params['asset_id'],)).fetchone()
        state = self.metadata.effective(params['asset_id'], 'basic_text')
        value = state['value'] if state['source'] == 'user' else None
        original = self.db.execute('SELECT display_name FROM assets WHERE id=?', (params['asset_id'],)).fetchone()[0]
        return {'tags': tags, 'title': row[0] or '' if row else '', 'description': row[1] or '' if row else '',
                'aliases': value.get('aliases', []) if isinstance(value, dict) else [],
                'originalName': original, 'revision': state['revision'],
                'tagsRevision': self.metadata.effective(params['asset_id'], 'user_tags')['revision']}

    def save(self, params):
        legacy = {'asset_id', 'title', 'description'}
        if not isinstance(params, dict) or set(params) not in (legacy, legacy | {'aliases', 'expected_revision'}):
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        for key, limit in (('title',128), ('description',1024)):
            value = params[key]
            if not isinstance(value,str) or len(value) > limit or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
                raise LibraryError('INVALID_PARAMS')
        aliases = self.aliases(params['aliases']) if 'aliases' in params else None
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current = self.get({'asset_id': params['asset_id']})
            value = {'title': params['title'].strip(), 'description': params['description'].strip(),
                     'aliases': current['aliases'] if aliases is None else aliases}
            self.metadata._decide(params['asset_id'], 'basic_text', 'set',
                                  params.get('expected_revision', current['revision']), True, value, None)
            self.db.execute('''INSERT INTO asset_user_annotations(asset_id,title_override,description_override,updated_at)
            VALUES (?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id) DO UPDATE SET
            title_override=excluded.title_override,description_override=excluded.description_override,updated_at=excluded.updated_at''',
                (params['asset_id'],value['title'] or None,value['description'] or None))
            result = self.get({'asset_id': params['asset_id']})
            self.db.execute('COMMIT')
        except MetadataError as error:
            self.db.execute('ROLLBACK')
            raise LibraryError('METADATA_CONFLICT' if str(error) == 'METADATA_CONFLICT' else 'INVALID_PARAMS') from None
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return result

    @staticmethod
    def aliases(value):
        if not isinstance(value, list) or len(value) > 16:
            raise LibraryError('INVALID_PARAMS')
        result = {}
        for alias in value:
            if not isinstance(alias, str): raise LibraryError('INVALID_PARAMS')
            alias = unicodedata.normalize('NFKC', alias).strip()
            if not alias or len(alias) > 64 or any(unicodedata.category(c).startswith('C') for c in alias):
                raise LibraryError('INVALID_PARAMS')
            result.setdefault(alias.casefold(), alias)
        if sum(map(len, result.values())) > 512: raise LibraryError('INVALID_PARAMS')
        return list(result.values())

    @staticmethod
    def labels(value):
        if not isinstance(value, list) or len(value) > 32:
            raise LibraryError('INVALID_PARAMS')
        result = {}
        for label in value:
            if not isinstance(label, str): raise LibraryError('INVALID_PARAMS')
            label = unicodedata.normalize('NFKC', label).strip()
            if not label or len(label) > 64 or any(unicodedata.category(c).startswith('C') for c in label):
                raise LibraryError('INVALID_PARAMS')
            result[label.casefold()] = label
        return result

    def tags(self, params):
        keys = {'asset_id', 'add', 'remove'}
        if not isinstance(params, dict) or set(params) not in (keys, keys | {'expected_revision'}):
            raise LibraryError('INVALID_PARAMS')
        if 'expected_revision' in params and (type(params['expected_revision']) is not int or params['expected_revision'] < 0):
            raise LibraryError('INVALID_PARAMS')
        self.batch({'asset_ids':[params['asset_id']], 'add':params['add'], 'remove':params['remove']},
                   expected=params.get('expected_revision') if 'expected_revision' in params else None)
        return self.get({'asset_id':params['asset_id']})

    def batch(self, params, expected=None):
        if not isinstance(params, dict) or set(params) != {'asset_ids', 'add', 'remove'}:
            raise LibraryError('INVALID_PARAMS')
        identifiers = params['asset_ids']
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100 or not all(isinstance(i,str) for i in identifiers) or len(set(identifiers)) != len(identifiers):
            raise LibraryError('INVALID_PARAMS')
        add, remove = self.labels(params['add']), self.labels(params['remove'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for identifier in identifiers:
                self.require_asset(identifier)
                for normalized in remove:
                    self.db.execute("DELETE FROM asset_tags WHERE asset_id=? AND source='user' AND tag_id IN (SELECT id FROM tags WHERE normalized_label=?)", (identifier, normalized))
                for normalized, label in add.items():
                    self.db.execute('INSERT OR IGNORE INTO tags(id,label,normalized_label) VALUES (?,?,?)', (str(uuid4()), label, normalized))
                    self.db.execute("INSERT OR IGNORE INTO asset_tags(asset_id,tag_id,source) SELECT ?,id,'user' FROM tags WHERE normalized_label=?", (identifier, normalized))
                labels = self.get({'asset_id':identifier})['tags']
                if len(labels) > 32 or sum(map(len,labels)) > 512:
                    raise LibraryError('INVALID_PARAMS')
                revision = self.metadata.effective(identifier, 'user_tags')['revision']
                self.metadata._decide(identifier, 'user_tags', 'set', revision if expected is None else expected, True, labels, None)
            self.db.execute('COMMIT')
        except MetadataError as error:
            self.db.execute('ROLLBACK')
            raise LibraryError('METADATA_CONFLICT' if str(error) == 'METADATA_CONFLICT' else 'INVALID_PARAMS') from None
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return {'updated':len(identifiers)}
