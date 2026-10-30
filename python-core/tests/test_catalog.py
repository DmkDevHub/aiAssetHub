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
