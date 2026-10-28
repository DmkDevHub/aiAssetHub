"""Private inherited-pipe transport. No socket, discovery file or bearer token."""
import json

MAX_FRAME = 16_384


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def serve(application, source, sink):
    while True:
        frame = source.readline(MAX_FRAME + 1)
        if not frame:
            return 0
        oversized = len(frame) > MAX_FRAME or not frame.endswith(b"\n")
        try:
            if oversized:
                raise ValueError
            request = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_object,
                                 parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
            response = application.handle(request)
        except (ValueError, UnicodeError, RecursionError):
            response = application.error(None, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.")
        sink.write((json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii"))
        sink.flush()
        if oversized:
            return 2
