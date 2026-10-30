import json
import sqlite3
import unittest
from uuid import uuid4
import test_annotations as fixtures
import test_creators as creator_fixtures
from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.creators import Creators
from ai_asset_hub_core.packages import Packages
from ai_asset_hub_core.provenance import Provenance
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.libraries import LibraryError


class ProvenanceTests(unittest.TestCase):
    setUp = fixtures.AnnotationTests.setUp
    tearDown = fixtures.AnnotationTests.tearDown

    def creator_value(self):
        return creator_fixtures.CreatorTests.value(self)

    def subject(self):
        return {'kind': 'asset', 'id': self.id}

    def package(self):
        return Packages(self.db).package_create({'value': dict(name='fixture pack', description='', unit='purchase', version='', purchase=dict(amount='0', currency='KRW', date='2026-10-30'))})

    def call(self, method, **params):
        return CoreApplication(self.db).handle({'request_id': str(uuid4()), 'method': method, 'params': params})

    def test_shared_creator_roles_update_live_and_unlink_preserves_original_and_snapshots(self):
        creator = Creators(self.db).create({'value': self.creator_value()})
        package = self.package(); owner = {'kind': 'package', 'id': package['id']}
        Packages(self.db).package_assign(dict(asset_id=self.id, package_ids=[package['id']], expected_revision=0))
        snapshots = self.db.connection.execute('SELECT * FROM package_purchase_snapshots').fetchall()
        service = Provenance(self.db)
        links = [dict(creator_id=creator['id'], role=role) for role in ('creator', 'producer')]
        for subject in (self.subject(), owner):
            result = self.call('creator.links.save', subject=subject, links=links, expected_revision=0)
            self.assertTrue(result['ok'], result)
            self.assertEqual(len(result['data']['items']), 2)
        value = self.creator_value(); value['name'] = '수정된 공유 주체'
        Creators(self.db).update(dict(creator_id=creator['id'], value=value, expected_revision=1))
        for subject in (self.subject(), owner):
            self.assertEqual(service.links({'subject': subject})['items'][0]['name'], value['name'])
            service.save_links(dict(subject=subject, links=[], expected_revision=1))
        self.assertEqual(self.db.connection.execute('SELECT * FROM package_purchase_snapshots').fetchall(), snapshots)
        for table in ('analysis_jobs', 'asset_embeddings'):
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        self.assertEqual(Provenance(self.db).links({'subject': owner})['revision'], 2)

    def test_invalid_duplicate_disabled_links_and_stale_revision_leave_state_unchanged(self):
        service = Provenance(self.db); creator = Creators(self.db).create({'value': self.creator_value()})
        link = dict(creator_id=creator['id'], role='creator')
        service.save_links(dict(subject=self.subject(), links=[link], expected_revision=0))
        Creators(self.db).set_enabled(dict(creator_id=creator['id'], enabled=False, expected_revision=1))
        service.save_links(dict(subject=self.subject(), links=[link], expected_revision=1))
        for links in ([link, link], [dict(creator_id=str(uuid4()), role='creator')], [dict(creator_id=creator['id'], role='unknown')],
                      [dict(creator_id=creator['id'], role='distributor')]):
            with self.assertRaises(LibraryError): service.save_links(dict(subject=self.subject(), links=links, expected_revision=2))
        with self.assertRaisesRegex(LibraryError, 'METADATA_CONFLICT'):
            service.save_links(dict(subject=self.subject(), links=[], expected_revision=1))
        self.assertEqual(service.links({'subject': self.subject()})['links'], [link])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.connection.execute('INSERT INTO asset_creator_links VALUES (?,?,?)', (str(uuid4()), creator['id'], 'creator'))

    def test_history_failure_rolls_back_links_revision_and_audit(self):
        service = Provenance(self.db); creator = Creators(self.db).create({'value': self.creator_value()})
        count = self.db.connection.execute('SELECT count(*) FROM audit_events').fetchone()[0]
        self.db.connection.execute("CREATE TRIGGER fixture_history_failure BEFORE INSERT ON provenance_history BEGIN SELECT RAISE(ABORT,'secret-fixture'); END;")
        result = self.call('creator.links.save', subject=self.subject(), links=[dict(creator_id=creator['id'], role='creator')], expected_revision=0)
        self.assertEqual(result['error']['code'], 'DB_UNAVAILABLE'); self.assertNotIn('secret-fixture', json.dumps(result))
        self.assertEqual(service.links({'subject': self.subject()})['revision'], 0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM audit_events').fetchone()[0], count)

    def test_maximum_role_response_is_bounded_and_history_is_immutable(self):
        service = Provenance(self.db); links = []
        for _ in range(16):
            value = self.creator_value(); value.update(name='😀'*128, brand='😀'*128)
            creator = Creators(self.db).create({'value': value}); links.append(dict(creator_id=creator['id'], role='creator'))
        response = self.call('creator.links.save', subject=self.subject(), links=links, expected_revision=0)
        self.assertTrue(response['ok']); self.assertLess(len(json.dumps(response, ensure_ascii=False).encode()), 16384)
        self.assertNotIn('contact', json.dumps(response))
        for sql in ('DELETE FROM provenance_history', "UPDATE provenance_history SET before_json='null'"):
            with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute(sql)
