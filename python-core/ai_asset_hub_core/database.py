"""The Python Core alone owns schema migrations and database writes."""
import hashlib
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from uuid import uuid4


class DatabaseFailure(Exception):
    def __init__(self, code='DB_UNAVAILABLE'):
        self.code = code
        super().__init__(code)


def migration_directory():
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'migrations'
    return Path(__file__).resolve().parents[2] / 'db' / 'migrations'


class Database:
    def __init__(self, path, migrations=None):
        self.connection = None
        self.backup_path = None
        path = Path(path)
        self.path = path
        if not path.is_absolute():
            raise DatabaseFailure('DB_PATH_INVALID')
        try:
            scripts = []
            for file in sorted(Path(migrations or migration_directory()).glob('*.sql')):
                match = re.fullmatch(r'(\d{3})_[a-z_]+\.sql', file.name)
                if not match:
                    raise DatabaseFailure('DB_MIGRATION_INVALID')
                content = file.read_text(encoding='utf-8').encode('utf-8')
                scripts.append((int(match[1]), content.decode('utf-8'), hashlib.sha256(content).hexdigest()))
            if not scripts or [version for version, _, _ in scripts] != list(range(1, len(scripts) + 1)):
                raise DatabaseFailure('DB_MIGRATION_INVALID')
            existed = path.exists() and path.stat().st_size > 0
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, timeout=3, isolation_level=None)
            self.connection.create_function('search_normalize', 1, lambda text: ' '.join(unicodedata.normalize('NFKC', text or '').casefold().split()), deterministic=True)
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA busy_timeout=3000')
            tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and 'schema_migrations' not in tables:
                raise DatabaseFailure('DB_SCHEMA_UNKNOWN')
            applied = list(self.connection.execute('SELECT version, checksum FROM schema_migrations ORDER BY version')) if tables else []
            if len(applied) > len(scripts) or any(version != scripts[index][0] or checksum != scripts[index][2]
                                                  for index, (version, checksum) in enumerate(applied)):
                raise DatabaseFailure('DB_SCHEMA_INCOMPATIBLE')
            if self.connection.execute('PRAGMA user_version').fetchone()[0] != len(applied):
                raise DatabaseFailure('DB_SCHEMA_INCOMPATIBLE')
            if len(applied) < len(scripts):
                if existed:
                    backup_dir = path.parent / 'backups'
                    backup_dir.mkdir(exist_ok=True)
                    backup_path = backup_dir / f'pre-migration-{uuid4()}.sqlite'
                    backup = sqlite3.connect(backup_path)
                    deadline = time.monotonic() + 3
                    def check_backup(status, remaining, total):
                        if time.monotonic() > deadline:
                            raise DatabaseFailure('DB_BUSY')
                    try:
                        self.connection.backup(backup, pages=128, progress=check_backup, sleep=0.05)
                    finally:
                        backup.close()
                    self.backup_path = backup_path
                self._migrate(scripts[len(applied):])
            self.connection.execute('PRAGMA journal_mode=WAL')
            if self.connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise DatabaseFailure()
        except DatabaseFailure:
            self.close()
            raise
        except (OSError, UnicodeError, sqlite3.Error):
            self.close()
            raise DatabaseFailure() from None

    def _migrate(self, scripts):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            self.connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
            for version, script, checksum in scripts:
                statement = ''
                for line in script.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        self.connection.execute(statement)
                        statement = ''
                if statement.strip():
                    raise DatabaseFailure('DB_MIGRATION_INVALID')
                self.connection.execute("INSERT INTO schema_migrations VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (version, checksum))
                self.connection.execute(f'PRAGMA user_version={version}')
            self.connection.execute('COMMIT')
        except Exception:
            self.connection.execute('ROLLBACK')
            raise

    def health(self):
        try:
            self.connection.execute('SELECT 1').fetchone()
            return {'status': 'ready', 'schema_version': self.connection.execute('PRAGMA user_version').fetchone()[0],
                    'sqlite_version': sqlite3.sqlite_version,
                    'journal_mode': self.connection.execute('PRAGMA journal_mode').fetchone()[0]}
        except (sqlite3.Error, AttributeError):
            return {'status': 'error', 'error_code': 'DB_UNAVAILABLE'}

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
