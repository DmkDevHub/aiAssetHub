from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import UUID

CORE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE_ROOT))

from ai_asset_hub_core import __version__
from ai_asset_hub_core.__main__ import main
from ai_asset_hub_core.application import CoreApplication

REQUEST_ID = "12345678-1234-4234-9234-123456789abc"


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.app = CoreApplication()

    def request(self, **changes):
        return {"request_id": REQUEST_ID, "method": "health.get", **changes}

    def test_health_measures_this_process_and_reports_database_honestly(self):
        before = datetime.now(timezone.utc)
        response = self.app.handle(self.request())
        self.assertEqual(set(response), {"request_id", "ok", "data", "error", "timestamp"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], REQUEST_ID)
        self.assertIsNone(response["error"])
        core = response["data"]["core"]
        self.assertEqual(core["pid"], os.getpid())
        self.assertEqual(core["version"], __version__)
        self.assertEqual(core["python_version"], platform.python_version())
        self.assertEqual(core["status"], "ready")
        self.assertIsInstance(core["uptime_ms"], int)
        self.assertGreaterEqual(core["uptime_ms"], 0)
        self.assertEqual(response["data"]["database"], {"status": "not_configured"})
        stamp = datetime.fromisoformat(response["timestamp"].replace("Z", "+00:00"))
        self.assertLessEqual(abs((stamp - before).total_seconds()), 1)

    def test_uptime_uses_monotonic_measurements_not_wall_clock(self):
        with patch("ai_asset_hub_core.application.time.monotonic_ns", side_effect=[5_000_000_000, 5_250_000_000, 5_500_000_000]):
            app = CoreApplication()
            self.assertEqual(app.health()["core"]["uptime_ms"], 250)
            self.assertEqual(app.health()["core"]["uptime_ms"], 500)

    def test_invalid_request_ids_are_not_echoed(self):
        for value in [None, 1, "", "fixture-secret-key-or-private-path", "!" * 36, "x" * 1000]:
            with self.subTest(value_type=type(value).__name__):
                response = self.app.handle(self.request(request_id=value))
                self.assertFalse(response["ok"])
                self.assertIsNone(response["request_id"])
                self.assertEqual(response["error"]["code"], "INVALID_REQUEST")
                self.assertIsNone(response["data"])

    def test_request_shape_and_parameters_are_strictly_validated(self):
        for request in [None, [], "fixture-secret", self.request(method=None), self.request(extra="fixture-secret")]:
            with self.subTest(request_type=type(request).__name__):
                self.assertEqual(self.app.handle(request)["error"]["code"], "INVALID_REQUEST")
        for value in [None, [], {"path": "fixture-secret"}, {"analyze": True}]:
            self.assertEqual(self.app.handle(self.request(params=value))["error"]["code"], "INVALID_PARAMS")
        self.assertTrue(self.app.handle(self.request(params={}))['ok'])

    def test_unknown_or_analysis_commands_cannot_run_health_or_start_work(self):
        with patch.object(self.app, "health", side_effect=AssertionError("must not run")):
            for method in ["analysis.start", "__dict__", "fixture-secret"]:
                response = self.app.handle(self.request(method=method))
                self.assertEqual(response["error"]["code"], "METHOD_NOT_FOUND")
                self.assertFalse(response["error"]["retryable"])
                self.assertIsNone(response["data"])
                self.assertNotIn(method, json.dumps(response))

    def test_internal_exceptions_are_redacted_without_logging(self):
        secret = "fixture-API-key-C:/private/assets.png"
        stderr = io.StringIO()
        with patch.object(self.app, "health", side_effect=RuntimeError(secret)), redirect_stderr(stderr), self.assertNoLogs():
            response = self.app.handle(self.request())
        self.assertEqual(response["request_id"], REQUEST_ID)
        self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
        self.assertTrue(response["error"]["retryable"])
        self.assertNotIn(secret, json.dumps(response))
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_module_returns_live_child_pid_and_one_response(self):
        child = subprocess.Popen(
            [sys.executable, "-B", "-m", "ai_asset_hub_core", "health.get", "--request-id", REQUEST_ID],
            cwd=CORE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            stdout, stderr = child.communicate(timeout=10)
        except BaseException:
            child.kill()
            child.communicate()
            raise
        self.assertEqual(child.returncode, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(stdout.splitlines()), 1)
        response = json.loads(stdout)
        self.assertEqual(response["data"]["core"]["pid"], child.pid)
        self.assertEqual(response["request_id"], REQUEST_ID)
        self.assertEqual(response["data"]["database"]["status"], "not_configured")

    def call_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        return code, json.loads(stdout.getvalue())

    def test_cli_generates_a_real_correlation_uuid(self):
        code, response = self.call_cli(["health.get"])
        self.assertEqual(code, 0)
        self.assertEqual(str(UUID(response["request_id"])), response["request_id"])

    def test_cli_invalid_arguments_and_commands_are_safe_failures(self):
        secret = "fixture-private-path-API-key"
        for argv in [[], ["health.get", "--unknown", secret], [secret], ["health.get", "--request-id", secret]]:
            with self.subTest(argument_count=len(argv)):
                code, response = self.call_cli(argv)
                self.assertEqual(code, 2)
                self.assertFalse(response["ok"])
                self.assertNotIn(secret, json.dumps(response))

    def test_cli_internal_failure_has_nonzero_exit_without_traceback(self):
        with patch.object(CoreApplication, "health", side_effect=RuntimeError("fixture-secret")):
            code, response = self.call_cli(["health.get"])
        self.assertEqual(code, 1)
        self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("fixture-secret", json.dumps(response))

    def test_health_under_audit_guard_performs_no_io_jobs_or_network(self):
        # Imports finish before the guard; the command itself may not read/write files,
        # open a DB, start a process, or connect/bind/listen on any socket.
        source = '''
import json
import sys
from ai_asset_hub_core.application import CoreApplication
application = CoreApplication()
def guard(event, args):
    if event == "open" or event.startswith(("socket.", "sqlite3.", "subprocess.", "os.spawn", "os.exec")) or event in {
        "os.system", "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.scandir", "os.listdir"
    }:
        raise RuntimeError("forbidden side effect")
sys.addaudithook(guard)
response = application.handle({"request_id": "12345678-1234-4234-9234-123456789abc", "method": "health.get"})
print(json.dumps(response))
raise SystemExit(0 if response["ok"] else 1)
'''
        result = subprocess.run([sys.executable, "-B", "-c", source], cwd=CORE_ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
