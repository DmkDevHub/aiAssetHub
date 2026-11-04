"""Read-only Unity planning contract. No Editor connection, copy, import or execution."""
import json
import re
from pathlib import Path
from .libraries import LibraryError, _local_path
from .session_file import no_links
from .annotations import AnnotationService
from .packages import Packages
from .mcp_files import McpFiles

SCHEMA='unity-planning.v1'


class UnityMetadata:
    def __init__(self,database,allowed_projects=()):
        self.database=database;self.db=database.connection
        # Only a trusted Core caller supplies this scope. Never accept it from MCP.
        self.allowed_projects=tuple(Path(p) for p in allowed_projects)

    def describe(self,asset):
        AnnotationService(self.database).require_asset(asset)
        rows=self.db.execute('''SELECT id,asset_id,package_id,value_json,revision FROM provenance_licenses WHERE enabled=1 AND
            (asset_id=? OR package_id IN (SELECT m.package_id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id AND p.enabled=1 WHERE m.asset_id=?))
            ORDER BY id LIMIT 21''',(asset,asset)).fetchall()
        if len(rows)>20:raise LibraryError('MCP_SEARCH_LIMIT')
        licenses=[]
        for identifier,owner,package,raw,revision in rows:
            value=json.loads(raw)
            licenses.append(dict(id=identifier,subjectKind='asset' if owner else 'package',subjectId=owner or package,
                revision=revision,label=value['label'],scope=value['scope'],reviewStatus=value['reviewStatus']))
        engine=Packages(self.database).package_effective({'asset_id':asset})['fields']['engine']
        return dict(schema=SCHEMA,assetId=asset,compatibility=dict(status='unknown',declaredEngine=engine,editorVerified=False),
            rights=dict(permission='unknown',reviewRequired=True,declarations=licenses,privateFieldsExcluded=True),
            project=dict(status='not-connected'),executable=False,requiresExecutionApproval=True)

    def project(self,value):
        if not isinstance(value,str) or len(value)>2048:raise LibraryError('INVALID_PARAMS')
        path=Path(value)
        # Compare before touching any caller-supplied filesystem path.
        if path not in self.allowed_projects:raise LibraryError('UNITY_PROJECT_NOT_ALLOWED')
        try:
            _local_path(path);no_links(path)
            assets=path/'Assets';version=path/'ProjectSettings'/'ProjectVersion.txt'
            no_links(assets);no_links(version)
            if not assets.is_dir() or not version.is_file() or version.stat().st_size>512:raise ValueError()
            with version.open(encoding='utf-8') as source:text=source.read(513)
            if len(text)>512:raise ValueError()
            match=re.search(r'^m_EditorVersion: ([0-9]{4}\.[0-9]+\.[0-9]+[abfp][0-9]+)\s*$',text,re.M)
            if not match:raise ValueError()
            return path,match[1]
        except (OSError,ValueError,UnicodeError):raise LibraryError('UNITY_PROJECT_UNAVAILABLE') from None

    def preview(self,params):
        if not isinstance(params,dict) or set(params)!={'asset_id','project_path'}:raise LibraryError('INVALID_PARAMS')
        metadata=self.describe(params['asset_id']);project,version=self.project(params['project_path'])
        from .mcp_queries import McpQueries
        composition=McpFiles(self.database,McpQueries.safe_path).get(params['asset_id'])
        files=[f for f in composition['files'] if set(f['roles'])&{'source','dependency'}]
        included={f['id'] for f in files};targets=[];names=set();issues={'RIGHTS_REVIEW_REQUIRED','COMPATIBILITY_UNVERIFIED'}
        destination=project/'Assets'/'AIAssetHub'
        try:
            no_links(destination)
            if destination.exists() and not destination.is_dir():raise ValueError()
        except (OSError,ValueError):raise LibraryError('UNITY_PROJECT_UNAVAILABLE') from None
        for file in files:
            item=dict(fileId=file['id'],roles=file['roles'],availability=file['availability'],targetRelativePath=None,conflicts=[])
            if file['availability']!='present':issues.add('SOURCE_UNAVAILABLE')
            if file.get('technical',{}).get('stale'):issues.add('TECHNICAL_STALE')
            if file.get('path'):
                name=Path(file['path']).name;key=name.casefold();target=destination/name
                # Never read an existing destination or follow a reparse target.
                try:
                    no_links(target);no_links(Path(str(target)+'.meta'))
                    if target.exists():item['conflicts'].append('TARGET_EXISTS')
                    if Path(str(target)+'.meta').exists():item['conflicts'].append('META_EXISTS')
                except (OSError,ValueError):item['conflicts'].append('TARGET_UNAVAILABLE')
                if key in names:item['conflicts'].append('DUPLICATE_TARGET')
                names.add(key);item['targetRelativePath']='Assets/AIAssetHub/'+name
            for dependency in file['dependencies']['items']:
                if dependency['status']!='present':issues.add('DEPENDENCY_UNRESOLVED')
                elif dependency['fileId'] not in included:issues.add('DEPENDENCY_NOT_SELECTED')
            if file['dependencies']['unresolvedDeclarationCount']:issues.add('DECLARATIONS_UNRESOLVED')
            if item['conflicts']:issues.add('TARGET_CONFLICT')
            targets.append(item)
        if metadata['compatibility']['declaredEngine']['status']=='conflict':issues.add('ENGINE_DECLARATION_CONFLICT')
        return dict(**{**metadata,'project':dict(status='filesystem-validated',path=str(project),editorVersion=version,editorConnected=False)},
            files=targets,issues=sorted(issues),planOnly=True,contentCopied=False,editorExecuted=False,modelCalled=False)
