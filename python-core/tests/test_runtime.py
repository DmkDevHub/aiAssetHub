import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ai_asset_hub_core.runtime import CoreRuntime

CORE = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        root = CORE.parent / '.artifacts' / 'core-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def runtime(self, directory, environment='development'):
        runtime = CoreRuntime(directory, environment)
        self.addCleanup(runtime.close)
        return runtime

    def test_development_and_production_data_never_share_a_database(self):
        dev = self.runtime(self.root / 'dev')
        prod = self.runtime(self.root / 'appdata', 'production')
        self.assertEqual(dev.database.health()['status'], 'ready')
        self.assertEqual(prod.database.health()['status'], 'ready')
        dev.database.connection.execute("INSERT INTO settings VALUES ('fixture','123','fixture')")
        self.assertEqual(prod.database.connection.execute('SELECT COUNT(*) FROM settings').fetchone()[0], 0)
        dev.close()
        reused = self.runtime(self.root / 'dev', 'production')
        self.assertEqual(reused.database.health()['error_code'], 'DATA_ENV_MISMATCH')
        reopened = self.runtime(self.root / 'dev')
        self.assertEqual(reopened.database.connection.execute('SELECT value_json FROM settings').fetchone()[0], '123')

    def test_duplicate_writer_is_rejected_and_lock_released_on_close(self):
        first = self.runtime(self.root / 'data')
        second = self.runtime(self.root / 'data')
        self.assertEqual(second.database.health()['error_code'], 'DATA_IN_USE')
        first.close()
        third = self.runtime(self.root / 'data')
        self.assertEqual(third.database.health()['status'], 'ready')

    def test_unknown_directory_and_relative_path_are_not_claimed(self):
        (self.root / 'fixture-original.txt').write_text('fixture original', encoding='utf-8')
        runtime = self.runtime(self.root)
        self.assertEqual(runtime.database.health()['error_code'], 'DATA_DIRECTORY_UNKNOWN')
        self.assertEqual((self.root / 'fixture-original.txt').read_text(encoding='utf-8'), 'fixture original')
        self.assertFalse((self.root / 'asset_hub.sqlite').exists())
        self.assertEqual(self.runtime('relative-fixture').database.health()['error_code'], 'DATA_PATH_INVALID')

    def test_marker_corruption_and_corrupt_database_remain_visible(self):
        directory = self.root / 'data'
        self.runtime(directory).close()
        marker = directory / '.ai-asset-hub.json'
        expected = marker.read_text(encoding='utf-8')
        marker.write_text('{invalid fixture', encoding='utf-8')
        runtime = self.runtime(directory)
        self.assertEqual(runtime.database.health()['status'], 'error')
        runtime.close()
        marker.write_text(expected, encoding='utf-8')
        database = directory / 'asset_hub.sqlite'
        database.write_bytes(b'fixture-corrupt-db')
        runtime = self.runtime(directory)
        self.assertEqual(runtime.database.health()['status'], 'error')
        self.assertEqual(database.read_bytes(), b'fixture-corrupt-db')

    def test_real_core_restart_preserves_python_written_data(self):
        directory = self.root / 'restart'
        runtime = self.runtime(directory)
        runtime.database.connection.execute("INSERT INTO settings VALUES ('fixture','456','fixture')")
        runtime.close()
        for _ in range(2):
            result = subprocess.run([sys.executable, '-B', '-m', 'ai_asset_hub_core', 'health.get',
                '--data-dir', str(directory), '--environment', 'development'], cwd=CORE,
                capture_output=True, text=True, encoding='utf-8', timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['data']['database']['status'], 'ready')
        reopened = self.runtime(directory)
        self.assertEqual(reopened.database.connection.execute('SELECT value_json FROM settings').fetchone()[0], '456')

    def test_killed_core_releases_lease_without_resuming_or_creating_analysis(self):
        directory = self.root / 'crash'
        runtime = self.runtime(directory)
        runtime.database.connection.execute("INSERT INTO settings VALUES ('fixture','789','fixture')")
        runtime.close()
        child = subprocess.Popen([sys.executable, '-B', '-m', 'ai_asset_hub_core', '--serve',
            '--data-dir', str(directory), '--environment', 'development'], cwd=CORE,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            child.stdin.write(json.dumps({'request_id': '12345678-1234-4234-9234-123456789abc', 'method': 'health.get'}) + '\n')
            child.stdin.flush()
            response = json.loads(child.stdout.readline())
            self.assertEqual(response['data']['database']['status'], 'ready')
            self.assertEqual(self.runtime(directory).database.health()['error_code'], 'DATA_IN_USE')
        finally:
            child.kill()
            child.communicate(timeout=10)
        reopened = self.runtime(directory)
        self.assertEqual(reopened.database.health()['status'], 'ready')
        self.assertEqual(reopened.database.connection.execute('SELECT value_json FROM settings').fetchone()[0], '789')
        self.assertEqual(reopened.database.connection.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0], 0)
