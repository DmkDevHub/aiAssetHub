"""Bounded authenticated local read-only channel owned by the running Core."""
import hmac
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from uuid import uuid4
from . import session_file
from .libraries import valid_id
from .transport import _unique_object

MAX_FRAME=65536


class BrokerError(Exception):pass


def frame(source):
    value=source.readline(MAX_FRAME+1)
    if len(value)>MAX_FRAME or not value.endswith(b'\n'):raise ValueError()
    result=json.loads(value,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    if not isinstance(result,dict):raise ValueError()
    return result


def receive(connection):
    deadline=time.monotonic()+1.5;raw=bytearray()
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError()
        connection.settimeout(remaining);chunk=connection.recv(min(4096,MAX_FRAME+1-len(raw)))
        if not chunk:raise ValueError()
        raw.extend(chunk)
        if len(raw)>MAX_FRAME:raise ValueError()
        if b'\n' in raw:
            if raw[-1]!=10 or raw.count(10)!=1:raise ValueError()
            import io
            return frame(io.BytesIO(raw))


def signature(value,token):
    raw=json.dumps({k:v for k,v in value.items() if k!='mac'},sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    return hmac.new(token.encode(),raw,hashlib.sha256).hexdigest()


def authentic(value,token):
    return isinstance(value.get('mac'),str) and len(value['mac'])==64 and hmac.compare_digest(value['mac'],signature(value,token))


def encode(value):
    raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()+b'\n'
    if len(raw)>MAX_FRAME:raise ValueError()
    return raw


class Broker:
    def __init__(self,database,application=None):
        self.path=database.path;self.application=application;self.stop_event=threading.Event();self.current=None
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.socket.listen(4);self.socket.settimeout(.05)
        self.ready=threading.Event();self.failed=False
        self.session={'version':2,'port':self.socket.getsockname()[1],'pid':os.getpid(),'session':str(uuid4()),'token':secrets.token_hex(32)}
        try:self.discovery=session_file.publish(self.path.parent,self.session)
        except Exception:self.socket.close();raise
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
        if not self.ready.wait(2) or self.failed:self.close();raise ValueError('CORE_UNAVAILABLE')

    def dispatch(self,database,tool,arguments,host,identifier):
        if tool=='_health' and arguments=={}:return {'status':'ready'}
        from .mcp_queries import McpQueries
        from .libraries import LibraryError
        import sqlite3
        try:return McpQueries(database,self.application).dispatch(tool,arguments)
        except LibraryError as error:
            raise BrokerError(str(error) if str(error) in ('INVALID_PARAMS','MCP_TOOL_NOT_ALLOWED','MCP_ASSET_NOT_FOUND','MCP_SEARCH_LIMIT') else 'CORE_UNAVAILABLE') from None
        except sqlite3.Error:raise BrokerError('CORE_UNAVAILABLE') from None

    def run(self):
        from .database import Database
        database=None
        try:
            database=Database(self.path)
            self.ready.set()
            while not self.stop_event.is_set():
                try:connection,_=self.socket.accept()
                except socket.timeout:continue
                except OSError:break
                self.current=connection
                with connection:
                    connection.settimeout(1)
                    identifier=None;request=None;authenticated=False;started=time.monotonic()
                    try:
                        request=receive(connection)
                        identifier=request.get('request_id')
                        if not valid_id(identifier):raise BrokerError('INVALID_PARAMS')
                        if not authentic(request,self.session['token']) or request.get('session')!=self.session['session']:raise BrokerError('AUTH_DENIED')
                        authenticated=True
                        if set(request)!={'mac','session','request_id','host','tool','arguments'} or not isinstance(request['tool'],str) or len(request['tool'])>64 or not isinstance(request['host'],str) or not 1<=len(request['host'])<=64 or not isinstance(request['arguments'],dict):raise BrokerError('INVALID_PARAMS')
                        data=self.dispatch(database,request['tool'],request['arguments'],request['host'],identifier)
                        result={'ok':True,'data':data}
                    except Exception as error:
                        code=str(error) if isinstance(error,BrokerError) else 'INVALID_PARAMS'
                        result={'ok':False,'error':code}
                    try:
                        result.update(request_id=identifier,session=self.session['session'],pid=os.getpid())
                        result['mac']=signature(result,self.session['token'])
                        try:raw=encode(result)
                        except ValueError:
                            result={'ok':False,'error':'MCP_RESPONSE_LIMIT','request_id':identifier,'session':self.session['session'],'pid':os.getpid()};result['mac']=signature(result,self.session['token']);raw=encode(result)
                        from .mcp_audit import record
                        try:record(database,request,result,authenticated,started)
                        except Exception:
                            result={'ok':False,'error':'CORE_UNAVAILABLE','request_id':identifier,'session':self.session['session'],'pid':os.getpid()};result['mac']=signature(result,self.session['token']);raw=encode(result)
                        connection.sendall(raw)
                    except (OSError,ValueError):pass
                self.current=None
        except Exception:self.failed=True
        finally:
            self.ready.set()
            if database:database.close()

    def close(self):
        self.stop_event.set();self.socket.close()
        current=self.current
        if current:
            try:current.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(2)
        try:
            if session_file.read(self.path.parent)['session']==self.session['session']:self.discovery.unlink()
        except (OSError,ValueError,KeyError):pass


class BrokerClient:
    def __init__(self,directory):self.directory=Path(directory)

    def call(self,tool,arguments,host='mcp-host'):
        try:
            from .libraries import _local_path
            _local_path(self.directory)
            info=session_file.read(self.directory)
            if set(info)!={'version','port','pid','session','token'} or type(info['version']) is not int or info['version']!=2 or type(info['port']) is not int or not 1024<=info['port']<=65535 or type(info['pid']) is not int or info['pid']<1 or not valid_id(info['session']) or not isinstance(info['token'],str) or len(info['token'])!=64 or any(c not in '0123456789abcdef' for c in info['token']):raise ValueError()
        except Exception:raise BrokerError('APP_NOT_RUNNING') from None
        identifier=str(uuid4())
        try:
            with socket.create_connection(('127.0.0.1',info['port']),timeout=2) as connection:
                request={'session':info['session'],'request_id':identifier,'host':host,'tool':tool,'arguments':arguments};request['mac']=signature(request,info['token'])
                connection.sendall(encode(request));result=receive(connection)
            if not authentic(result,info['token']) or result.get('request_id')!=identifier or result.get('session')!=info['session'] or result.get('pid')!=info['pid']:raise ValueError()
            if result.get('ok') is not True:raise BrokerError(result.get('error') if result.get('error') in ('AUTH_DENIED','INVALID_PARAMS','TOOL_NOT_ALLOWED','MCP_TOOL_NOT_ALLOWED','MCP_ASSET_NOT_FOUND','MCP_SEARCH_LIMIT','MCP_RESPONSE_LIMIT') else 'CORE_UNAVAILABLE')
            return result['data']
        except BrokerError:raise
        except (OSError,ValueError,KeyError,TypeError,RecursionError):raise BrokerError('CORE_UNAVAILABLE') from None
