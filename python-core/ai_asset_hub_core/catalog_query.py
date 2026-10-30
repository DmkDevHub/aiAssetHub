"""Offline compound predicates, shared by lexical and explicit semantic ranking."""
import json
import unicodedata
import base64
import hashlib
import os
import re
from decimal import Decimal
from datetime import datetime, timezone
from .libraries import LibraryError, valid_id
from .analysis_state import asset_state
from .packages import Packages


UNKNOWN='__unknown__'
ARRAYS=('group_ids','package_ids','types','creator_ids','creator_roles','roles','styles','genres','views','dimensions','engines','license_labels','license_status','purchase_status','management_states','tags','formats')
RANGES=('size','rating','width','height','duration')
SORTS=('source','name','kind','modified','analysis','size','size_desc','registered','registered_asc','creator','relevance')


def timestamp(value):
    if not value:return None
    try:
        delta=datetime.fromisoformat(value.replace('Z','+00:00'))-datetime(1970,1,1,tzinfo=timezone.utc)
        return (delta.days*86400+delta.seconds)*1000000000+delta.microseconds*1000
    except (ValueError,TypeError):return None


def criteria(value):
    defaults=dict(library_id=None,folder_parts=[],kind='',tag='',analysis='',group_id=None,include_descendants=True,favorite=None,
                  size_unknown=False,rating_unknown=False,technical_unknown=False,availability='',purchase_currency='')
    defaults.update({key:[] for key in ARRAYS});defaults.update({side+'_'+key:None for key in RANGES for side in ('min','max')})
    if not isinstance(value,dict) or set(value)-set(defaults):raise LibraryError('INVALID_PARAMS')
    result={**defaults,**value}
    for key in ('library_id','group_id'):
        if result[key] is not None and not valid_id(result[key]):raise LibraryError('INVALID_PARAMS')
    parts=result['folder_parts']
    if not isinstance(parts,list) or len(parts)>32 or any(not isinstance(p,str) or not p or len(p)>255 or p in ('.','..') or '/' in p or '\\' in p or any(ord(c)<32 for c in p) for p in parts) or parts and not result['library_id']:raise LibraryError('INVALID_PARAMS')
    for key in ('kind','tag','analysis','availability','purchase_currency'):
        if not isinstance(result[key],str) or len(result[key])>64:raise LibraryError('INVALID_PARAMS')
    if result['analysis'] not in ('','completed','unanalyzed','failed') or result['availability'] not in ('','available','partial','missing'):raise LibraryError('INVALID_PARAMS')
    if result['purchase_currency'] and not re.fullmatch('[A-Z]{3}',result['purchase_currency']):raise LibraryError('INVALID_PARAMS')
    for key in ('include_descendants','size_unknown','rating_unknown','technical_unknown'):
        if type(result[key]) is not bool:raise LibraryError('INVALID_PARAMS')
    if result['favorite'] is not None and type(result['favorite']) is not bool:raise LibraryError('INVALID_PARAMS')
    for key in ARRAYS:
        values=result[key]
        if not isinstance(values,list) or len(values)>16 or any(not isinstance(v,str) or not v or len(v)>128 or any(unicodedata.category(c).startswith('C') for c in v) for v in values):raise LibraryError('INVALID_PARAMS')
        result[key]=list(dict.fromkeys(values))
    for key in ('group_ids','package_ids','creator_ids','tags'):
        if any(v!=UNKNOWN and not valid_id(v) for v in result[key]):raise LibraryError('INVALID_PARAMS')
    if result['group_id']:result['group_ids']=list(dict.fromkeys([*result['group_ids'],result['group_id']]))
    if set(result['purchase_status'])-{'unknown','free','paid'} or set(result['creator_roles'])-{'creator','producer','distributor'} or set(result['license_status'])-{'unknown','needs_review','user_reviewed'} or set(result['management_states'])-{'unreviewed','reviewing','approved','archived'}:raise LibraryError('INVALID_PARAMS')
    for key in RANGES:
        low,high=result['min_'+key],result['max_'+key]
        if any(v is not None and (type(v) is not int or not (1 if key=='rating' else 0)<=v<=(5 if key=='rating' else 9007199254740991)) for v in (low,high)) or low is not None and high is not None and low>high:raise LibraryError('INVALID_PARAMS')
    return result


def normalized(value):return unicodedata.normalize('NFKC',str(value)).casefold()


class CatalogQuery:
    def __init__(self,database):self.database=database;self.db=database.connection

    def data(self,identifier):
        row=self.db.execute('SELECT a.id,a.library_root_id,f.relative_path,f.extension,a.created_at,a.updated_at,coalesce(u.title_override,a.display_name) '
            'FROM assets a JOIN library_roots l ON l.id=a.library_root_id JOIN asset_files f ON f.asset_id=a.id LEFT JOIN asset_user_annotations u ON u.asset_id=a.id WHERE a.id=? AND l.enabled=1 ORDER BY f.id LIMIT 1',(identifier,)).fetchone()
        if not row:return None
        return dict(zip(('id','library','path','kind','created','modified','name'),row))

    def metrics(self,identifier):
        rows=self.db.execute('SELECT DISTINCT f.id,f.size_bytes,f.exists_flag,o.width,o.height,o.duration_ms FROM asset_file_members m JOIN asset_files f ON f.id=m.file_id LEFT JOIN asset_observations o ON o.asset_file_id=f.id WHERE m.asset_id=?',(identifier,)).fetchall()
        available=[r for r in rows if r[2]]
        return dict(size=sum(r[1] for r in available) if available else None,availability='available' if rows and len(available)==len(rows) else 'partial' if available else 'missing',
                    **{key:max((r[index] for r in available if r[index] is not None),default=None) for key,index in [('width',3),('height',4),('duration',5)]})

    def creators(self,identifier):
        return self.db.execute('SELECT c.id,m.role,c.name FROM asset_creator_links m JOIN creators c ON c.id=m.creator_id WHERE m.asset_id=? UNION SELECT c.id,m.role,c.name FROM asset_package_members p JOIN asset_packages k ON k.id=p.package_id AND k.enabled=1 JOIN package_creator_links m ON m.package_id=p.package_id JOIN creators c ON c.id=m.creator_id WHERE p.asset_id=?',(identifier,identifier)).fetchall()

    @staticmethod
    def axis(values,wanted,descendants=False):
        return not wanted or any(v==UNKNOWN and not values or any(actual==v or descendants and actual.startswith(v+'.') for actual in values) for v in wanted)

    @staticmethod
    def numeric(value,low,high,unknown=False):
        if low is None and high is None:return value is None if unknown else True
        return unknown if value is None else (low is None or value>=low) and (high is None or value<=high)

    def matches(self,identifier,f):
        row=self.data(identifier)
        if not row:return False
        if f['library_id'] and row['library']!=f['library_id'] or row['path'].replace('\\','/').split('/')[:len(f['folder_parts'])]!=f['folder_parts']:return False
        if f['kind'] and (row['kind'].lstrip('.').upper() or 'FILE')!=f['kind']:return False
        if f['formats'] and not (self.axis([row['kind'].lstrip('.').upper() or 'FILE'],f['formats']) or UNKNOWN in f['formats'] and not row['kind']):return False
        if f['analysis']:
            state=asset_state(self.db,identifier)
            if f['analysis']=='completed' and not state['hasActiveResult'] or f['analysis']=='unanalyzed' and state['hasActiveResult'] or f['analysis']=='failed' and state['lastAttemptState']!='failed':return False
        if f['tag'] or f['tags']:
            tags=self.db.execute("SELECT t.id,t.label FROM asset_tags m JOIN tags t ON t.id=m.tag_id WHERE m.asset_id=? AND m.source='user'",(identifier,)).fetchall()
            if f['tag'] and normalized(f['tag']) not in [normalized(t[1]) for t in tags] or not self.axis([t[0] for t in tags],f['tags']):return False
        if f['group_ids']:
            groups=[r[0] for r in self.db.execute('SELECT group_id FROM asset_group_members WHERE asset_id=?',(identifier,))]
            candidates=list(groups)
            if f['include_descendants'] and groups:candidates=[r[0] for r in self.db.execute('SELECT DISTINCT parent FROM catalog_group_ancestors WHERE child IN (SELECT group_id FROM asset_group_members WHERE asset_id=?)',(identifier,))]
            if not any(v==UNKNOWN and not groups or v in candidates for v in f['group_ids']):return False
        packages=None
        if f['package_ids'] or f['license_labels'] or f['license_status']:
            packages=[r[0] for r in self.db.execute('SELECT p.id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1',(identifier,))]
            if not self.axis(packages,f['package_ids']):return False
        if f['creator_ids'] or f['creator_roles']:
            creators=self.creators(identifier)
            if f['creator_ids'] and not any(v==UNKNOWN and not creators or any(r[0]==v for r in creators) for v in f['creator_ids']):return False
            if f['creator_roles'] and not any(r[1] in f['creator_roles'] and (not f['creator_ids'] or r[0] in f['creator_ids']) for r in creators):return False
        if any(f[k] for k in ('types','roles','styles','genres','views','dimensions','engines')):
            classes={}
            for axis,code in self.db.execute('SELECT axis,code FROM asset_classification_links WHERE asset_id=?',(identifier,)):classes.setdefault(axis,[]).append(code)
            primary=self.db.execute('SELECT primary_code FROM asset_classification_selections WHERE asset_id=?',(identifier,)).fetchone()
            if primary and primary[0]:classes.setdefault('type',[]).append(primary[0])
            for key,axis in [('types','type'),('roles','role'),('styles','style'),('genres','genre'),('views','view'),('dimensions','dimension')]:
                if not self.axis(classes.get(axis,[]),f[key],axis=='type' and f['include_descendants']):return False
            if f['engines']:
                values=classes.get('engine',[]);effective=Packages(self.database).package_effective({'asset_id':identifier})['fields']['engine']
                if effective['value']:values=[*values,'engine.'+normalized(effective['value'])]
                if not self.axis(values,f['engines']):return False
        if f['license_labels'] or f['license_status']:
            rows=self.db.execute('SELECT value_json FROM provenance_licenses WHERE enabled=1 AND (asset_id=? OR package_id IN (SELECT m.package_id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1))',(identifier,identifier)).fetchall()
            licenses=[json.loads(r[0]) for r in rows]
            if f['license_labels'] and not set(normalized(v['label']) for v in licenses)&set(normalized(v) for v in f['license_labels']):return False
            states=[v['reviewStatus'] for v in licenses] or ['unknown']
            if f['license_status'] and not set(states)&set(f['license_status']):return False
        if f['purchase_status'] or f['purchase_currency']:
            purchases=[json.loads(r[0])['purchase'] for r in self.db.execute('SELECT value_json FROM provenance_sources WHERE enabled=1 AND (asset_id=? OR package_id IN (SELECT m.package_id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1))',(identifier,identifier))]
            purchases.extend(json.loads(r[0]) for r in self.db.execute('SELECT p.purchase_json FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1',(identifier,)))
            # Only evaluate declarations; never export the amounts/dates or infer permission.
            def purchase_matches(p):
                state='unknown' if p.get('amount') is None else 'free' if Decimal(p['amount'])==0 else 'paid'
                return (not f['purchase_status'] or state in f['purchase_status']) and (not f['purchase_currency'] or p.get('currency')==f['purchase_currency'])
            if not any(purchase_matches(p) for p in purchases or [{}]):return False
        if f['management_states'] or f['favorite'] is not None or f['min_rating'] is not None or f['max_rating'] is not None or f['rating_unknown']:
            raw=self.db.execute("SELECT value_json FROM metadata_decisions WHERE asset_id=? AND field='management'",(identifier,)).fetchone();management=json.loads(raw[0]) if raw else {}
            if f['management_states'] and management.get('status','unreviewed') not in f['management_states'] or f['favorite'] is not None and management.get('favorite',False)!=f['favorite']:return False
            if not self.numeric(management.get('rating'),f['min_rating'],f['max_rating'],f['rating_unknown']):return False
        if f['availability'] or f['size_unknown'] or f['technical_unknown'] or any(f[side+'_'+key] is not None for key in ('size','width','height','duration') for side in ('min','max')):
            metrics=self.metrics(identifier)
            if f['availability'] and metrics['availability']!=f['availability']:return False
            for key in ('size','width','height','duration'):
                unknown=f['size_unknown'] if key=='size' else f['technical_unknown'] and (f['min_'+key] is not None or f['max_'+key] is not None)
                if not self.numeric(metrics[key],f['min_'+key],f['max_'+key],unknown):return False
            if f['technical_unknown'] and not any(f[s+'_'+k] is not None for k in ('width','height','duration') for s in ('min','max')) and any(metrics[k] is not None for k in ('width','height','duration')):return False
        return True

    def sorted_ids(self,ids,sort,texts=None,terms=()):
        if sort not in SORTS:raise LibraryError('INVALID_PARAMS')
        result=sorted(ids)  # Every equal key has the same UUID tie-break, in both directions.
        if sort=='source':return result
        def key(identifier):
            row=self.data(identifier)
            if not row:raise LibraryError('ASSET_NOT_FOUND')
            if sort=='name':return normalized(row['name'])
            if sort=='kind':return normalized(row['kind'])
            if sort in ('size','size_desc'):return self.metrics(identifier)['size']
            if sort in ('registered','registered_asc'):return timestamp(row['created'])
            if sort=='analysis':return timestamp(asset_state(self.db,identifier)['lastAnalysisAt'])
            if sort=='creator':
                creators=self.creators(identifier);names=[normalized(r[2]) for r in creators if r[1]=='producer'] or [normalized(r[2]) for r in creators]
                return min(names,default=None)
            if sort=='relevance':return sum((texts or {}).get(identifier,'').count(term) for term in terms)
            times=[timestamp(row['modified'])]
            for table in ('asset_user_annotations','metadata_decisions','catalog_documents'):
                times.extend(timestamp(r[0]) for r in self.db.execute('SELECT updated_at FROM '+table+' WHERE asset_id=?',(identifier,)))
            times.extend(r[0] for r in self.db.execute('SELECT f.mtime_ns FROM asset_file_members m JOIN asset_files f ON f.id=m.file_id WHERE m.asset_id=? AND f.exists_flag=1',(identifier,)))
            times.extend(timestamp(r[0]) for r in self.db.execute("SELECT created_at FROM provenance_history WHERE (subject_kind='asset' AND subject_id=?) OR (subject_kind='package' AND subject_id IN (SELECT m.package_id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1))",(identifier,identifier)))
            return max((t for t in times if t is not None),default=None)
        keys={identifier:key(identifier) for identifier in result}
        known=[i for i in result if keys[i] is not None];unknown=[i for i in result if keys[i] is None]
        known.sort(key=lambda i:keys[i],reverse=sort in ('modified','analysis','size_desc','registered','relevance'))
        return known+unknown

    def order(self,params):
        if not isinstance(params,dict) or set(params)!={'asset_ids','sort'} or not isinstance(params['asset_ids'],list) or len(params['asset_ids'])>100 or any(not valid_id(i) for i in params['asset_ids']) or len(set(params['asset_ids']))!=len(params['asset_ids']) or params['sort'] not in SORTS:raise LibraryError('INVALID_PARAMS')
        if any(not self.data(i) for i in params['asset_ids']):raise LibraryError('ASSET_NOT_FOUND')
        # Preserve an already computed semantic ranking; never create a new query vector.
        ids=list(params['asset_ids']) if params['sort'] in ('source','relevance') else self.sorted_ids(params['asset_ids'],params['sort'])
        return {'ids':ids,'inferenceCalled':False}

    def stamp(self):return [os.getpid(),self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0]]

    def query(self,params):
        if not isinstance(params,dict) or set(params)-{'query','criteria','after_id','sort'} or not {'query','criteria','after_id'}<=set(params) or not isinstance(params['query'],str) or len(params['query'])>256:raise LibraryError('INVALID_PARAMS')
        f=criteria(params['criteria']);cursor=params['after_id'];sort=params.get('sort','source')
        if not isinstance(sort,str) or sort not in SORTS:raise LibraryError('INVALID_PARAMS')
        stamp=self.stamp();digest=hashlib.sha256(json.dumps([params['query'],f,sort],sort_keys=True).encode()).hexdigest()
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>512:raise ValueError()
                decoded=json.loads(base64.b64decode(cursor.encode(),altchars=b'-_',validate=True))
                if set(decoded)!={'id','stamp','digest'} or not valid_id(decoded['id']):raise ValueError()
                if decoded['stamp']!=stamp or decoded['digest']!=digest:raise LibraryError('METADATA_CONFLICT')
                after=decoded['id']
            except (ValueError,TypeError,UnicodeError):raise LibraryError('INVALID_PARAMS') from None
        terms=normalized(params['query']).split()
        if len(terms)>16:raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('SELECT d.asset_id,d.searchable_text FROM catalog_documents d JOIN assets a ON a.id=d.asset_id JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 ORDER BY d.asset_id LIMIT 10001').fetchall()
        if len(rows)>10000:raise LibraryError('CATALOG_LIMIT')
        ids=self.sorted_ids([identifier for identifier,text in rows if all(term in text for term in terms) and self.matches(identifier,f)],sort,dict(rows),terms)
        if after is not None:
            if after not in ids:raise LibraryError('METADATA_CONFLICT')
            ids=ids[ids.index(after)+1:]
        if self.stamp()!=stamp:raise LibraryError('METADATA_CONFLICT')
        next_cursor=base64.urlsafe_b64encode(json.dumps(dict(id=ids[199],stamp=stamp,digest=digest)).encode()).decode() if len(ids)>200 else None
        return {'ids':ids[:200],'next_cursor':next_cursor,'inferenceCalled':False}
