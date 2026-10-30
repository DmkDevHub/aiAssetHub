"""User-declared license conditions and explicitly selected registered evidence. No legal/AI inference."""
import unicodedata
from .source_records import OwnedRecords, Sources
from .collections import Collections
from .libraries import LibraryError, valid_id
from .mcp_queries import McpQueries


class Licenses(OwnedRecords):
    table = 'provenance_licenses'
    field = 'license'
    confirmation = True

    @staticmethod
    def prose(value, limit):
        if not isinstance(value, str) or len(value) > limit or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
            raise LibraryError('INVALID_PARAMS')
        text = unicodedata.normalize('NFKC', value).strip()
        if len(text) > limit: raise LibraryError('INVALID_PARAMS')
        return text

    def value(self, value):
        Collections.keys(value, 'label terms attribution reviewStatus scope note source_id')
        if value['reviewStatus'] not in ('unknown', 'needs_review', 'user_reviewed') or value['source_id'] is not None and not valid_id(value['source_id']):
            raise LibraryError('INVALID_PARAMS')
        return {**{key: self.prose(value[key], limit) if key in ('terms', 'attribution', 'note') else Collections.text(value[key], limit) for key, limit in
                   [('label', 128), ('terms', 1024), ('attribution', 256), ('scope', 128), ('note', 256)]},
                'reviewStatus': value['reviewStatus'], 'source_id': value['source_id']}

    def validate_owner(self, value, subject, before=None):
        if value['source_id'] is None: return
        source = Sources(self.database).record(value['source_id'])
        if source['subject'] != subject or not source['enabled'] and not (before and before['value']['source_id'] == source['id']):
            raise LibraryError('INVALID_PARAMS')

    @staticmethod
    def public_value(value):
        return {key: value[key] for key in ('label', 'reviewStatus', 'scope')}

    def record(self, identifier):
        result = super().record(identifier)
        result['evidence'] = [dict(file_id=r[0], label=r[1]) for r in self.db.execute('SELECT file_id,label FROM license_evidence WHERE license_id=? ORDER BY file_id', (identifier,))]
        return result

    def evidence_file(self, subject, file_id):
        kind, owner = self.subject(subject, active=False)
        if not valid_id(file_id): raise LibraryError('INVALID_PARAMS')
        scope = 'm.asset_id=?' if kind == 'asset' else 'EXISTS(SELECT 1 FROM asset_package_members p WHERE p.package_id=? AND p.asset_id=m.asset_id)'
        row = self.db.execute('SELECT DISTINCT f.absolute_path,l.absolute_path,f.relative_path,l.enabled FROM asset_files f '
            'JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id JOIN asset_file_members m ON m.file_id=f.id '
            f'WHERE f.id=? AND {scope}', (file_id, owner)).fetchone()
        if row is None or not row[3]: return False
        path = McpQueries.safe_path(row[0], row[1], row[2])
        try: return path is not None and path.is_file()
        except OSError: return False

    def project(self, record, private=False):
        result = super().project(record, private)
        result.pop('evidence', None)
        result.update(permission='unknown', declaredBy='user', evidenceCount=len(record.get('evidence', [])))
        if private:
            result['evidence'] = [{**item, 'availability': 'present' if self.evidence_file(record['subject'], item['file_id']) else 'unavailable'} for item in record['evidence']]
        return result

    def save_evidence(self, params):
        Collections.keys(params, 'record_id files expected_revision confirmed')
        files = params['files']
        if params['confirmed'] is not True or not isinstance(files, list) or len(files) > 8: raise LibraryError('INVALID_PARAMS')
        normalized = []
        for item in files:
            Collections.keys(item, 'file_id label')
            if not valid_id(item['file_id']): raise LibraryError('INVALID_PARAMS')
            normalized.append(dict(file_id=item['file_id'], label=Collections.text(item['label'], 64)))
        if len({i['file_id'] for i in normalized}) != len(normalized): raise LibraryError('INVALID_PARAMS')
        def operation():
            before = self.record(params['record_id']); self.subject(before['subject'])
            if not before['enabled']: raise LibraryError('INVALID_PARAMS')
            Collections.revision(params['expected_revision'], before['revision'])
            if any(not self.evidence_file(before['subject'], item['file_id']) for item in normalized): raise LibraryError('INVALID_PARAMS')
            self.db.execute('DELETE FROM license_evidence WHERE license_id=?', (before['id'],))
            self.db.executemany('INSERT INTO license_evidence VALUES (?,?,?)', [(before['id'], i['file_id'], i['label']) for i in normalized])
            self.db.execute('UPDATE provenance_licenses SET revision=revision+1 WHERE id=?', (before['id'],))
            result = self.record(before['id'])
            self.event(before['subject'], before['id'], self.field, result['revision'], 'evidence', before, result)
            return self.project(result)
        return self.write(operation)
