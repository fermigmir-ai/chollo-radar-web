import unittest

from chollo_radar.models import Offer, RunSummary
from chollo_radar.storage import SupabaseRestClient, SupabaseStorage


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "POST" and path == "products":
            return [{"id": "product-uuid"}]
        if method == "GET" and path == "publications":
            return []
        if method == "GET" and path == "bot_state":
            return [{"value": "4"}]
        if method == "POST" and path == "bot_runs":
            return [{"id": 7}]
        return None


class SupabaseStorageTests(unittest.TestCase):
    def test_new_secret_key_is_not_sent_as_bearer(self):
        new_client = SupabaseRestClient("https://example.supabase.co", "sb_secret_x")
        legacy_client = SupabaseRestClient("https://example.supabase.co", "legacy-jwt")

        self.assertNotIn("Authorization", new_client._headers())
        self.assertEqual(
            legacy_client._headers()["Authorization"],
            "Bearer legacy-jwt",
        )

    def test_catalog_history_dedup_and_run_log(self):
        storage = SupabaseStorage("https://example.supabase.co", "sb_secret_x")
        fake = FakeClient()
        storage.client = fake
        offer = Offer(
            provider="amazon",
            product_id="B000TEST",
            title="Producto de prueba",
            url="https://amazon.example/B000TEST",
            current_price=49.99,
            reference_price=99.99,
            discount_percent=50,
            category="Electronics",
        )

        storage.observe(offer)
        self.assertFalse(storage.recently_published(offer.key, 168))
        storage.record_publication(offer, 90, "telegram", "mensaje", "42")
        self.assertEqual(storage.get_cursor(), 4)
        storage.set_cursor(7)
        run_id = storage.start_run("amazon", True)
        self.assertEqual(run_id, "7")
        storage.finish_run(
            run_id,
            RunSummary(3, 10, 2, 0, 1, previewed=2),
        )

        paths = [(method, path) for method, path, _ in fake.calls]
        self.assertIn(("POST", "products"), paths)
        self.assertIn(("POST", "price_observations"), paths)
        self.assertIn(("POST", "publications"), paths)
        self.assertIn(("PATCH", "bot_runs"), paths)


if __name__ == "__main__":
    unittest.main()
