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
    parser.add_argument("method", help="health.get")
    parser.add_argument("--request-id", default=None, metavar="UUID")
    application = CoreApplication()
    try:
        args = parser.parse_args(argv)
    except InvalidArguments:
        response = application.error(None, "INVALID_REQUEST", "명령 인자가 올바르지 않습니다.")
    else:
        response = application.handle({
            "request_id": args.request_id if args.request_id is not None else str(uuid4()),
            "method": args.method,
        })
    # ASCII escapes keep the wire output UTF-8 compatible even on legacy Windows consoles.
    sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
    return 0 if response["ok"] else 2 if response["error"]["code"] != "INTERNAL_ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
