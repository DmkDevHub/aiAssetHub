"""Explicit desktop data directory, environment marker and single-writer lease."""
import json
import os
from pathlib import Path

from .database import Database, DatabaseFailure


class FailedDatabase:
    def __init__(self, code):
        self.code = code

    def health(self):
        return {'status': 'error', 'error_code': self.code}

    def close(self):
        pass


class DataLease:
    def __init__(self, directory, environment):
        self.file = None
        directory = Path(directory)
        if not directory.is_absolute() or environment not in ('development', 'production') or directory.is_symlink():
            raise DatabaseFailure('DATA_PATH_INVALID')
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / '.core.lock'
        if lock_path.is_symlink():
            raise DatabaseFailure('DATA_PATH_INVALID')
        self.file = lock_path.open('a+b')
        try:
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise DatabaseFailure('DATA_IN_USE') from None
        marker = directory / '.ai-asset-hub.json'
        expected = {'application_id': 'local.aiassethub.dev', 'environment': environment, 'layout_version': 1}
        try:
            if marker.exists():
                if marker.is_symlink() or marker.stat().st_size > 1024 or json.loads(marker.read_text(encoding='utf-8')) != expected:
                    raise DatabaseFailure('DATA_ENV_MISMATCH')
            else:
                if any(path.name != '.core.lock' for path in directory.iterdir()):
                    raise DatabaseFailure('DATA_DIRECTORY_UNKNOWN')
                with marker.open('x', encoding='utf-8') as file:
                    json.dump(expected, file)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.file is not None:
            self.file.close() # OS releases the byte/file lock, even after a crash.
            self.file = None


class CoreRuntime:
    def __init__(self, directory, environment):
        self.lease = None
        self.database = None
        try:
            self.lease = DataLease(directory, environment)
            path = Path(directory) / 'asset_hub.sqlite'
            if path.is_symlink():
                raise DatabaseFailure('DATA_PATH_INVALID')
            self.database = Database(path)
        except DatabaseFailure as error:
            self.database = FailedDatabase(error.code)
        except (OSError, ValueError):
            self.database = FailedDatabase('DATA_UNAVAILABLE')

    def close(self):
        if self.database:
            self.database.close()
        if self.lease:
            self.lease.close()
