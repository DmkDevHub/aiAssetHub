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

    def test_shared_defaults_are_live_and_asset_overrides_win_without_snapshot_rewrite(self):
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        first=service.package_assign(dict(asset_id=self.id,package_ids=[p['id']],expected_revision=0))['items'][0]['purchaseSnapshot']
        service.package_defaults(dict(package_id=p['id'],value={'engine':'Unity','sourceUrl':'https://example.com/pack','licenseLabel':'Declared fixture'},expected_revision=1))
        current=service.package_effective({'asset_id':self.id})
        self.assertEqual(current['fields']['engine'],dict(value='Unity',source='package',status='inherited',packageIds=[p['id']]))
        result=service.package_override(dict(asset_id=self.id,value={'engine':'Godot','licenseLabel':None},expected_revision=0,expected_packages=current['packageVersions']))
        self.assertEqual(result['fields']['engine']['value'],'Godot')
        self.assertEqual(result['fields']['licenseLabel']['status'],'cleared')
        service.package_defaults(dict(package_id=p['id'],value={'engine':'Unreal','licenseLabel':'Changed'},expected_revision=2))
        current=service.package_effective({'asset_id':self.id})
        self.assertEqual(current['fields']['engine']['value'],'Godot')
        self.assertIsNone(current['fields']['licenseLabel']['value'])
        self.assertEqual(service.package_membership({'asset_id':self.id})['items'][0]['purchaseSnapshot'],first)
        result=service.package_override(dict(asset_id=self.id,value={},expected_revision=1,expected_packages=current['packageVersions']))
        self.assertEqual(result['fields']['engine']['value'],'Unreal')

    def test_different_package_values_conflict_identical_values_coalesce_and_management_version_wins(self):
        from ai_asset_hub_core.asset_management import AssetManagement
        service=Packages(self.db);a=service.package_create({'value':self.value('a')});b=service.package_create({'value':self.value('b')})
        service.package_defaults(dict(package_id=a['id'],value={'engine':'Unity'},expected_revision=1))
        service.package_defaults(dict(package_id=b['id'],value={'engine':'Godot'},expected_revision=1))
        service.package_assign(dict(asset_id=self.id,package_ids=[a['id'],b['id']],expected_revision=0))
        field=service.package_effective({'asset_id':self.id})['fields']['engine']
        self.assertEqual(field['status'],'conflict');self.assertIsNone(field['value'])
        service.package_defaults(dict(package_id=b['id'],value={'engine':'Unity'},expected_revision=2))
        field=service.package_effective({'asset_id':self.id})['fields']['engine']
        self.assertEqual(field['status'],'inherited');self.assertEqual(len(field['packageIds']),2)
        manager=AssetManagement(self.db);value=manager.read({'asset_id':self.id})['value'];value['assetVersion']='individual-v2'
        manager.save_management(dict(asset_id=self.id,value=value,expected_revision=0))
        self.assertEqual(service.package_effective({'asset_id':self.id})['fields']['assetVersion']['value'],'individual-v2')

    def test_shared_version_or_membership_change_rejects_stale_override_and_late_failure_rolls_back(self):
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        service.package_assign(dict(asset_id=self.id,package_ids=[p['id']],expected_revision=0))
        state=service.package_effective({'asset_id':self.id})
        params=dict(asset_id=self.id,value={'engine':'user draft'},expected_revision=0,expected_packages=state['packageVersions'])
        other=Database(self.base/'db.sqlite')
        try:Packages(other).package_defaults(dict(package_id=p['id'],value={'engine':'changed'},expected_revision=1))
        finally:other.close()
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.package_override(params)
        params['expected_packages']=service.package_effective({'asset_id':self.id})['packageVersions']
        self.db.connection.execute("CREATE TRIGGER fixture_override_failure BEFORE INSERT ON metadata_decision_history WHEN NEW.field='package_overrides' BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        with self.assertRaises(sqlite3.IntegrityError):service.package_override(params)
        self.assertEqual(service.package_effective({'asset_id':self.id})['revision'],0)
        self.db.connection.execute('DROP TRIGGER fixture_override_failure')
        service.package_override(params)
        with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):service.package_override(params)

    def test_default_validation_and_no_implicit_ai_or_network(self):
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        for value in ({'sourceUrl':'file:///private'},{'sourceUrl':'https://user:secret@example.com'},{'engine':'x'*129},{'licenseLabel':True},{'unrecognized':'value'}):
            with self.assertRaises(LibraryError):service.package_defaults(dict(package_id=p['id'],value=value,expected_revision=1))
        self.assertEqual(service.package(p['id'])['revision'],1)
        state=service.package_effective({'asset_id':self.id})
        self.assertEqual(state['fields']['engine']['status'],'unknown')
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_override_survives_rescan_reopen_and_keeps_original_bytes(self):
        from ai_asset_hub_core.assets import AssetService
        service=Packages(self.db)
        service.package_override(dict(asset_id=self.id,value={'engine':'user engine'},expected_revision=0,expected_packages=[]))
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        self.db.close();self.db=Database(self.base/'db.sqlite')
        state=Packages(self.db).package_effective({'asset_id':self.id})
        self.assertEqual(state['fields']['engine']['value'],'user engine')
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_one_package_contains_multiple_assets_and_delete_preserves_each_asset(self):
        from ai_asset_hub_core.assets import AssetService
        service=Packages(self.db);p=service.package_create({'value':self.value()})
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        (self.source/'second.wav').write_bytes(b'second original');AssetService(self.db).scan({'library_id':library})
        ids=[r[0] for r in self.db.connection.execute('SELECT id FROM assets')]
        for asset in ids:service.package_assign(dict(asset_id=asset,package_ids=[p['id']],expected_revision=0))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_package_members').fetchone()[0],2)
        service.package_delete(dict(package_id=p['id'],expected_revision=1))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM assets').fetchone()[0],2)
        for asset in ids:
            self.assertEqual(service.package_membership({'asset_id':asset})['ids'],[])
            self.assertEqual(service.package_membership({'asset_id':asset})['revision'],2)
        self.assertEqual((self.source/'second.wav').read_bytes(),b'second original')
