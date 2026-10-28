"""Transport-independent allowlisted Core command dispatch."""

from datetime import datetime, timezone
import os
import platform
import time
from uuid import UUID

from . import __version__


class CoreApplication:
    def __init__(self, database=None):
        self._started_at = time.monotonic_ns()
        self.database = database

    def health(self):
        """Measure this live process without opening a database or starting jobs."""
        return {
            "core": {
                "status": "ready",
                "version": __version__,
                "pid": os.getpid(),
                "python_version": platform.python_version(),
                "uptime_ms": max(0, (time.monotonic_ns() - self._started_at) // 1_000_000),
            },
            "database": self.database.health() if self.database is not None else {"status": "not_configured"},
        }

    def handle(self, request):
        """Return a safe envelope. Only explicitly allowlisted methods can run."""
        request_id = None
        try:
            if not isinstance(request, dict):
                return self.error(None, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.")
            candidate = request.get("request_id")
            if not isinstance(candidate, str) or len(candidate) != 36:
                return self.error(None, "INVALID_REQUEST", "요청 ID가 올바르지 않습니다.")
            try:
                if str(UUID(candidate)) != candidate.lower():
                    raise ValueError
            except ValueError:
                return self.error(None, "INVALID_REQUEST", "요청 ID가 올바르지 않습니다.")
            request_id = candidate
            if set(request) - {"request_id", "method", "params"}:
                return self.error(request_id, "INVALID_REQUEST", "지원하지 않는 요청 필드입니다.")
            method = request.get("method")
            if not isinstance(method, str) or not method:
                return self.error(request_id, "INVALID_REQUEST", "명령 형식이 올바르지 않습니다.")
            if method not in {"health.get", "library.register", "library.unregister", "library.list"}:
                return self.error(request_id, "METHOD_NOT_FOUND", "지원하지 않는 명령입니다.")
            if method.startswith('library.'):
                from .libraries import LibraryService, LibraryError, ERROR_MESSAGES
                import sqlite3
                try:
                    service = LibraryService(self.database)
                    action = {'library.register': service.register, 'library.unregister': service.unregister,
                              'library.list': service.list}[method]
                    return self._response(request_id, data=action(request.get('params', {})))
                except LibraryError as error:
                    code = str(error) if str(error) in ERROR_MESSAGES else 'DB_UNAVAILABLE'
                    return self.error(request_id, code, ERROR_MESSAGES[code])
                except sqlite3.Error:
                    return self.error(request_id, 'DB_UNAVAILABLE', ERROR_MESSAGES['DB_UNAVAILABLE'])
            if request.get("params", {}) != {}:
                return self.error(request_id, "INVALID_PARAMS", "이 명령은 입력 매개변수를 받지 않습니다.")
            return self._response(request_id, data=self.health())
        except Exception:
            # Never expose exception messages, arguments, paths, environment, or tracebacks.
            return self.error(request_id, "INTERNAL_ERROR", "Core 상태를 확인하지 못했습니다.", retryable=True)

    @staticmethod
    def _response(request_id, *, data=None, error=None):
        return {
            "request_id": request_id,
            "ok": error is None,
            "data": data,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }

    @classmethod
    def error(cls, request_id, code, message, *, retryable=False):
        return cls._response(request_id, error={"code": code, "message": message, "retryable": retryable})
