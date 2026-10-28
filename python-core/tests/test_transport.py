import io
import json
import unittest

from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.transport import MAX_FRAME, serve

ID = '12345678-1234-4234-9234-123456789abc'


class TransportTests(unittest.TestCase):
    def test_multiple_requests_and_eof_keep_one_application(self):
        frame = json.dumps({'request_id': ID, 'method': 'health.get'}).encode() + b'\n'
        sink = io.BytesIO()
        self.assertEqual(serve(CoreApplication(), io.BytesIO(frame * 2), sink), 0)
        responses = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertTrue(all(response['ok'] for response in responses))
        self.assertEqual(responses[0]['data']['core']['pid'], responses[1]['data']['core']['pid'])

    def test_bad_json_utf8_duplicates_and_constants_do_not_escape(self):
        for frame in [b'{secret\n', b'\xff\n', b'{"method":"x","method":"y"}\n', b'{"x":NaN}\n']:
            sink = io.BytesIO()
            self.assertEqual(serve(CoreApplication(), io.BytesIO(frame), sink), 0)
            response = json.loads(sink.getvalue())
            self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
            self.assertNotIn(b'secret', sink.getvalue())

    def test_oversized_or_unterminated_frame_closes_transport(self):
        for frame in [b'x' * (MAX_FRAME + 1), b'{}']:
            sink = io.BytesIO()
            self.assertEqual(serve(CoreApplication(), io.BytesIO(frame), sink), 2)
            self.assertEqual(json.loads(sink.getvalue())['error']['code'], 'INVALID_REQUEST')
