"""Desktop-only connection information; no session secret or network authority exposed."""
import sys
from pathlib import Path


def connection(database,broker,params):
    from .libraries import LibraryError
    if params!={}:raise LibraryError('INVALID_PARAMS')
    if not database or database.health().get('status')!='ready':raise LibraryError('DB_UNAVAILABLE')
    executable=Path(sys.executable).resolve();args=[]
    if getattr(sys,'frozen',False):directory=executable.parent
    else:
        directory=Path(__file__).resolve().parents[1];packages=directory.parent/'.artifacts/core-build-venv/Lib/site-packages'
        bootstrap='import site,runpy;site.addsitedir('+repr(str(packages))+');runpy.run_module("ai_asset_hub_core",run_name="__main__")'
        args=['-B','-c',bootstrap]
    args+=['--mcp','--data-dir',str(database.path.parent)]
    return {'brokerReady':bool(broker and broker.thread.is_alive() and not broker.failed),'transport':'stdio','readOnly':True,
            'configuration':{'command':str(executable),'args':args,'cwd':str(directory)}}
