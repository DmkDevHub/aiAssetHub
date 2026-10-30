import json
import shutil
import unittest
import sqlite3
import test_annotations as fixtures
import test_creators as creator_fixtures
import test_provenance as provenance_fixtures
from ai_asset_hub_core.search import SearchService
from ai_asset_hub_core.catalog import Catalog
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.provenance import Provenance
from ai_asset_hub_core.packages import Packages
from ai_asset_hub_core.annotations import AnnotationService
from ai_asset_hub_core.metadata_store import MetadataStore
from ai_asset_hub_core.database import Database,migration_directory
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryService


class CatalogSearchTests(unittest.TestCase):
    setUp=fixtures.AnnotationTests.setUp
    tearDown=fixtures.AnnotationTests.tearDown

    def find(self, text):return SearchService(self.db).search({'query':text})['ids']

    def test_alias_type_ancestors_facets_and_group_rename_sync_offline(self):
        AnnotationService(self.db).save(dict(asset_id=self.id,title='',description='',aliases=['특수별칭'],expected_revision=0))
        self.assertEqual(self.find('특수별칭'),[self.id])
        MetadataStore(self.db).classify(self.id,primary='A01.01',facets={'style':['style.pixel']},expected_revision=0,confirmed=True)
        self.assertEqual(self.find('2D 그래픽'),[self.id]);self.assertEqual(self.find('픽셀아트'),[self.id])
        service=Catalog(self.db);parent=service.group_create({'value':dict(name='선조이름',description='')});child=service.group_create({'value':dict(name='후손이름',description='')})
        child=service.group_move(dict(group_id=child['id'],parent_id=parent['id'],expected_revision=1))
        service.group_assign(dict(asset_id=self.id,group_ids=[child['id']],expected_revision=0))
        self.assertEqual(self.find('선조이름'),[self.id])
        service.group_update(dict(group_id=parent['id'],value=dict(name='바뀐선조',description=''),expected_revision=1))
        self.assertEqual(self.find('선조이름'),[]);self.assertEqual(self.find('바뀐선조'),[self.id])
        self.db.connection.execute("INSERT INTO catalog_fts(catalog_fts,rank) VALUES ('integrity-check',1)")

    def test_package_creator_changes_reflect_but_private_fields_are_not_indexed(self):
        package=provenance_fixtures.ProvenanceTests.package(self);service=Packages(self.db)
        service.package_assign(dict(asset_id=self.id,package_ids=[package['id']],expected_revision=0))
        value=creator_fixtures.CreatorTests.value(self);value.update(name='고유제작사',brand='특수상표',contact='PRIVATE-DO-NOT-INDEX',homepageUrl='https://example.com/PRIVATE-URL')
        creator=Creators(self.db).create({'value':value})
        Provenance(self.db).save_links(dict(subject={'kind':'package','id':package['id']},links=[dict(creator_id=creator['id'],role='producer')],expected_revision=0))
        self.assertEqual(self.find('고유제작사'),[self.id]);self.assertEqual(self.find('특수상표'),[self.id])
        self.assertEqual(self.find('PRIVATE-DO-NOT-INDEX'),[]);self.assertEqual(self.find('PRIVATE-URL'),[])
        before=self.db.connection.execute('SELECT version FROM catalog_documents WHERE asset_id=?',(self.id,)).fetchone()[0]
        value['contact']='PRIVATE-CHANGED';Creators(self.db).update(dict(creator_id=creator['id'],value=value,expected_revision=1))
        self.assertEqual(self.db.connection.execute('SELECT version FROM catalog_documents WHERE asset_id=?',(self.id,)).fetchone()[0],before)
        value['name']='新版制作';Creators(self.db).update(dict(creator_id=creator['id'],value=value,expected_revision=2))
        self.assertEqual(self.find('고유제작사'),[]);self.assertEqual(self.find('新版制作'),[self.id])
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_index_failure_rolls_back_public_dictionary_write_and_original_index(self):
        value=creator_fixtures.CreatorTests.value(self);value['name']='first';creator=Creators(self.db).create({'value':value})
        Provenance(self.db).save_links(dict(subject={'kind':'asset','id':self.id},links=[dict(creator_id=creator['id'],role='creator')],expected_revision=0))
        self.db.connection.execute("CREATE TRIGGER fixture_index_failure BEFORE UPDATE ON catalog_documents BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        value['name']='second'
        with self.assertRaises(sqlite3.IntegrityError):Creators(self.db).update(dict(creator_id=creator['id'],value=value,expected_revision=1))
        self.assertEqual(self.find('first'),[self.id]);self.assertEqual(self.find('second'),[])
        self.assertEqual(Creators(self.db).creator(creator['id'])['revision'],1)

    def test_upgrade_backfills_public_index_without_rewriting_existing_search_or_ai(self):
        self.db.close();scripts=self.base/'v12';scripts.mkdir()
        for source in sorted(migration_directory().glob('*.sql'))[:12]:shutil.copyfile(source,scripts/source.name)
        self.db=Database(self.base/'legacy.sqlite',migrations=scripts)
        library=LibraryService(self.db).register({'path':str(self.source)})['library']['id'];AssetService(self.db).scan({'library_id':library});self.id=AssetService(self.db).list({})['items'][0]['id']
        AnnotationService(self.db).save(dict(asset_id=self.id,title='',description='',aliases=['이전별칭'],expected_revision=0))
        before=self.db.connection.execute('SELECT * FROM search_documents').fetchall();self.db.close();self.db=Database(self.base/'legacy.sqlite')
        self.assertEqual(before,self.db.connection.execute('SELECT * FROM search_documents').fetchall())
        self.assertEqual(self.find('이전별칭'),[self.id]);self.assertTrue(self.db.backup_path.is_file())
        self.db.connection.execute("INSERT INTO catalog_fts(catalog_fts,rank) VALUES ('integrity-check',1)")
