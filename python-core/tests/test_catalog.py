import unittest
import test_annotations as fixtures
from ai_asset_hub_core.catalog import Catalog
from ai_asset_hub_core.packages import Packages
from ai_asset_hub_core.metadata_store import MetadataStore
from ai_asset_hub_core.libraries import LibraryError


class CatalogTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown

    def test_scope_uses_actual_memberships_types_and_preserves_original_without_jobs(self):
        service = Catalog(self.db)
        group = service.group_create({'value': dict(name='한글 그룹', description='')})
        service.group_assign(dict(asset_id=self.id, group_ids=[group['id']], expected_revision=0))
        self.assertEqual(service.scope(dict(kind='groups', id=group['id'], after_id=None))['ids'], [self.id])
        MetadataStore(self.db).classify(self.id, primary='A01.01', expected_revision=0, confirmed=True)
        self.assertEqual(service.scope(dict(kind='types', id='A01', after_id=None))['ids'], [self.id])
        self.assertEqual(service.scope(dict(kind='types', id='A02', after_id=None))['ids'], [])
        self.assertEqual(service.options(dict(kind='groups', after_id=None))['items'][0]['name'], '한글 그룹')
        self.assertEqual((self.source/'나무.png').read_bytes(), b'original')
        for table in ('analysis_jobs', 'asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)

    def test_options_are_bounded_and_unknown_scopes_rejected(self):
        service = Catalog(self.db); cursor = None; ids = []
        while True:
            page = service.options(dict(kind='types', after_id=cursor))
            self.assertLessEqual(len(page['items']), 20); ids.extend(i['id'] for i in page['items']); cursor=page['next_cursor']
            if cursor is None: break
        self.assertEqual(len(ids), len(set(ids))); self.assertIn('A14', ids)
        for params in (dict(kind='unknown', id='A01', after_id=None), dict(kind='types', id='FAKE', after_id=None)):
            with self.assertRaises(LibraryError): service.scope(params)

    def test_classification_save_preserves_versions_conflicts_and_no_inference(self):
        service=Catalog(self.db); initial=service.classification({'asset_id':self.id})
        self.assertIsNone(initial['value']['primary'])
        value=initial['value'];value.update(primary='A01.01',navigation=['A08'],facets={'style':['style.pixel']})
        result=service.save_classification(dict(asset_id=self.id,value=value,expected_revision=0,confirmed=True))
        self.assertEqual(result['revision'],1);self.assertEqual(result['source'],'user')
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):
            service.save_classification(dict(asset_id=self.id,value=value,expected_revision=0,confirmed=True))
        page=service.options(dict(kind='facets',after_id=None,version=value['facet_version']))
        self.assertTrue(page['items']);self.assertTrue(all('axis' in t for t in page['items']))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_evidence_candidates_only_registered_subject_files_without_paths(self):
        service=Catalog(self.db);page=service.evidence_candidates(dict(subject={'kind':'asset','id':self.id},after_id=None))
        self.assertEqual(len(page['items']),1);self.assertNotIn('path',page['items'][0])
        self.assertEqual(page['items'][0]['id'],self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id=?',(self.id,)).fetchone()[0])
