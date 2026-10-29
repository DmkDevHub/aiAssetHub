"""Current-user-only discovery, containing no asset data. Never print its contents."""
import json
import os
from pathlib import Path
import stat
from uuid import uuid4


def no_links(path):
    path=Path(path)
    if not path.is_absolute():raise ValueError('SESSION_UNAVAILABLE')
    for part in (path,*path.parents):
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('SESSION_UNAVAILABLE')


def windows_acl(path,write=False):
    import ctypes as c
    from ctypes import wintypes as w
    adv=c.WinDLL('advapi32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.LocalFree.argtypes=[w.HLOCAL];kernel.LocalFree.restype=w.HLOCAL
    adv.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)]
    adv.ConvertSidToStringSidW.argtypes=[c.c_void_p,c.POINTER(w.LPWSTR)]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,c.POINTER(c.c_void_p),c.POINTER(w.DWORD)]
    adv.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p]
    adv.GetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes=[c.c_void_p,w.DWORD,w.DWORD,c.POINTER(w.LPWSTR),c.POINTER(w.DWORD)]
    token=w.HANDLE();size=w.DWORD();sid_text=w.LPWSTR()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(),8,c.byref(token)):raise OSError('SESSION_UNAVAILABLE')
    try:
        adv.GetTokenInformation(token,1,None,0,c.byref(size));buffer=c.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token,1,buffer,size,c.byref(size)):raise OSError('SESSION_UNAVAILABLE')
        sid=c.cast(buffer,c.POINTER(c.c_void_p))[0]
        if not adv.ConvertSidToStringSidW(sid,c.byref(sid_text)):raise OSError('SESSION_UNAVAILABLE')
        expected='O:'+sid_text.value+'D:P(A;;FA;;;SY)(A;;FA;;;'+sid_text.value+')'
    finally:
        if sid_text:kernel.LocalFree(c.cast(sid_text,w.HLOCAL))
        kernel.CloseHandle(token)
    if write:
        descriptor=c.c_void_p()
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(expected,1,c.byref(descriptor),None):raise OSError('SESSION_UNAVAILABLE')
        try:
            if not adv.SetFileSecurityW(str(path),0x80000004,descriptor):raise OSError('SESSION_UNAVAILABLE')
        finally:kernel.LocalFree(descriptor)
    size=w.DWORD();adv.GetFileSecurityW(str(path),5,None,0,c.byref(size));buffer=c.create_string_buffer(size.value)
    if not adv.GetFileSecurityW(str(path),5,buffer,size,c.byref(size)):raise OSError('SESSION_UNAVAILABLE')
    actual=w.LPWSTR()
    if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(buffer,1,5,c.byref(actual),None):raise OSError('SESSION_UNAVAILABLE')
    try:
        if actual.value!=expected:raise ValueError('SESSION_PERMISSIONS')
    finally:kernel.LocalFree(c.cast(actual,w.HLOCAL))


def private(path,write=False):
    no_links(path)
    if os.name=='nt':windows_acl(path,write)
    else:
        if write:os.chmod(path,0o600)
        info=Path(path).stat()
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:raise ValueError('SESSION_PERMISSIONS')


def publish(directory,value):
    directory=Path(directory);no_links(directory)
    destination=directory/'mcp-session.json';no_links(destination)
    temporary=directory/('.mcp-'+str(uuid4())+'.tmp')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        private(temporary,True)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            fd=None;json.dump(value,output);output.flush();os.fsync(output.fileno())
        os.replace(temporary,destination)
    finally:
        if fd is not None:os.close(fd)
        temporary.unlink(missing_ok=True)
    return destination


def read(directory):
    path=Path(directory)/'mcp-session.json';private(path)
    with path.open('rb') as source:raw=source.read(2049)
    if len(raw)>2048:raise ValueError('SESSION_UNAVAILABLE')
    from .transport import _unique_object
    return json.loads(raw,object_pairs_hook=_unique_object)
