"""Explicit private SQLite snapshots and offline, leased restore. Never touch asset originals."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from uuid import uuid4
from .database import DatabaseFailure,migration_directory
from .libraries import LibraryError,valid_id
from .session_file import no_links,private

MAX_SIZE=1024**3


def digest(path):
    no_links(path)
    if not path.is_file() or path.stat().st_size>MAX_SIZE:raise ValueError()
    result=hashlib.sha256()
    with path.open('rb') as source:
        total=0
        while chunk:=source.read(1024*1024):
            total+=len(chunk)
            if total>MAX_SIZE:raise ValueError()
            result.update(chunk)
    return result.hexdigest()


def validate(path):
    expected=[(index+1,hashlib.sha256(p.read_text(encoding='utf-8').encode('utf-8')).hexdigest()) for index,p in enumerate(sorted(migration_directory().glob('*.sql')))]
    connection=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        connection.execute('PRAGMA trusted_schema=OFF')
        if connection.execute('PRAGMA quick_check').fetchone()!=('ok',) or connection.execute('PRAGMA foreign_key_check').fetchone():raise ValueError()
        if list(connection.execute('SELECT version,checksum FROM schema_migrations ORDER BY version'))!=expected or connection.execute('PRAGMA user_version').fetchone()[0]!=len(expected):raise ValueError()
        return len(expected)
    finally:connection.close()


def directory(root):
    path=Path(root)/'backups';no_links(path);path.mkdir(exist_ok=True);private(path,True);return path


def copy_private(source,target):
    no_links(source);no_links(target)
    with target.open('xb') as output:
        private(target,True)
        with source.open('rb') as incoming:
            total=0
            while chunk:=incoming.read(1024*1024):
                total+=len(chunk)
                if total>MAX_SIZE:raise ValueError()
                output.write(chunk)
        output.flush();os.fsync(output.fileno())


class Backups:
    def __init__(self,database):self.database=database;self.root=database.path.parent

    def create(self,params):
        if params!={'confirmed':True} or type(params.get('confirmed')) is not bool:raise LibraryError('INVALID_PARAMS')
        identifier=str(uuid4());folder=directory(self.root);path=folder/(identifier+'.sqlite');manifest=folder/(identifier+'.json')
        try:
            no_links(self.database.path)
            with path.open('xb'):private(path,True)
            snapshot=sqlite3.connect(path);deadline=time.monotonic()+1.5
            def progress(*_):
                if time.monotonic()>deadline:raise ValueError()
            try:
                self.database.connection.backup(snapshot,pages=128,progress=progress,sleep=.01)
                snapshot.execute('PRAGMA journal_mode=DELETE')
            finally:snapshot.close()
            schema=validate(path)
            value=dict(id=identifier,schemaVersion=schema,createdAt=datetime.now(timezone.utc).isoformat(),sizeBytes=path.stat().st_size,sha256=digest(path),containsPrivateMetadata=True)
            with manifest.open('x',encoding='utf-8') as output:
                private(manifest,True);json.dump(value,output);output.flush();os.fsync(output.fileno())
            return value
        except (OSError,ValueError,sqlite3.Error):
            path.unlink(missing_ok=True);manifest.unlink(missing_ok=True)
            raise LibraryError('BACKUP_FAILED') from None

    def list(self,params):
        if not isinstance(params,dict) or set(params)-{'after_id'} or params.get('after_id') is not None and not valid_id(params['after_id']):raise LibraryError('INVALID_PARAMS')
        folder=self.root/'backups';no_links(folder)
        if not folder.exists():return dict(items=[],next_cursor=None)
        identifiers=[]
        for path in folder.glob('*.json'):
            if valid_id(path.stem):identifiers.append(path.stem)
            if len(identifiers)>1000:raise LibraryError('BACKUP_LIMIT')
        identifiers.sort(reverse=True);cursor=params.get('after_id')
        if cursor is not None:
            if cursor not in identifiers:raise LibraryError('INVALID_PARAMS')
            identifiers=identifiers[identifiers.index(cursor)+1:]
        items=[]
        for identifier in identifiers[:10]:
            try:value=manifest_value(self.root,identifier);items.append({**value,'manifestValid':True})
            except LibraryError:items.append(dict(id=identifier,manifestValid=False))
        return dict(items=items,next_cursor=identifiers[9] if len(identifiers)>10 else None)

    def info(self,params):
        if params!={}:raise LibraryError('INVALID_PARAMS')
        prefix=[] if getattr(sys,'frozen',False) else ['-B','-m','ai_asset_hub_core']
        marker=json.loads((self.root/'.ai-asset-hub.json').read_text(encoding='utf-8')) if (self.root/'.ai-asset-hub.json').is_file() else None
        return dict(command=sys.executable,argsPrefix=prefix,dataDirectory=str(self.root),environment=marker['environment'] if marker else None,requiresAppClosed=True,backupContainsPrivateMetadata=True)


def manifest_value(root,identifier):
    if not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
    path=Path(root)/'backups'/(identifier+'.json')
    try:
        private(path)
        with path.open('rb') as source:raw=source.read(2049)
        if len(raw)>2048:raise ValueError()
        value=json.loads(raw)
        if set(value)!={'id','schemaVersion','createdAt','sizeBytes','sha256','containsPrivateMetadata'} or value['id']!=identifier:raise ValueError()
        import re
        if not isinstance(value['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',value['sha256']):raise ValueError()
        if type(value['sizeBytes']) is not int or not 0<value['sizeBytes']<=MAX_SIZE or type(value['schemaVersion']) is not int or not isinstance(value['createdAt'],str) or len(value['createdAt'])>40 or value['containsPrivateMetadata'] is not True:raise ValueError()
        return value
    except (OSError,ValueError,KeyError,TypeError):raise LibraryError('BACKUP_INVALID') from None


def restore(root,environment,identifier,confirmed):
    if confirmed is not True or not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
    from .runtime import DataLease
    lease=None;stage=None;moved=[]
    try:
        lease=DataLease(root,environment);root=Path(root);folder=directory(root);value=manifest_value(root,identifier);source=folder/(identifier+'.sqlite');private(source)
        if source.stat().st_size!=value['sizeBytes'] or digest(source)!=value['sha256']:raise LibraryError('BACKUP_INVALID')
        validate(source)
        stage=root/('.restore-'+str(uuid4())+'.sqlite');copy_private(source,stage)
        if digest(stage)!=value['sha256']:raise LibraryError('BACKUP_INVALID')
        validate(stage);current=root/'asset_hub.sqlite';no_links(current)
        if not current.is_file():raise LibraryError('BACKUP_INVALID')
        recovery=folder/('pre-restore-'+str(uuid4()));recovery.mkdir();private(recovery,True)
        # Preserve the exact prior DB and any crash WAL/SHM before touching the live names.
        copy_private(current,recovery/current.name)
        for suffix in ('-wal','-shm'):
            side=Path(str(current)+suffix);no_links(side)
            if side.exists():
                target=recovery/side.name;os.replace(side,target);moved.append((side,target));private(target,True)
        try:os.replace(stage,current);stage=None
        except OSError:
            for original,saved in reversed(moved):os.replace(saved,original)
            moved=[];raise
        return dict(restored=True,backupId=identifier,rollbackId=recovery.name,schemaVersion=value['schemaVersion'],analysisResumed=False)
    except DatabaseFailure:raise
    except LibraryError:raise
    except (OSError,ValueError,sqlite3.Error):raise LibraryError('BACKUP_INVALID') from None
    finally:
        # If moving a sidecar failed before DB replacement, restore any already moved names.
        if stage is not None:
            for original,saved in reversed(moved):
                if saved.exists() and not original.exists():os.replace(saved,original)
            stage.unlink(missing_ok=True)
        if lease:lease.close()
