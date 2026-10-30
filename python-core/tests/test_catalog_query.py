import json
import unittest
from uuid import uuid4
import test_annotations as fixtures
import test_creators as creator_fixtures
import test_licenses as license_fixtures
from ai_asset_hub_core.catalog_query import CatalogQuery,criteria,UNKNOWN
from ai_asset_hub_core.catalog import Catalog
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.provenance import Provenance
from ai_asset_hub_core.license_records import Licenses
from ai_asset_hub_core.metadata_store import MetadataStore
from ai_asset_hub_core.libraries import LibraryError


class CatalogQueryTests(unittest.TestCase):
    setUp=fixtures.AnnotationTests.setUp
    tearDown=fixtures.AnnotationTests.tearDown

    def query(self,filters,after=None,text=''):
        return CatalogQuery(self.db).query(dict(query=text,criteria=filters,after_id=after))

    def extra_assets(self,count):
        library=self.db.connection.execute('SELECT library_root_id FROM assets WHERE id=?',(self.id,)).fetchone()[0];ids=[]
        for index in range(count):
            asset=str(uuid4());file=str(uuid4());ids.append(asset)
            self.db.connection.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)',(asset,library,'needle '+str(index)))
            self.db.connection.execute("INSERT INTO asset_files VALUES (?,?,?,?,'txt',?,1,NULL,1)",(file,asset,'file'+str(index),str(self.base/('fixture-'+str(index))),index+1))
        return ids

    def test_same_axis_or_cross_axis_and_hierarchy_and_real_creator_roles(self):
        service=Catalog(self.db);parent=service.group_create({'value':dict(name='parent',description='')});child=service.group_create({'value':dict(name='child',description='')})
        service.group_move(dict(group_id=child['id'],parent_id=parent['id'],expected_revision=1));service.group_assign(dict(asset_id=self.id,group_ids=[child['id']],expected_revision=0))
        MetadataStore(self.db).classify(self.id,primary='A01.01',facets={'style':['style.pixel'],'genre':['genre.fantasy']},expected_revision=0,confirmed=True)
        creator=Creators(self.db).create({'value':creator_fixtures.CreatorTests.value(self)})
        Provenance(self.db).save_links(dict(subject={'kind':'asset','id':self.id},links=[dict(creator_id=creator['id'],role='producer')],expected_revision=0))
        Licenses(self.db).create_record(dict(subject={'kind':'asset','id':self.id},value=license_fixtures.LicenseTests.license_value(self),confirmed=True))
        filters=dict(group_ids=[parent['id']],types=['A01'],styles=['style.cartoon','style.pixel'],genres=['genre.fantasy'],creator_ids=[creator['id']],creator_roles=['producer'],license_status=['unknown'])
        self.assertEqual(self.query(filters)['ids'],[self.id]);self.assertEqual(self.query({**filters,'include_descendants':False})['ids'],[])
        self.assertEqual(self.query({**filters,'styles':['style.cartoon']})['ids'],[])
        self.assertEqual(self.query({**filters,'creator_roles':['distributor']})['ids'],[])

    def test_unknown_values_numeric_ranges_and_missing_do_not_become_zero(self):
        self.assertEqual(self.query(dict(types=[UNKNOWN],creator_ids=[UNKNOWN],rating_unknown=True,size_unknown=False,min_size=8,max_size=8))['ids'],[self.id])
        self.assertEqual(self.query(dict(min_rating=1,max_rating=5))['ids'],[])
        self.assertEqual(self.query(dict(min_rating=1,max_rating=5,rating_unknown=True))['ids'],[self.id])
        self.assertEqual(self.query(dict(min_width=100))['ids'],[])
        self.assertEqual(self.query(dict(min_width=100,technical_unknown=True))['ids'],[self.id])
        self.db.connection.execute('UPDATE asset_files SET exists_flag=0 WHERE asset_id=?',(self.id,))
        self.assertEqual(self.query(dict(availability='missing',size_unknown=True))['ids'],[self.id])
        self.assertEqual(self.query(dict(min_size=0))['ids'],[])

    def test_filters_are_applied_before_two_hundred_item_pages(self):
        ids=self.extra_assets(202);group=Catalog(self.db).group_create({'value':dict(name='target',description='')})
        selected=sorted(ids)[-2:]
        self.db.connection.executemany('INSERT INTO asset_group_members VALUES (?,?)',[(group['id'],i) for i in selected])
        page=self.query({'group_ids':[group['id']]},text='needle')
        self.assertEqual(page['ids'],selected);self.assertIsNone(page['next_cursor'])
        first=self.query({},text='needle');second=self.query({},first['next_cursor'],text='needle')
        self.assertEqual(len(first['ids']),200);self.assertEqual(len(second['ids']),2);self.assertEqual(len(set(first['ids']+second['ids'])),202)

    def test_invalid_filters_are_rejected_and_reads_create_no_jobs_or_vectors(self):
        for filters in ({'min_size':True},{'min_size':10,'max_size':1},{'min_rating':0},{'license_status':['allowed']},{'creator_ids':['fake']},{'unexpected':True}):
            with self.assertRaises(LibraryError):self.query(filters)
        self.query({'license_status':['unknown'],'management_states':['unreviewed'],'favorite':False})
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
