from uuid import uuid4
import unittest
import test_annotations
from ai_asset_hub_core.search import SearchService
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryService, LibraryError


class SearchTests(unittest.TestCase):
    setUp = test_annotations.AnnotationTests.setUp
    tearDown = test_annotations.AnnotationTests.tearDown
    def find(self, query):
        return SearchService(self.db).search({'query':query})['ids']

    def test_fts_and_korean_substrings_sync_without_analysis(self):
        self.service.tags({'asset_id':self.id,'add':['푸른숲','Forest'],'remove':[]})
        self.service.save({'asset_id':self.id,'title':'고목','description':'산속의 아름다운 나무 texture'})
        for query in ('나무','푸른','숲','  FOREST   나무 ','아름다','text'):
            self.assertEqual(self.find(query),[self.id],query)
        self.assertTrue(self.db.connection.execute("SELECT rowid FROM asset_fts WHERE asset_fts MATCH ?",('"forest"',)).fetchall())
        self.service.tags({'asset_id':self.id,'add':[],'remove':['푸른숲']})
        self.assertEqual(self.find('푸른'),[])
        self.service.save({'asset_id':self.id,'title':'','description':''})
        self.assertEqual(self.find('아름다'),[])
        for query in ('" OR *', '"', '%', '_', '없는 단어'):
            self.assertEqual(self.find(query),[])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_search_pagination_and_disabled_roots(self):
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        for _ in range(205):
            self.db.connection.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)',(str(uuid4()),library,'pagination'))
        service=SearchService(self.db)
        first=service.search({'query':'pagination'})
        second=service.search({'query':'pagination','after_id':first['next_cursor']})
        self.assertEqual((len(first['ids']),len(second['ids'])),(200,5))
        self.assertFalse(set(first['ids']) & set(second['ids']))
        LibraryService(self.db).unregister({'library_id':library})
        self.assertEqual(self.find('pagination'),[])
        with self.assertRaises(LibraryError): service.search({'query':'x'*257})

    def test_rescan_and_reopen_keep_index_consistent(self):
        from ai_asset_hub_core.database import Database
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        (self.source/'한글 신규.txt').write_text('fixture')
        AssetService(self.db).scan({'library_id':library})
        self.assertEqual(len(self.find('한글')),1)
        self.db.close(); self.db=Database(self.base/'db.sqlite')
        self.assertEqual(len(self.find('한글')),1)
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")

    def test_v1_upgrade_backfills_existing_metadata_and_makes_backup(self):
        import shutil
        from ai_asset_hub_core.database import Database, migration_directory
        old=self.base/'old-migrations'; old.mkdir()
        shutil.copy(migration_directory()/'001_initial.sql',old/'001_initial.sql')
        path=self.base/'old.sqlite'; database=Database(path,migrations=old)
        library=LibraryService(database).register({'path':str(self.source)})['library']['id']
        AssetService(database).scan({'library_id':library})
        identifier=AssetService(database).list({})['items'][0]['id']
        # Seed historical v1 rows directly; the current service requires v4.
        database.connection.execute('INSERT INTO asset_user_annotations VALUES (?,?,?,?)',(identifier,'이전 별칭','마이그레이션 보존','fixture'))
        database.connection.execute("INSERT INTO search_documents VALUES (?,'stale v1 index',1,'fixture')",(identifier,))
        database.close(); database=Database(path)
        try:
            self.assertEqual(database.health()['schema_version'],len(list(migration_directory().glob('*.sql'))))
            self.assertTrue(database.backup_path.is_file())
            self.assertEqual(SearchService(database).search({'query':'마이그레이션'})['ids'],[identifier])
            database.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")
        finally: database.close()

    def test_active_ai_description_tags_and_failed_retry_are_searchable_without_calls(self):
        import test_analysis
        from unittest.mock import patch
        test_analysis.AnalysisTests.history(self,self.id,'completed',True)
        result=self.db.connection.execute('SELECT id FROM analysis_results').fetchone()[0]
        tag=str(uuid4());self.db.connection.execute('INSERT INTO tags VALUES (?,?,?)',(tag,'중세 횃불','중세 횃불'))
        self.db.connection.execute("INSERT INTO asset_tags VALUES (?,?,'ai',?)",(self.id,tag,result))
        test_analysis.AnalysisTests.history(self,self.id,'failed',timestamp='2030-01-01')
        with patch('ai_asset_hub_core.providers.metadata',side_effect=AssertionError('no model calls')):
            self.assertEqual(self.find('successful'),[self.id]);self.assertEqual(self.find('중세 횃불'),[self.id])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_runs').fetchone()[0],2)
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")
