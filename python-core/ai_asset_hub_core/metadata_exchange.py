"""Versioned public metadata exchange. Never exports paths, credentials or private provenance."""
import csv
import io
import json
from .bulk_metadata import BulkMetadata,FIELDS,identifiers,bounded
from .annotations import AnnotationService
from .asset_management import AssetManagement
from .libraries import LibraryError

SCHEMA='metadata-exchange.v1'
EXPORT_FIELDS=FIELDS|{'basic','packages','relations'}
COLUMNS=('schema_version','asset_id','fields','values','versions')
MAX_DOCUMENT_BYTES=6000


def packed(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


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
