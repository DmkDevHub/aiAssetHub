import json
import sqlite3
import unittest
import test_annotations as fixtures
from ai_asset_hub_core.catalog_admin import CatalogAdmin
from ai_asset_hub_core.annotations import AnnotationService
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.metadata_store import MetadataStore


class CatalogAdminTests(unittest.TestCase):
    setUp=fixtures.AnnotationTests.setUp
    tearDown=fixtures.AnnotationTests.tearDown

    def test_dictionary_edits_publish_versions_and_preserve_old_assignments(self):
        service=CatalogAdmin(self.db);MetadataStore(self.db).classify(self.id,primary='A01.01',expected_revision=0,confirmed=True)
        old=service.term_get(dict(kind='type',code='A01.01'));value=old['value'];value['ko']='사용자 스프라이트'
        result=service.term_save(dict(kind='type',base_version=old['base_version'],value=value,expected_usage=old['usedAssets'],confirmed=True))
        self.assertNotEqual(result['version'],old['base_version']);self.assertEqual(service.term_get(dict(kind='type',code='A01.01'))['value']['ko'],value['ko'])
        state=MetadataStore(self.db).effective(self.id,'classification')
        self.assertEqual(state['value']['type']['version'],old['base_version'])
        self.assertNotEqual(MetadataStore(self.db).dictionary(old['base_version'],'type').contract()['version'],result['version'])
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):
            service.term_save(dict(kind='type',base_version=old['base_version'],value=value,expected_usage=old['usedAssets'],confirmed=True))

    def test_used_facet_deactivation_requires_reviewed_same_axis_replacement(self):
        service=CatalogAdmin(self.db);MetadataStore(self.db).classify(self.id,facets={'style':['style.pixel']},expected_revision=0,confirmed=True)
        old=service.term_get(dict(kind='facet',code='style.pixel'));value=old['value'];value['active']=False
        with self.assertRaises(LibraryError):service.term_save(dict(kind='facet',base_version=old['base_version'],value=value,expected_usage=1,confirmed=True))
        value['replacement']='engine.unity'
        with self.assertRaises(LibraryError):service.term_save(dict(kind='facet',base_version=old['base_version'],value=value,expected_usage=1,confirmed=True))
        value['replacement']='style.cartoon'
        service.term_save(dict(kind='facet',base_version=old['base_version'],value=value,expected_usage=1,confirmed=True))
        self.assertFalse(service.term_get(dict(kind='facet',code='style.pixel'))['value']['active'])
        self.assertTrue(self.db.connection.execute('SELECT 1 FROM asset_classification_links WHERE code=\'style.pixel\'').fetchone())

    def test_global_tag_rename_versions_all_user_refs_and_preserves_ai_history(self):
        import test_analysis
        annotation=AnnotationService(self.db);annotation.tags(dict(asset_id=self.id,add=['old'],remove=[]))
        test_analysis.AnalysisTests.history(self,self.id,'completed',active=True)
        tag=self.db.connection.execute("SELECT id FROM tags WHERE label='old'").fetchone()[0]
        result_id=self.db.connection.execute('SELECT id FROM analysis_results').fetchone()[0]
        self.db.connection.execute("INSERT INTO asset_tags VALUES (?,?,'ai',?)",(self.id,tag,result_id))
        before=self.db.connection.execute('SELECT * FROM analysis_results').fetchall();service=CatalogAdmin(self.db)
        original=service.tag_get({'tag_id':tag});self.assertFalse(original['plan']['canDelete'])
        service.tag_save(dict(tag_id=tag,value=dict(label='new',enabled=True),plan=original['plan'],confirmed=True))
        self.assertEqual(annotation.get({'asset_id':self.id})['tags'],['new'])
        self.assertEqual(annotation.get({'asset_id':self.id})['tagsRevision'],2)
        self.assertEqual(before,self.db.connection.execute('SELECT * FROM analysis_results').fetchall())
        with self.assertRaises(LibraryError):service.tag_delete(dict(plan=service.tag_get({'tag_id':tag})['plan'],confirmed=True))
        annotation.tags(dict(asset_id=self.id,add=[],remove=['new'],expected_revision=2))
        self.assertEqual(self.db.connection.execute("SELECT count(*) FROM asset_tags WHERE source='ai'").fetchone()[0],1)

    def test_disabled_tag_blocks_new_assignments_and_unused_delete_is_reviewed(self):
        service=CatalogAdmin(self.db);tag=service.tag_save(dict(tag_id=None,value=dict(label='停用',enabled=False),plan=None,confirmed=True))
        with self.assertRaises(LibraryError):AnnotationService(self.db).tags(dict(asset_id=self.id,add=['停用'],remove=[]))
        service.tag_delete(dict(plan=tag['plan'],confirmed=True))
        self.assertIsNone(self.db.connection.execute('SELECT 1 FROM tags WHERE id=?',(tag['id'],)).fetchone())
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_admin_history_failure_rolls_back_dictionary_and_tag_decisions(self):
        service=CatalogAdmin(self.db);AnnotationService(self.db).tags(dict(asset_id=self.id,add=['old'],remove=[]))
        tag=self.db.connection.execute('SELECT id FROM tags').fetchone()[0];before=service.tag_get({'tag_id':tag})
        self.db.connection.execute("CREATE TRIGGER fixture_admin_fail BEFORE INSERT ON catalog_admin_history BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        with self.assertRaises(sqlite3.IntegrityError):service.tag_save(dict(tag_id=tag,value=dict(label='new',enabled=True),plan=before['plan'],confirmed=True))
        self.assertEqual(service.tag_get({'tag_id':tag}),before)
        term=service.term_get(dict(kind='type',code='A01.01'));count=self.db.connection.execute('SELECT count(*) FROM classification_dictionaries').fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):service.term_save(dict(kind='type',base_version=term['base_version'],value=term['value'],expected_usage=0,confirmed=True))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM classification_dictionaries').fetchone()[0],count)
