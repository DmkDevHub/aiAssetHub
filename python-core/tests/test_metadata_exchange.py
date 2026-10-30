import csv
import io
import json
import unittest
from unittest.mock import patch
import test_annotations
from ai_asset_hub_core.metadata_exchange import MetadataExchange,SCHEMA
from ai_asset_hub_core.source_records import Sources
from ai_asset_hub_core.libraries import LibraryError


class ExchangeTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def export(self,format='json',fields=None):return MetadataExchange(self.db).export({'asset_ids':[self.id],'fields':fields or ['basic','tags','sources'],'format':format})

    def test_selected_public_fields_and_actual_ids_export_without_private_values_or_writes(self):
        Sources(self.db).create_record({'subject':{'kind':'asset','id':self.id},'value':{'site':'상점','productName':'상품','originalUrl':'https://example.com/?key=PRIVATE-SECRET','productUrl':'','downloadUrl':'','purchase':{'amount':'12345','currency':'KRW','purchasedOn':'','downloadedOn':''}}})
        before='\n'.join(self.db.connection.iterdump());count=self.db.connection.total_changes
        with patch('builtins.open',side_effect=AssertionError('no file reads')),patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no AI')):result=self.export()
        document=json.loads(result['content']);self.assertEqual(document['schema_version'],SCHEMA)
        self.assertEqual(document['assets'][0]['asset_id'],self.id)
        self.assertEqual(set(document['assets'][0]['values']),{'basic','tags','sources'})
        self.assertNotIn('PRIVATE',result['content']);self.assertNotIn('12345',result['content']);self.assertNotIn(str(self.source),result['content'])
        self.assertEqual(self.db.connection.total_changes,count);self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_csv_json_cells_prevent_formula_injection_and_keep_unicode_quotes_newlines(self):
        self.service.save({'asset_id':self.id,'title':'=HYPERLINK("evil")','description':'한글\n쉼표, "따옴표"','aliases':['+formula','@value','-name'],'expected_revision':0})
        result=self.export('csv',['basic']);rows=list(csv.DictReader(io.StringIO(result['content'])))
        self.assertEqual(len(rows),1)
        for cell in rows[0].values():self.assertFalse(cell.lstrip().startswith(('=','+','-','@','\t','\r')))
        value=json.loads(rows[0]['values'])['basic'];self.assertEqual(value['title'],'=HYPERLINK("evil")');self.assertEqual(value['description'],'한글\n쉼표, "따옴표"')

    def test_export_rejects_unknown_private_fields_duplicate_ids_and_oversize(self):
        service=MetadataExchange(self.db)
        for params in ({'asset_ids':[self.id],'fields':['contact'],'format':'json'},{'asset_ids':[self.id,self.id],'fields':['tags'],'format':'csv'}, {'asset_ids':[self.id],'fields':['tags'],'format':'xml'}):
            with self.assertRaises(LibraryError):service.export(params)
