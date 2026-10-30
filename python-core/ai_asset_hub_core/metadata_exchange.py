"""Versioned public metadata exchange. Never exports paths, credentials or private provenance."""
import csv
import io
import json
from .bulk_metadata import BulkMetadata,FIELDS,identifiers,bounded
from .annotations import AnnotationService
from .asset_management import AssetManagement
from .libraries import LibraryError
from .analysis_contract import digest

SCHEMA='metadata-exchange.v1'
EXPORT_FIELDS=FIELDS|{'basic','packages','relations'}
COLUMNS=('schema_version','asset_id','fields','values','versions')
MAX_DOCUMENT_BYTES=6000


def packed(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def parse_document(content,format):
    from .transport import _unique_object
    def load(raw):return json.loads(raw,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    try:
        if not isinstance(content,str) or not content or len(content.encode('utf-8'))>MAX_DOCUMENT_BYTES:raise LibraryError('BULK_LIMIT')
        content=content.removeprefix('\ufeff')
        if format=='json':document=load(content)
        elif format=='csv':
            reader=csv.reader(io.StringIO(content,newline=''),strict=True)
            if next(reader)!=list(COLUMNS):raise ValueError()
            assets=[];fields=None
            for row in reader:
                if len(row)!=len(COLUMNS) or row[0]!=SCHEMA or len(assets)>=20:raise ValueError()
                row_fields=load(row[2])
                if fields is not None and row_fields!=fields:raise ValueError()
                fields=row_fields;assets.append({'asset_id':row[1],'values':load(row[3]),'versions':load(row[4])})
            document={'schema_version':SCHEMA,'fields':fields,'assets':assets}
        else:raise ValueError()
        if not isinstance(document,dict) or set(document)!={'schema_version','fields','assets'} or document['schema_version']!=SCHEMA:raise ValueError()
        fields,assets=document['fields'],document['assets']
        if not isinstance(fields,list) or not fields or any(not isinstance(f,str) or f not in EXPORT_FIELDS for f in fields) or len(set(fields))!=len(fields):raise ValueError()
        if not isinstance(assets,list) or not 1<=len(assets)<=20:raise ValueError()
        for row in assets:
            if not isinstance(row,dict) or set(row)!={'asset_id','values','versions'} or not isinstance(row['values'],dict) or not isinstance(row['versions'],dict) or set(row['values'])!=set(fields) or set(row['versions'])!=set(fields):raise ValueError()
        identifiers([r['asset_id'] for r in assets],20)
        return document
    except LibraryError:raise
    except (ValueError,TypeError,UnicodeError,RecursionError,StopIteration,csv.Error):raise LibraryError('INVALID_PARAMS') from None


class MetadataExchange(BulkMetadata):
    def export_value(self,asset,field):
        if field=='basic':
            state=AnnotationService(self.database).get({'asset_id':asset})
            return {key:state[key] for key in ('title','description','aliases')},state['revision']
        if field=='packages':
            state=self.membership_value(asset,'package');return state['ids'],state['revision']
        if field=='relations':
            state=AssetManagement(self.database).relations({'asset_id':asset});return state['value'],state['revision']
        value,version,_=self.read_field(asset,field)
        return value,version

    def export(self,params):
        self.keys(params,'asset_ids fields format')
        assets=identifiers(params['asset_ids'],20);fields=params['fields'];format=params['format']
        if not assets or not isinstance(fields,list) or not fields or any(not isinstance(f,str) or f not in EXPORT_FIELDS for f in fields) or len(set(fields))!=len(fields) or format not in ('json','csv'):raise LibraryError('INVALID_PARAMS')
        fields=sorted(fields);rows=[]
        self.db.execute('BEGIN')
        try:
            for asset in assets:
                self.require_asset(asset);values={};versions={}
                for field in fields:values[field],versions[field]=self.export_value(asset,field)
                rows.append({'asset_id':asset,'values':values,'versions':versions})
            document={'schema_version':SCHEMA,'fields':fields,'assets':rows}
            if format=='json':content=packed(document)
            else:
                # Every untrusted field value is inside a JSON object cell, beginning
                # with '{'. It cannot become an Excel formula, even with whitespace.
                output=io.StringIO(newline='');writer=csv.writer(output,lineterminator='\r\n');writer.writerow(COLUMNS)
                for row in rows:writer.writerow([SCHEMA,row['asset_id'],packed(fields),packed(row['values']),packed(row['versions'])])
                content=output.getvalue()
            if len(content.encode('utf-8'))>MAX_DOCUMENT_BYTES:raise LibraryError('BULK_LIMIT')
            result=bounded({'schemaVersion':SCHEMA,'format':format,'content':content,'assetCount':len(rows),
                'fields':fields,'privateFieldsExcluded':True,'inferenceCalled':False})
            self.db.execute('COMMIT');return result
        except Exception:self.db.execute('ROLLBACK');raise

    def import_plan(self,params):
        document=parse_document(params['content'],params['format']);current=params['use_current_versions']
        if type(current) is not bool:raise LibraryError('INVALID_PARAMS')
        targets=[];tokens=[]
        for row in sorted(document['assets'],key=lambda r:r['asset_id']):
            changes={}
            for field,value in row['values'].items():
                changes[field]={'set':value} if field in ('groups','packages','tags','creators') else {'records':value} if field=='sources' else value
            # Always validate the supplied versions even when explicitly rebasing.
            original={'asset_ids':[row['asset_id']],'changes':changes,'expected':{row['asset_id']:row['versions']}}
            items,token=self.targets(original,check_graph=False)
            if current:
                items,token=self.targets({'asset_ids':[row['asset_id']],'changes':changes},check_graph=False)
            targets.extend(items);tokens.append(token)
        self.validate_relations({t['assetId']:t['after']['relations'] for t in targets if 'relations' in t['after']})
        return targets,digest({'document':document,'tokens':tokens,'useCurrentVersions':current,'policy':'metadata-import.v1'})

    def import_preview(self,params):
        self.keys(params,'content format use_current_versions after_id plan_token')
        self.db.execute('BEGIN')
        try:
            targets,token=self.import_plan(params)
            if params['plan_token'] is not None and params['plan_token']!=token:raise LibraryError('METADATA_CONFLICT')
            cursor=params['after_id']
            if cursor is not None and cursor not in [t['assetId'] for t in targets]:raise LibraryError('INVALID_PARAMS')
            rows=[t for t in targets if cursor is None or t['assetId']>cursor]
            result=bounded({'items':rows[:1],'next_cursor':rows[0]['assetId'] if len(rows)>1 else None,'planToken':token,
                'targetCount':len(targets),'changedCount':sum(t['changed'] for t in targets),'conflictCount':sum(bool(t['conflicts']) for t in targets),
                'policy':'all-or-nothing','inferenceCalled':False})
            self.db.execute('COMMIT');return result
        except Exception:self.db.execute('ROLLBACK');raise

    def import_apply(self,params):
        self.keys(params,'content format use_current_versions plan_token confirmed')
        if params['confirmed'] is not True or not isinstance(params['plan_token'],str) or len(params['plan_token'])!=64:raise LibraryError('INVALID_PARAMS')
        def operation():
            targets,token=self.import_plan(params)
            if token!=params['plan_token'] or any(t['conflicts'] for t in targets):raise LibraryError('METADATA_CONFLICT')
            changed=[t for t in targets if t['changed']]
            for target in changed:self.apply_target(target)
            self.validate_relations({})
            if changed:
                from uuid import uuid4
                self.db.execute("INSERT INTO audit_events VALUES (?,'user','exchange.import','metadata',NULL,'succeeded',strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
                    (str(uuid4()),packed({'assetIds':[t['assetId'] for t in changed],'fields':sorted({f for t in changed for f in t['after']}),'policy':'all-or-nothing'})))
            return {'updated':len(changed),'unchanged':len(targets)-len(changed),'inferenceCalled':False,'policy':'all-or-nothing'}
        return self.transaction(operation)
