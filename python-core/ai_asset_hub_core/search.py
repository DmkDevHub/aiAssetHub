"""Bounded offline keyword search, with FTS5 and Korean substring fallback."""
import unicodedata
from .libraries import LibraryError, valid_id


class SearchService:
    def __init__(self, database):
        self.db = database.connection

    def search(self, params):
        if not isinstance(params,dict) or set(params)-{'query','after_id'} or not isinstance(params.get('query'),str) or len(params['query'])>256:
            raise LibraryError('INVALID_PARAMS')
        cursor=params.get('after_id')
        if cursor is not None and not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
        terms=unicodedata.normalize('NFKC',params['query']).casefold().split()
        if len(terms)>16: raise LibraryError('INVALID_PARAMS')
        if not terms: return {'ids':[], 'next_cursor':None}
        # Quote every literal token; user input can never supply FTS operators.
        match=' AND '.join('"'+term.replace('"','""')+'"*' for term in terms)
        substring=' AND '.join('instr(d.searchable_text,?)>0' for _ in terms)
        rows=self.db.execute(f'''SELECT d.asset_id FROM search_documents d JOIN assets a ON a.id=d.asset_id
            JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND d.asset_id>?
            AND (d.rowid IN (SELECT rowid FROM asset_fts WHERE asset_fts MATCH ?) OR ({substring}))
            ORDER BY d.asset_id LIMIT 201''',(cursor or '',match,*terms)).fetchall()
        ids=[row[0] for row in rows[:200]]
        return {'ids':ids,'next_cursor':ids[-1] if len(rows)>200 else None}
