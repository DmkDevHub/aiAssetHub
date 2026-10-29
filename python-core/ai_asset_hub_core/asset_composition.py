"""Internal catalog references, never Unity object IDs or physical file operations."""
import re
from uuid import uuid5,NAMESPACE_URL
from .libraries import valid_id
from .metadata_values import MetadataError

ROLES=('source','dependency','preview','evidence')
KINDS=('mesh','material','skeleton','animation','sprite_frame')


def membership(asset_id,file_id,role,*,known_files):
    if not valid_id(asset_id) or not valid_id(file_id) or role not in ROLES or file_id not in known_files:raise MetadataError('INVALID_FILE_REFERENCE')
    return {'assetId':asset_id,'fileId':file_id,'role':role}


def component(file_id,fingerprint,kind,locator):
    if not valid_id(file_id) or not isinstance(fingerprint,str) or not re.fullmatch('[0-9a-f]{64}',fingerprint) or kind not in KINDS or not isinstance(locator,list) or not 1<=len(locator)<=32:raise MetadataError('INVALID_COMPONENT')
    if any(not isinstance(p,str) or not 1<=len(p)<=128 or p in ('.','..') or any(ord(c)<32 or c in '/\\:' for c in p) for p in locator):raise MetadataError('INVALID_COMPONENT')
    import json
    identity=json.dumps([file_id,fingerprint,kind,locator],ensure_ascii=False,separators=(',',':'))
    return {'id':str(uuid5(NAMESPACE_URL,'ai-asset-hub/component/v1/'+identity)),'fileId':file_id,'inputFingerprint':fingerprint,'kind':kind,'locator':list(locator),'identityVersion':1}
