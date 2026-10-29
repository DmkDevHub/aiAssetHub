"""Core-internal explicit metadata storage. Not a public UI/MCP write API."""
import json
import re
from uuid import uuid4
from .libraries import valid_id
from .metadata_values import Claim,FieldState,MetadataError,json_value
from .taxonomy import default_taxonomy,Taxonomy,Category
from .classification_axes import default_facets,Facets,Term


def packed(value):return json.dumps(json_value(value),ensure_ascii=False,separators=(',',':'))


class MetadataStore:
    def __init__(self,database):self.db=database.connection

    def dictionary(self,version,kind):
        row=self.db.execute('SELECT payload_json FROM classification_dictionaries WHERE version=? AND kind=?',(version,kind)).fetchone()
        if not row:raise MetadataError('DICTIONARY_UNAVAILABLE')
        snapshot=json.loads(row[0])
        if kind=='facet':return Facets((Term(**n) for n in snapshot['terms']),version)
        return Taxonomy((Category(n['code'],n['parent'],n['labels']['ko'],n['labels']['en'],tuple(n['aliases']),n['active']) for n in snapshot['categories']),version)

    def require(self,asset,field):
        if not valid_id(asset) or not isinstance(field,str) or not re.fullmatch('[a-z][a-z0-9_.]{0,63}',field):raise MetadataError('INVALID_METADATA')
        if not self.db.execute('SELECT 1 FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1',(asset,)).fetchone():raise MetadataError('ASSET_UNAVAILABLE')

    def state(self,asset,field):
        self.require(asset,field);state=FieldState()
        for identifier,source,value,file,result,schema in self.db.execute('SELECT id,source,value_json,evidence_file_id,analysis_result_id,schema_version FROM metadata_claims WHERE asset_id=? AND field=? ORDER BY rowid',(asset,field)):
            state.propose(Claim(identifier,source,json.loads(value),('result:' if result else 'file:')+(result or file),schema))
        decision=self.db.execute('SELECT action,value_json,claim_id,revision FROM metadata_decisions WHERE asset_id=? AND field=?',(asset,field)).fetchone()
        if decision:
            state._decision={'value':json.loads(decision[1]),'source':'user','status':'cleared' if decision[0]=='clear' else 'confirmed','claimId':decision[2]}
            state.revision=decision[3]
        return state

    def effective(self,asset,field):
        state=self.state(asset,field);return {**state.selected(),'revision':state.revision}

    def propose(self,asset,field,source,value,evidence_id,schema_version):
        self.require(asset,field)
        if not valid_id(evidence_id):raise MetadataError('INVALID_EVIDENCE')
        identifier=str(uuid4());claim=Claim(identifier,source,value,evidence_id,schema_version);FieldState().propose(claim)
        if source=='ai':
            if not self.db.execute('SELECT 1 FROM analysis_results WHERE id=? AND asset_id=?',(evidence_id,asset)).fetchone():raise MetadataError('INVALID_EVIDENCE')
        elif not self.db.execute('SELECT 1 FROM asset_file_members WHERE asset_id=? AND file_id=?',(asset,evidence_id)).fetchone():raise MetadataError('INVALID_EVIDENCE')
        self.db.execute("INSERT INTO metadata_claims VALUES (?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",(identifier,asset,field,source,packed(value),evidence_id if source!='ai' else None,evidence_id if source=='ai' else None,schema_version))
        return identifier

    def _decide(self,asset,field,action,expected_revision,confirmed,value,claim_id):
        state=self.state(asset,field);result=state.decide(action,expected_revision=expected_revision,confirmed=confirmed,value=value,claim_id=claim_id)
        self.db.execute("INSERT INTO metadata_decisions VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id,field) DO UPDATE SET action=excluded.action,value_json=excluded.value_json,claim_id=excluded.claim_id,revision=excluded.revision,updated_at=excluded.updated_at",(asset,field,action,packed(result['value']),result['claimId'],state.revision))
        return {**result,'revision':state.revision}

    def decide(self,asset,field,action,*,expected_revision,confirmed,value=None,claim_id=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result=self._decide(asset,field,action,expected_revision,confirmed,value,claim_id);self.db.execute('COMMIT');return result
        except Exception:self.db.execute('ROLLBACK');raise

    def classify(self,asset,*,primary=None,navigation=(),facets=None,expected_revision,confirmed,type_version=None,facet_version=None):
        types=self.dictionary(type_version or default_taxonomy().version,'type');axes=self.dictionary(facet_version or default_facets().version,'facet')
        value={'type':types.assignment(primary,navigation,version=types.version),'facets':axes.assignment(facets or {},version=axes.version)}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._decide(asset,'classification','set',expected_revision,confirmed,value,None)
            self.db.execute('DELETE FROM asset_classification_links WHERE asset_id=?',(asset,))
            self.db.execute('INSERT INTO asset_classification_selections(asset_id,type_version,primary_code) VALUES (?,?,?) ON CONFLICT(asset_id) DO UPDATE SET type_version=excluded.type_version,primary_code=excluded.primary_code',(asset,types.version,value['type']['primary']))
            self.db.executemany('INSERT INTO asset_classification_links VALUES (?,?,?,?)',[(asset,types.version,'type',code) for code in value['type']['navigation']]+[(asset,axes.version,axis,code) for axis,codes in value['facets']['values'].items() for code in codes])
            self.db.execute('COMMIT');return value
        except Exception:self.db.execute('ROLLBACK');raise

    def retire_facet(self,code,*,new_version,replacement=None,confirmed=False,version=None):
        old=self.dictionary(version or default_facets().version,'facet');self.db.execute('BEGIN IMMEDIATE')
        try:
            used=self.db.execute('SELECT count(DISTINCT asset_id) FROM asset_classification_links WHERE version=? AND code=?',(old.version,code)).fetchone()[0]
            new=old.retire(code,new_version=new_version,used=bool(used),replacement=replacement,confirmed=confirmed)
            contract=new.contract()
            self.db.execute('INSERT INTO classification_dictionaries VALUES (?,?,?)',(new.version,'facet',packed(contract)))
            self.db.executemany('INSERT INTO classification_terms VALUES (?,?,?,?,?,?,?,?,?,?)',[(new.version,'facet',t.axis,t.code,None,t.ko,t.en,'[]',int(t.active),t.replacement) for t in new.terms])
            self.db.execute('COMMIT');return {'version':new.version,'affectedAssetCount':used,'requiresReassignment':bool(used)}
        except Exception:self.db.execute('ROLLBACK');raise
