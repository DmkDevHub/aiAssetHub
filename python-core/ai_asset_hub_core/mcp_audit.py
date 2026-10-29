"""Core-owned audit projection. Never record arguments, queries, paths, MACs or tokens."""
import hashlib
import json
import time
from uuid import uuid4
from .libraries import LibraryError,valid_id

TOOLS={'list_libraries','search_assets','get_asset','get_asset_files','get_analysis_status'}
HOSTS={'mcp','mcp-client','reference-host','AIAssetHub-MCP-Verification','Codex','Claude Code','Claude Desktop'}


def record(database,request,result,authenticated,started):
    tool=request.get('tool') if authenticated and isinstance(request,dict) else None
    if tool=='_health':return
    host=request.get('host') if authenticated and isinstance(request,dict) else None
    label=host if isinstance(host,str) and host in HOSTS else 'other-host' if authenticated else 'unauthenticated'
    fingerprint=hashlib.sha256(host.encode()).hexdigest()[:16] if isinstance(host,str) else None
    params=request.get('arguments',{}) if authenticated and isinstance(request,dict) else {}
    identifiers=[]
    if isinstance(params,dict):
        identifiers=[params.get('asset_id'),*(params.get('asset_ids',[]) if isinstance(params.get('asset_ids'),list) else [])]
    data=result.get('data',{})
    if isinstance(data,dict):
        identifiers.extend([data.get('id'),data.get('assetId')])
        identifiers.extend(i.get('id') for i in data.get('items',[]) if isinstance(i,dict))
    identifiers=list(dict.fromkeys(i for i in identifiers if valid_id(i)))[:50]
    identifier=request.get('request_id') if isinstance(request,dict) else None
    details={'requestId':identifier if valid_id(identifier) else None,'hostFingerprint':fingerprint,'targetIds':identifiers,
             'errorCode':result.get('error'),'durationMs':max(0,int((time.monotonic()-started)*1000))}
    outcome='succeeded' if result.get('ok') is True else 'denied' if result.get('error') in ('AUTH_DENIED','MCP_TOOL_NOT_ALLOWED','INVALID_PARAMS') else 'failed'
    database.connection.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
                                (str(uuid4()),'mcp:'+label,tool if tool in TOOLS else 'mcp.denied','library' if tool=='list_libraries' else 'asset',identifiers[0] if identifiers else None,outcome,json.dumps(details)))


def read(database,params):
    if not isinstance(params,dict) or set(params)-{'after_id'} or params.get('after_id') is not None and not valid_id(params['after_id']):raise LibraryError('INVALID_PARAMS')
    cursor=params.get('after_id');values=[];condition=''
    if cursor:
        row=database.connection.execute("SELECT created_at,rowid FROM audit_events WHERE id=? AND actor LIKE 'mcp:%'",(cursor,)).fetchone()
        if not row:raise LibraryError('INVALID_PARAMS')
        condition='AND (created_at<? OR (created_at=? AND rowid<?))';values=[row[0],row[0],row[1]]
    rows=database.connection.execute("SELECT id,actor,action,outcome,created_at,details_redacted_json FROM audit_events WHERE actor LIKE 'mcp:%' "+condition+' ORDER BY created_at DESC,rowid DESC LIMIT 11',values).fetchall()
    items=[]
    for row in rows[:10]:
        detail=json.loads(row[5]);targets=detail.get('targetIds',[])
        items.append({'id':row[0],'host':row[1][4:],'tool':row[2],'outcome':row[3],'createdAt':row[4],
                      'requestId':detail.get('requestId'),'hostFingerprint':detail.get('hostFingerprint'),'targetIds':targets[:5],'targetCount':len(targets),
                      'errorCode':detail.get('errorCode'),'durationMs':detail.get('durationMs')})
    return {'items':items,'next_cursor':items[-1]['id'] if len(rows)>10 else None}
