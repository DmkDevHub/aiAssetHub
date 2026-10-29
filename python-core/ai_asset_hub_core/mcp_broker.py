"""Bounded authenticated local read-only channel owned by the running Core."""
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import threading
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


def encode(value):
    raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()+b'\n'
    if len(raw)>MAX_FRAME:raise ValueError()
    return raw


class Broker:
    def __init__(self,database):
        self.path=database.path;self.stop_event=threading.Event();self.current=None
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.socket.listen(4);self.socket.settimeout(.05)
        self.session={'version':1,'port':self.socket.getsockname()[1],'pid':os.getpid(),'session':str(uuid4()),'token':secrets.token_hex(32)}
        try:self.discovery=session_file.publish(self.path.parent,self.session)
        except Exception:self.socket.close();raise
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def dispatch(self,database,tool,arguments,host,identifier):
        if tool=='_health' and arguments=={}:return {'status':'ready'}
        raise BrokerError('TOOL_NOT_ALLOWED')

    def run(self):
        from .database import Database
        database=None
        try:
            database=Database(self.path)
            while not self.stop_event.is_set():
                try:connection,_=self.socket.accept()
                except socket.timeout:continue
                except OSError:break
                self.current=connection
                with connection:
                    connection.settimeout(1)
                    identifier=None
                    try:
                        with connection.makefile('rb') as source:request=frame(source)
                        identifier=request.get('request_id')
                        if not valid_id(identifier):raise BrokerError('INVALID_PARAMS')
                        if not isinstance(request.get('token'),str) or not hmac.compare_digest(request['token'],self.session['token']) or request.get('session')!=self.session['session']:raise BrokerError('AUTH_DENIED')
                        if set(request)!={'token','session','request_id','host','tool','arguments'} or not isinstance(request['tool'],str) or not isinstance(request['arguments'],dict):raise BrokerError('INVALID_PARAMS')
                        data=self.dispatch(database,request['tool'],request['arguments'],request['host'],identifier)
                        result={'ok':True,'data':data}
                    except Exception as error:
                        code=str(error) if isinstance(error,BrokerError) else 'INVALID_PARAMS'
                        result={'ok':False,'error':code}
                    try:connection.sendall(encode({**result,'request_id':identifier,'session':self.session['session'],'pid':os.getpid()}))
                    except (OSError,ValueError):pass
                self.current=None
        except Exception:pass
        finally:
            if database:database.close()

    def close(self):
        self.stop_event.set();self.socket.close()
        if self.current:
            try:self.current.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(2)
        try:
            if session_file.read(self.path.parent)['session']==self.session['session']:self.discovery.unlink()
        except (OSError,ValueError,KeyError):pass


class BrokerClient:
    def __init__(self,directory):self.directory=Path(directory)

    def call(self,tool,arguments,host='mcp-host'):
        try:
            info=session_file.read(self.directory)
            if set(info)!={'version','port','pid','session','token'} or info['version']!=1 or type(info['port']) is not int or not 1024<=info['port']<=65535 or type(info['pid']) is not int or info['pid']<1 or not valid_id(info['session']) or not isinstance(info['token'],str) or len(info['token'])!=64:raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):raise BrokerError('APP_NOT_RUNNING') from None
        identifier=str(uuid4())
        try:
            with socket.create_connection(('127.0.0.1',info['port']),timeout=2) as connection:
                connection.sendall(encode({'token':info['token'],'session':info['session'],'request_id':identifier,'host':host,'tool':tool,'arguments':arguments}))
                with connection.makefile('rb') as source:result=frame(source)
            if result.get('request_id')!=identifier or result.get('session')!=info['session'] or result.get('pid')!=info['pid']:raise ValueError()
            if result.get('ok') is not True:raise BrokerError(result.get('error') if result.get('error') in ('AUTH_DENIED','INVALID_PARAMS','TOOL_NOT_ALLOWED') else 'CORE_UNAVAILABLE')
            return result['data']
        except BrokerError:raise
        except (OSError,ValueError,KeyError,TypeError):raise BrokerError('CORE_UNAVAILABLE') from None
