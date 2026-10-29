"""One-shot developer probe. This is not the Tauri IPC or MCP transport."""

import argparse
import json
import sys
from uuid import uuid4

from .application import CoreApplication


class InvalidArguments(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error includes user input, so discard it.
        raise InvalidArguments


def main(argv=None):
    parser = SafeArgumentParser(prog="ai_asset_hub_core", description="Read-only Core health probe")
    parser.add_argument("method", nargs="?", help="health.get")
    parser.add_argument("--serve", action="store_true", help="Private desktop pipe server")
    parser.add_argument("--mcp", action="store_true", help="Read-only MCP stdio Bridge; never opens the database")
    parser.add_argument("--request-id", default=None, metavar="UUID")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--environment", choices=['development', 'production'], default=None)
    application = CoreApplication()
    try:
        args = parser.parse_args(argv)
    except InvalidArguments:
        response = application.error(None, "INVALID_REQUEST", "명령 인자가 올바르지 않습니다.")
    else:
        if args.mcp:
            if args.serve or args.method or args.request_id or args.environment:return 2
            from .mcp_bridge import run_bridge
            return run_bridge(args.data_dir)
        if bool(args.data_dir) != bool(args.environment):
            response = application.error(None, "INVALID_REQUEST", "데이터 실행 환경을 지정해야 합니다.")
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + '\n')
            return 2
        runtime = None
        if args.data_dir:
            from .runtime import CoreRuntime
            runtime = CoreRuntime(args.data_dir, args.environment)
            application.database = runtime.database
        if args.serve and args.method is None and args.request_id is None:
            from .transport import serve
            broker=None
            try:
                if runtime and runtime.database.health().get('status')=='ready':
                    from .mcp_broker import Broker
                    broker=Broker(runtime.database,application)
                return serve(application, sys.stdin.buffer, sys.stdout.buffer)
            except (BrokenPipeError, OSError):
                return 1
            finally:
                if broker:broker.close()
                application.close()
                if runtime:
                    runtime.close()
        response = application.handle({
            "request_id": args.request_id if args.request_id is not None else str(uuid4()),
            "method": args.method if not args.serve else None,
        })
        if runtime:
            runtime.close()
    # ASCII escapes keep the wire output UTF-8 compatible even on legacy Windows consoles.
    sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
    return 0 if response["ok"] else 2 if response["error"]["code"] != "INTERNAL_ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
