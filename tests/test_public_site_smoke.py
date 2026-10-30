import importlib.util
import http.client
import io
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import Mock


PATH = Path(__file__).resolve().parents[1] / "scripts" / "public-site-smoke.py"
spec = importlib.util.spec_from_file_location("public_site_smoke", PATH)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def response(status=200, body=smoke.MARKER, url=smoke.URL, headers=None):
    result = Mock()
    result.getcode.return_value = status
    result.geturl.return_value = url
    result.read.return_value = body
    result.headers = headers or {}
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


class PublicSiteSmokeTests(unittest.TestCase):
    def test_success(self):
        self.assertIsNone(smoke.check_response(response()))
        self.assertIsNone(smoke.check_response(response(
            headers={"Content-Length": str(len(smoke.MARKER))},
        )))

    def test_truncated_response_and_invalid_lengths_fail_closed(self):
        for length in (str(len(smoke.MARKER) + 5), "-1", "invalid", "9" * 100):
            with self.subTest(length=length):
                self.assertIsNotNone(smoke.check_response(response(
                    headers={"Content-Length": length},
                )))

    def test_status_canonical_identity_marker_and_size_fail_closed(self):
        for item in (
            response(status=503),
            response(url="https://other.example/"),
            response(body=b"not the product"),
            response(body=smoke.MARKER + b"x" * smoke.MAX_BODY_BYTES),
        ):
            with self.subTest(item=item):
                self.assertIsNotNone(smoke.check_response(item))

    def test_http_error_reports_code_without_response_details(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            smoke.URL, 403, "private reason", {}, io.BytesIO(b"private body"),
        )
        messages = []
        self.assertFalse(smoke.probe(opener, attempts=1, report=messages.append))
        self.assertIn("got 403", messages[0])
        self.assertNotIn("private", messages[0])

    def test_transient_failure_recovers_with_bounded_retry(self):
        opener = Mock()
        opener.open.side_effect = [TimeoutError(), response()]
        sleep = Mock()
        self.assertTrue(smoke.probe(opener, sleep=sleep, report=Mock()))
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_persistent_failure_exhausts_retries(self):
        opener = Mock()
        opener.open.side_effect = OSError("private transport details")
        sleep = Mock()
        messages = []
        self.assertFalse(smoke.probe(opener, sleep=sleep, report=messages.append))
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertNotIn("private", " ".join(messages))

    def test_interrupted_response_is_retried_without_printing_partial_body(self):
        broken = response()
        broken.read.side_effect = http.client.IncompleteRead(b"private partial body", 12)
        opener = Mock()
        opener.open.side_effect = [broken, response()]
        messages = []
        self.assertTrue(smoke.probe(opener, sleep=Mock(), report=messages.append))
        self.assertIn("IncompleteRead", messages[0])
        self.assertNotIn("private", " ".join(messages))

    def test_http_rejection_remains_a_failure_after_all_attempts(self):
        opener = Mock()
        opener.open.side_effect = [
            urllib.error.HTTPError(smoke.URL, 403, "private reason", {},
                                   io.BytesIO(b"private body"))
            for _ in range(3)
        ]
        messages = []
        self.assertFalse(smoke.probe(opener, sleep=Mock(), report=messages.append))
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(all("got 403" in message for message in messages))
        self.assertNotIn("private", " ".join(messages))

    def test_redirects_are_not_followed(self):
        self.assertIsNone(smoke.NoRedirectHandler().redirect_request(
            None, None, 302, "Found", {}, "https://other.example/",
        ))


if __name__ == "__main__":
    unittest.main()
