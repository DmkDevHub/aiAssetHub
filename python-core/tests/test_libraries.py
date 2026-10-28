import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.database import Database


class LibraryTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[2] / '.artifacts' / 'library-tests'
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / '원본 자료'
        self.original.mkdir()
        (self.original / 'fixture.txt').write_text('fixture unchanged', encoding='utf-8')
        self.database = Database(self.root / 'data' / 'asset_hub.sqlite')
        self.addCleanup(self.database.close)
        self.app = CoreApplication(self.database)

    def request(self, method, params=None):
        return self.app.handle({'request_id': str(uuid4()), 'method': method, 'params': params if params is not None else {}})

    def register(self, path=None):
        return self.request('library.register', {'path': str(path or self.original)})

    def test_register_duplicate_reenable_and_reopen_keep_the_real_id(self):
        first = self.register()
        self.assertTrue(first['ok'])
        record = first['data']['library']
        self.assertEqual(str(UUID(record['id'])), record['id'])
        self.assertEqual(record['name'], '원본 자료')
        self.assertEqual(Path(record['path']).resolve(), self.original.resolve())
        duplicate = self.register(str(self.original).swapcase() if os.name == 'nt' else self.original)
        self.assertEqual(duplicate['data']['library']['id'], record['id'])
        self.assertFalse(duplicate['data']['created'])
        self.request('library.unregister', {'library_id': record['id']})
        self.assertEqual(self.request('library.list')['data']['libraries'], [])
        self.assertEqual(self.register()['data']['library']['id'], record['id'])
        self.database.close()
        self.database = Database(self.root / 'data' / 'asset_hub.sqlite')
        self.addCleanup(self.database.close)
        self.app = CoreApplication(self.database)
        self.assertEqual(self.request('library.list')['data']['libraries'][0]['id'], record['id'])

    def test_unregister_preserves_original_assets_and_user_annotations(self):
        record = self.register()['data']['library']
        db = self.database.connection
        db.execute("INSERT INTO assets(id,library_root_id,display_name) VALUES ('fixture-asset',?,'fixture')", (record['id'],))
        db.execute("INSERT INTO asset_user_annotations VALUES ('fixture-asset','내 이름','내 설명','fixture')")
        result = self.request('library.unregister', {'library_id': record['id']})
        self.assertTrue(result['ok'])
        self.assertEqual(db.execute('SELECT enabled FROM library_roots').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 1)
        self.assertEqual(db.execute('SELECT description_override FROM asset_user_annotations').fetchone()[0], '내 설명')
        self.assertEqual((self.original / 'fixture.txt').read_text(encoding='utf-8'), 'fixture unchanged')
        self.assertTrue(self.request('library.unregister', {'library_id': record['id']})['ok'])

    def test_parent_child_overlap_is_rejected_in_both_directions(self):
        nested = self.original / 'nested'
        nested.mkdir()
        parent = self.register()['data']['library']['id']
        self.assertEqual(self.register(nested)['error']['code'], 'LIBRARY_OVERLAP')
        self.request('library.unregister', {'library_id': parent})
        child = self.register(nested)['data']['library']['id']
        self.assertEqual(self.register()['error']['code'], 'LIBRARY_OVERLAP')
        self.request('library.unregister', {'library_id': child})
        self.assertEqual(self.register()['data']['library']['id'], parent)

    def test_invalid_missing_file_network_root_and_extra_params_do_not_write(self):
        for path in ['', 'relative', str(self.root / 'missing'), str(self.original / 'fixture.txt'),
                     str(Path(self.original.anchor)), '\\\\server\\share\\fixture', 'C:\\fixture\0secret']:
            with self.subTest(path_kind=type(path).__name__):
                self.assertFalse(self.register(path)['ok'] if path else self.request('library.register', {'path': path})['ok'])
        for params in [{}, {'path': str(self.original), 'analyze': True}, {'path': 1}]:
            self.assertEqual(self.request('library.register', params)['error']['code'], 'INVALID_PARAMS')
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM library_roots').fetchone()[0], 0)

    def test_permission_and_database_errors_are_redacted(self):
        with patch('ai_asset_hub_core.libraries.os.scandir', side_effect=PermissionError('fixture-secret-path')):
            response = self.register()
        self.assertEqual(response['error']['code'], 'LIBRARY_FOLDER_UNAVAILABLE')
        self.assertNotIn('fixture-secret-path', json.dumps(response))
        broken = CoreApplication(SimpleNamespace(connection=SimpleNamespace(execute=Mock(side_effect=sqlite3.OperationalError('fixture-secret-db')))))
        response = broken.handle({'request_id': str(uuid4()), 'method': 'library.list'})
        self.assertEqual(response['error']['code'], 'DB_UNAVAILABLE')
        self.assertNotIn('fixture-secret-db', json.dumps(response))

    def test_paged_lists_stay_below_the_pipe_limit_and_return_all_rows(self):
        ids = []
        for index in range(51):
            identifier = str(uuid4())
            ids.append(identifier)
            self.database.connection.execute('INSERT INTO library_roots(id,display_name,absolute_path) VALUES (?,?,?)',
                (identifier, f'fixture-{index}', 'D:\\fixture\\' + '긴경로' * 150 + str(index)))
        cursor, found = None, []
        while True:
            response = self.request('library.list', {'after_id': cursor})
            self.assertTrue(response['ok'])
            self.assertLess(len(json.dumps(response, ensure_ascii=True).encode('ascii')) + 1, 16384)
            found.extend(record['id'] for record in response['data']['libraries'])
            cursor = response['data']['next_cursor']
            if cursor is None:
                break
        self.assertEqual(found, sorted(ids))

    def test_invalid_ids_cursors_and_absent_database_cannot_mutate(self):
        for value in ['guessed-id', 'fixture-private-secret', None]:
            self.assertEqual(self.request('library.unregister', {'library_id': value})['error']['code'], 'INVALID_PARAMS')
        self.assertEqual(self.request('library.unregister', {'library_id': str(uuid4())})['error']['code'], 'LIBRARY_NOT_FOUND')
        self.assertEqual(self.request('library.list', {'after_id': 'wrong'})['error']['code'], 'INVALID_PARAMS')
        app = CoreApplication()
        self.assertEqual(app.handle({'request_id': str(uuid4()), 'method': 'library.list'})['error']['code'], 'DB_UNAVAILABLE')

    def test_registration_and_queries_make_no_jobs_network_calls_or_asset_changes(self):
        quoted = self.root / "fixture';DROP TABLE assets;--"
        quoted.mkdir()
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch('subprocess.Popen', side_effect=AssertionError('jobs forbidden')):
            record = self.register()['data']['library']
            self.assertTrue(self.request('library.list')['ok'])
            self.assertTrue(self.request('library.unregister', {'library_id': record['id']})['ok'])
            self.assertEqual(self.register(quoted)['data']['library']['name'], quoted.name)
        for table in ['assets', 'asset_files', 'analysis_jobs', 'analysis_runs', 'analysis_results', 'asset_embeddings', 'unity_operations']:
            self.assertEqual(self.database.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        self.assertEqual(list(self.original.iterdir()), [self.original / 'fixture.txt'])


if __name__ == '__main__':
    unittest.main()
