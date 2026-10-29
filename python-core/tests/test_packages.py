import unittest
import copy
import json
import sqlite3
import test_annotations as fixtures
from ai_asset_hub_core.packages import Packages
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.libraries import LibraryError


class PackageTests(unittest.TestCase):
    setUp=fixtures.AnnotationTests.setUp
    tearDown=fixtures.AnnotationTests.tearDown

    def value(self,name='fixture'):
        return dict(name=name,description='설명',unit='purchase',version='1.0',purchase=dict(amount='0',currency='KRW',date='2024-02-29'))

    def test_many_packages_membership_and_snapshot_preserved_after_update_delete(self):
        import test_analysis
        service=Packages(self.db);a=service.package_create({'value':self.value('a')});b=service.package_create({'value':self.value('b')})
        test_analysis.AnalysisTests.history(self,self.id,'completed',active=True)
        active=self.db.connection.execute('SELECT * FROM asset_active_results').fetchall()
        result=service.package_assign(dict(asset_id=self.id,package_ids=[a['id'],b['id']],expected_revision=0))
        self.assertEqual(len(result['items']),2)
        snapshot=copy.deepcopy(result['items'][0]['purchaseSnapshot'])
        value=self.value('changed');value['purchase']['amount']='123.45'
        service.package_update(dict(package_id=result['items'][0]['id'],value=value,expected_revision=1))
        self.assertEqual(service.package_membership({'asset_id':self.id})['items'][0]['purchaseSnapshot'],snapshot)
        service.package_delete(dict(package_id=a['id'],expected_revision=service.package(a['id'])['revision']))
        self.assertEqual(service.package_membership({'asset_id':self.id})['ids'],[b['id']])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM package_purchase_snapshots').fetchone()[0],2)
        self.assertEqual(self.db.connection.execute('SELECT * FROM asset_active_results').fetchall(),active)
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
        self.db.close();self.db=Database(self.base/'db.sqlite')
        self.assertEqual(Packages(self.db).package_membership({'asset_id':self.id})['ids'],[b['id']])

    def test_invalid_purchase_fields_duplicate_ids_and_conflicts_are_atomic(self):
        service=Packages(self.db);package=service.package_create({'value':self.value()})
        for field,invalid in [('amount',0),('amount',-1),('amount','-1'),('amount','01'),('currency','krw'),('date','2025-02-29')]:
            value=self.value();value['purchase'][field]=invalid
            with self.assertRaises(LibraryError):service.package_update(dict(package_id=package['id'],value=value,expected_revision=1))
        self.assertEqual(service.package(package['id'])['revision'],1)
        with self.assertRaises(LibraryError):service.package_assign(dict(asset_id=self.id,package_ids=[package['id']]*2,expected_revision=0))
        service.package_assign(dict(asset_id=self.id,package_ids=[package['id']],expected_revision=0))
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.package_assign(dict(asset_id=self.id,package_ids=[],expected_revision=0))
        self.assertEqual(service.package_membership({'asset_id':self.id})['ids'],[package['id']])

    def test_snapshot_is_immutable_and_first_join_survives_unlink_relink(self):
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        first=service.package_assign(dict(asset_id=self.id,package_ids=[p['id']],expected_revision=0))['items'][0]['purchaseSnapshot']
        service.package_assign(dict(asset_id=self.id,package_ids=[],expected_revision=1))
        value=self.value();value['purchase']['amount']='50';service.package_update(dict(package_id=p['id'],value=value,expected_revision=1))
        current=service.package_assign(dict(asset_id=self.id,package_ids=[p['id']],expected_revision=2))['items'][0]['purchaseSnapshot']
        self.assertEqual(current,first)
        for sql in ('DELETE FROM package_purchase_snapshots','UPDATE package_purchase_snapshots SET record_json=\'{}\''):
            with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute(sql)

    def test_late_sql_failure_rolls_back_membership_and_snapshot_and_no_jobs(self):
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        self.db.connection.execute("CREATE TRIGGER fixture_package_fail BEFORE INSERT ON collection_history WHEN NEW.kind='package_members' BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        with self.assertRaises(sqlite3.IntegrityError):service.package_assign(dict(asset_id=self.id,package_ids=[p['id']],expected_revision=0))
        for table in ('asset_package_members','package_purchase_snapshots','analysis_jobs','asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_package_pages_and_max_membership_transport_size(self):
        service=Packages(self.db);ids=[service.package_create({'value':self.value('😀'*128)})['id'] for _ in range(16)]
        result=service.package_assign(dict(asset_id=self.id,package_ids=ids,expected_revision=0))
        self.assertLess(len(json.dumps(result,ensure_ascii=False).encode()),16000)
        cursor=None;seen=[]
        while True:
            page=service.package_list({'after_id':cursor});self.assertLessEqual(len(page['items']),2)
            seen.extend(p['id'] for p in page['items']);cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(set(seen),set(ids))
