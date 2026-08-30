import tempfile
import unittest
from pathlib import Path

from chollo_radar.models import Offer
from chollo_radar.storage import Storage


class StorageTests(unittest.TestCase):
    def test_publication_cooldown_and_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "test.db")
            try:
                self.assertFalse(storage.recently_published("amazon:X", 24))
                offer = Offer(
                    provider="amazon",
                    product_id="X",
                    title="Producto",
                    url="https://example.com/X",
                    current_price=50,
                )
                storage.record_publication(
                    offer=offer,
                    score=80,
                    channel="telegram",
                    message="oferta",
                    external_message_id="123",
                )
                self.assertTrue(storage.recently_published("amazon:X", 24))
                self.assertEqual(storage.get_cursor(), 0)
                storage.set_cursor(4)
                self.assertEqual(storage.get_cursor(), 4)
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
