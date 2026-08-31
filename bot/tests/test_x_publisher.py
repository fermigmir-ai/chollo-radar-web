import json
import unittest
from unittest.mock import patch

from chollo_radar.publishers import XPublisher


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps({"data": {"id": "18990001"}}).encode("utf-8")


class XPublisherTests(unittest.TestCase):
    def setUp(self):
        self.publisher = XPublisher(
            api_key="api-key",
            api_secret="api-secret",
            access_token="access-token",
            access_token_secret="access-secret",
        )

    @patch("chollo_radar.publishers.urllib.request.urlopen")
    def test_publish_text_signs_and_posts_json(self, urlopen):
        urlopen.return_value = FakeResponse()
        result = self.publisher.publish_text("Oferta de prueba #ad")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        authorization = request.headers["Authorization"]

        self.assertEqual(request.full_url, "https://api.x.com/2/tweets")
        self.assertEqual(payload, {"text": "Oferta de prueba #ad"})
        self.assertTrue(authorization.startswith("OAuth "))
        self.assertIn("oauth_signature=", authorization)
        self.assertTrue(result.delivered)
        self.assertEqual(result.external_message_id, "18990001")

    def test_rejects_messages_over_280_characters(self):
        with self.assertRaises(ValueError):
            self.publisher.publish_text("x" * 281)


if __name__ == "__main__":
    unittest.main()
