"""Explicit dictionary administration, preserving published snapshots and AI history."""
import json
import re
from uuid import uuid4
from .catalog import Catalog
from .taxonomy import Taxonomy, Category, TaxonomyError
from .classification_axes import Facets, Term, AXES
from .libraries import LibraryError, valid_id


class CatalogAdmin(Catalog):
    def admin_log(self, kind, identifier, version, before, after):
        self.db.execute("INSERT INTO catalog_admin_history VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                        (str(uuid4()), kind, identifier, str(version), json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False)))

    def current(self, kind):
        if kind not in ('type','facet'): raise LibraryError('INVALID_PARAMS')
        return self.db.execute('SELECT version FROM classification_dictionaries WHERE kind=? ORDER BY rowid DESC LIMIT 1',(kind,)).fetchone()[0]

    def term_usage(self, kind, code):
        if kind=='type':
            return self.db.execute("SELECT count(*) FROM (SELECT asset_id FROM asset_classification_links WHERE axis='type' AND (code=? OR code LIKE ?) UNION SELECT asset_id FROM asset_classification_selections WHERE primary_code=? OR primary_code LIKE ?)",(code,code+'.%',code,code+'.%')).fetchone()[0]
        return self.db.execute('SELECT count(DISTINCT asset_id) FROM asset_classification_links WHERE code=?',(code,)).fetchone()[0]

    def term_get(self, params):
        self.keys(params,'kind code'); version=self.current(params['kind'])
        row=self.db.execute('SELECT code,axis,ko,en,aliases_json,active,replacement_code FROM classification_terms WHERE version=? AND code=?',(version,params['code'])).fetchone()
        if not row: raise LibraryError('INVALID_PARAMS')
        return dict(base_version=version,usedAssets=self.term_usage(params['kind'],row[0]),value=dict(code=row[0],axis=row[1],ko=row[2],en=row[3],aliases=json.loads(row[4]),active=bool(row[5]),replacement=row[6]))

    def term_save(self, params):
        self.keys(params,'kind base_version value expected_usage confirmed'); value=params['value'];self.keys(value,'code axis ko en aliases active replacement')
        if params['confirmed'] is not True or type(value['active']) is not bool or type(params['expected_usage']) is not int or params['expected_usage']<0: raise LibraryError('INVALID_PARAMS')
        kind=params['kind']; self.current(kind)
        code=self.text(value['code'],64,True); ko=self.text(value['ko'],64,True);en=self.text(value['en'],64,True)
        if not isinstance(value['aliases'],list) or len(value['aliases'])>8:raise LibraryError('INVALID_PARAMS')
        aliases=tuple(self.text(v,64,True) for v in value['aliases'])
        def operation():
            if self.current(kind)!=params['base_version'] or self.term_usage(kind,code)!=params['expected_usage']:raise LibraryError('METADATA_CONFLICT')
            old=self.metadata.dictionary(params['base_version'],kind);version='catalog-'+str(uuid4());before=None
            try:
                if kind=='type':
                    if value['axis']!='type' or value['replacement'] is not None:raise LibraryError('INVALID_PARAMS')
                    nodes=list(old._nodes.values());before=next((n.__dict__ for n in nodes if n.code==code),None)
                    if not value['active'] and any(n.parent==code and n.active for n in nodes):raise LibraryError('INVALID_PARAMS')
                    nodes=[n for n in nodes if n.code!=code]+[Category(code,code.rpartition('.')[0] or None,ko,en,aliases,value['active'])]
                    new=Taxonomy(nodes,version);contract=new.contract()
                    terms=[(version,'type','type',n.code,n.parent,n.ko,n.en,json.dumps(n.aliases,ensure_ascii=False,separators=(',',':')),int(n.active),None) for n in sorted(new._nodes.values(),key=lambda n:n.code)]
                else:
                    if not re.fullmatch(r'(role|style|genre|view|dimension|engine)\.[a-z0-9_]{1,48}',code):raise LibraryError('INVALID_PARAMS')
                    if value['axis'] not in AXES or aliases or value['replacement'] is not None and not isinstance(value['replacement'],str):raise LibraryError('INVALID_PARAMS')
                    if not value['active'] and params['expected_usage'] and not value['replacement']:raise LibraryError('INVALID_PARAMS')
                    nodes=list(old.terms);before=next((n.__dict__ for n in nodes if n.code==code),None)
                    nodes=[n for n in nodes if n.code!=code]+[Term(value['axis'],code,ko,en,value['active'],value['replacement'])]
                    new=Facets(nodes,version);contract=new.contract()
                    terms=[(version,'facet',n.axis,n.code,None,n.ko,n.en,'[]',int(n.active),n.replacement) for n in new.terms]
            except (TaxonomyError,ValueError,TypeError):raise LibraryError('INVALID_PARAMS') from None
            self.db.execute('INSERT INTO classification_dictionaries VALUES (?,?,?)',(version,kind,json.dumps(contract,ensure_ascii=False,separators=(',',':'))))
            self.db.executemany('INSERT INTO classification_terms VALUES (?,?,?,?,?,?,?,?,?,?)',terms)
            self.admin_log(kind,code,version,before,value)
            return dict(version=version,usedAssets=params['expected_usage'],oldAssignmentsPreserved=True)
        return self.transaction(operation)

    def tag_get(self, params):
        self.keys(params,'tag_id')
        if not valid_id(params['tag_id']):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT id,label,enabled,revision FROM tags WHERE id=?',(params['tag_id'],)).fetchone()
        if not row:raise LibraryError('INVALID_PARAMS')
        users=[dict(asset_id=r[0],revision=r[1] or 0) for r in self.db.execute("SELECT at.asset_id,d.revision FROM asset_tags at LEFT JOIN metadata_decisions d ON d.asset_id=at.asset_id AND d.field='user_tags' WHERE at.tag_id=? AND at.source='user' ORDER BY at.asset_id",(row[0],))]
        ai=self.db.execute("SELECT count(*) FROM asset_tags WHERE tag_id=? AND source='ai'",(row[0],)).fetchone()[0]
        if len(users)>100:raise LibraryError('INVALID_PARAMS')
        plan=dict(tag_id=row[0],revision=row[3],userAssets=users,aiReferences=ai,canDelete=not users and not ai)
        return dict(id=row[0],label=row[1],enabled=bool(row[2]),revision=row[3],plan=plan)

    def tag_save(self, params):
        self.keys(params,'tag_id value plan confirmed');self.keys(params['value'],'label enabled')
        if params['confirmed'] is not True or type(params['value']['enabled']) is not bool:raise LibraryError('INVALID_PARAMS')
        label=self.text(params['value']['label'],64,True);normalized=label.casefold()
        def operation():
            before=self.tag_get({'tag_id':params['tag_id']}) if params['tag_id'] is not None else None
            if (before['plan'] if before else None)!=params['plan']:raise LibraryError('METADATA_CONFLICT')
            duplicate=self.db.execute('SELECT id FROM tags WHERE normalized_label=?',(normalized,)).fetchone()
            if duplicate and (not before or duplicate[0]!=before['id']):raise LibraryError('INVALID_PARAMS')
            identifier=before['id'] if before else str(uuid4());revision=before['revision']+1 if before else 1
            self.db.execute('INSERT INTO tags(id,label,normalized_label,enabled,revision) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,normalized_label=excluded.normalized_label,enabled=excluded.enabled,revision=excluded.revision',(identifier,label,normalized,params['value']['enabled'],revision))
            if before and before['label']!=label:
                for asset in before['plan']['userAssets']:
                    labels=[r[0] for r in self.db.execute("SELECT t.label FROM tags t JOIN asset_tags a ON a.tag_id=t.id WHERE a.asset_id=? AND a.source='user' ORDER BY t.normalized_label",(asset['asset_id'],))]
                    if sum(map(len,labels))>512:raise LibraryError('INVALID_PARAMS')
                    self.db.execute("INSERT INTO metadata_decisions VALUES (?,'user_tags','set',?,NULL,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id,field) DO UPDATE SET action='set',value_json=excluded.value_json,claim_id=NULL,revision=excluded.revision,updated_at=excluded.updated_at",(asset['asset_id'],json.dumps(labels,ensure_ascii=False),asset['revision']+1))
            result=self.tag_get({'tag_id':identifier});self.admin_log('tag',identifier,revision,before,result);return result
        return self.transaction(operation)

    def tag_delete(self, params):
        self.keys(params,'plan confirmed');plan=params['plan']
        if params['confirmed'] is not True or not isinstance(plan,dict):raise LibraryError('INVALID_PARAMS')
        def operation():
            before=self.tag_get({'tag_id':plan.get('tag_id')})
            if before['plan']!=plan:raise LibraryError('METADATA_CONFLICT')
            if not before['plan']['canDelete']:raise LibraryError('INVALID_PARAMS')
            self.db.execute('DELETE FROM tags WHERE id=?',(before['id'],));self.admin_log('tag',before['id'],before['revision']+1,before,None)
            return {'deleted':before['id'],'affectedAssets':0}
        return self.transaction(operation)
