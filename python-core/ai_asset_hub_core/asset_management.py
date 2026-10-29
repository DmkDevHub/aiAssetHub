"""Explicit user metadata commands; no source writes or analysis scheduling."""
from datetime import date
import re
import unicodedata
from .annotations import AnnotationService
from .libraries import LibraryError
from .metadata_values import MetadataError


class AssetManagement(AnnotationService):
    @staticmethod
    def text(value, limit):
        if not isinstance(value, str) or len(value) > limit or any(
                unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
            raise LibraryError('INVALID_PARAMS')
        return value.strip()

    def read(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        state = self.metadata.effective(params['asset_id'], 'management')
        default = dict(favorite=False, rating=None, status='unreviewed', notes='', assetVersion='',
                       createdDate='', modifiedDate='')
        return {'value': state['value'] if state['source'] == 'user' else default, 'revision': state['revision']}

    def save_management(self, params):
        self.validate_request(params)
        value = params['value']
        if not isinstance(value, dict) or set(value) != {'favorite', 'rating', 'status', 'notes', 'assetVersion', 'createdDate', 'modifiedDate'}:
            raise LibraryError('INVALID_PARAMS')
        if type(value['favorite']) is not bool or (value['rating'] is not None and (type(value['rating']) is not int or not 1 <= value['rating'] <= 5)):
            raise LibraryError('INVALID_PARAMS')
        if value['status'] not in ('unreviewed', 'reviewing', 'approved', 'archived'):
            raise LibraryError('INVALID_PARAMS')
        value = {**value, 'notes': self.text(value['notes'], 1024), 'assetVersion': self.text(value['assetVersion'], 64)}
        for field in ('createdDate', 'modifiedDate'):
            day = value[field]
            if not isinstance(day, str): raise LibraryError('INVALID_PARAMS')
            if day:
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day): raise ValueError()
                    date.fromisoformat(day)
                except ValueError: raise LibraryError('INVALID_PARAMS') from None
        if value['createdDate'] and value['modifiedDate'] and value['createdDate'] > value['modifiedDate']:
            raise LibraryError('INVALID_PARAMS')
        return self.commit(params, 'management', value, self.read)

    def validate_request(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'value', 'expected_revision'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])

    def commit(self, params, field, value, reader, projection=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.metadata._decide(params['asset_id'], field, 'set', params['expected_revision'], True, value, None)
            if projection: projection()
            result = reader({'asset_id': params['asset_id']})
            self.db.execute('COMMIT')
            return result
        except MetadataError as error:
            self.db.execute('ROLLBACK')
            raise LibraryError('METADATA_CONFLICT' if str(error) == 'METADATA_CONFLICT' else 'INVALID_PARAMS') from None
        except Exception:
            self.db.execute('ROLLBACK')
            raise
