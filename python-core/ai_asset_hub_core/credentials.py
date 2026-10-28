"""Windows user vault; secrets never enter SQLite or result envelopes."""
import ctypes
from ctypes import wintypes
import hashlib
import os


class Credential(ctypes.Structure):
    _fields_=[('Flags',wintypes.DWORD),('Type',wintypes.DWORD),('TargetName',wintypes.LPWSTR),
              ('Comment',wintypes.LPWSTR),('LastWritten',wintypes.FILETIME),('CredentialBlobSize',wintypes.DWORD),
              ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
              ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
              ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]


class Vault:
    def __init__(self, database_path):
        self.scope=hashlib.sha256(str(database_path.resolve()).encode('utf-8')).hexdigest()

    def target(self, identifier):
        return 'AIAssetHub:'+self.scope+':'+identifier

    def api(self):
        if os.name!='nt':raise OSError()
        api=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
        api.CredWriteW.argtypes=[ctypes.POINTER(Credential),wintypes.DWORD];api.CredWriteW.restype=wintypes.BOOL
        api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))];api.CredReadW.restype=wintypes.BOOL
        api.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD];api.CredDeleteW.restype=wintypes.BOOL
        api.CredFree.argtypes=[ctypes.c_void_p];api.CredFree.restype=None
        return api

    def read(self, identifier):
        api=self.api();pointer=ctypes.POINTER(Credential)()
        if not api.CredReadW(self.target(identifier),1,0,ctypes.byref(pointer)):
            if ctypes.get_last_error()==1168:return None
            raise OSError()
        try:
            return ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode('utf-8')
        finally:api.CredFree(pointer)

    def write(self, identifier, key):
        api=self.api();raw=key.encode('utf-8');buffer=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
        credential=Credential();credential.Type=1;credential.TargetName=self.target(identifier)
        credential.CredentialBlobSize=len(raw);credential.CredentialBlob=buffer;credential.Persist=2
        credential.UserName='AI Asset Hub'
        if not api.CredWriteW(ctypes.byref(credential),0):raise OSError()

    def delete(self, identifier):
        api=self.api()
        if not api.CredDeleteW(self.target(identifier),1,0) and ctypes.get_last_error()!=1168:raise OSError()
