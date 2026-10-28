"""User metadata only: never changes source files or analysis history."""
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id


class AnnotationService:
    def __init__(self, database):
        self.db = database.connection

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
        return {'tags': tags}

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
        if not isinstance(params, dict) or set(params) != {'asset_id', 'add', 'remove'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        add, remove = self.labels(params['add']), self.labels(params['remove'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for normalized in remove:
                self.db.execute("DELETE FROM asset_tags WHERE asset_id=? AND source='user' AND tag_id IN (SELECT id FROM tags WHERE normalized_label=?)", (params['asset_id'], normalized))
            for normalized, label in add.items():
                self.db.execute('INSERT OR IGNORE INTO tags(id,label,normalized_label) VALUES (?,?,?)', (str(uuid4()), label, normalized))
                self.db.execute("INSERT OR IGNORE INTO asset_tags(asset_id,tag_id,source) SELECT ?,id,'user' FROM tags WHERE normalized_label=?", (params['asset_id'], normalized))
            if self.db.execute("SELECT count(*) FROM asset_tags WHERE asset_id=? AND source='user'", (params['asset_id'],)).fetchone()[0] > 32:
                raise LibraryError('INVALID_PARAMS')
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return self.get({'asset_id': params['asset_id']})
