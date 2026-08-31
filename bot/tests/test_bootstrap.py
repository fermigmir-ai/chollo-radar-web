import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chollo_radar.bootstrap import (
    AUTO_INDEX_END,
    AUTO_INDEX_START,
    AUTO_SITEMAP_END,
    AUTO_SITEMAP_START,
    format_bootstrap_message,
    format_x_message,
    load_campaign,
    publish_next_article,
    publish_telegram_recommendation,
)
from chollo_radar.models import PublishResult


class FakeStorage:
    def __init__(self):
        self.products = []
        self.recent = set()
        self.publications = []

    def ensure_product(self, offer):
        self.products.append(offer.product_id)

    def recently_published(self, offer_key, cooldown_hours):
        return offer_key in self.recent

    def record_publication(
        self, offer, score, channel, message, external_message_id=""
    ):
        self.publications.append((offer, score, channel, message))


class FakePublisher:
    def publish_text(self, message, channel="telegram"):
        return PublishResult(
            channel=channel,
            delivered=True,
            external_message_id="77",
            message=message,
        )


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        campaign_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "bootstrap_campaign.json"
        )
        self.campaign = load_campaign(campaign_path)
        self.now = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)

    def _site(self, root: Path):
        (root / "articulos").mkdir()
        (root / "index.html").write_text(
            f"<main>{AUTO_INDEX_START}\n{AUTO_INDEX_END}</main>",
            encoding="utf-8",
        )
        (root / "sitemap.xml").write_text(
            f"<urlset>{AUTO_SITEMAP_START}\n{AUTO_SITEMAP_END}</urlset>",
            encoding="utf-8",
        )

    def test_message_uses_affiliate_link_without_unverified_price(self):
        message = format_bootstrap_message(
            self.campaign.products[0], self.campaign
        )
        self.assertIn("https://amzn.to/", message)
        self.assertIn("#ad", message)
        self.assertIn("Ver precio actual", message)
        self.assertNotIn("€", message)

    def test_x_message_is_short_and_uses_affiliate_link(self):
        for product in self.campaign.products:
            with self.subTest(product=product.product_id):
                message = format_x_message(product, self.campaign)
                self.assertLessEqual(len(message), 280)
                self.assertIn(product.affiliate_url, message)
                self.assertIn("#ad", message)
                self.assertIn("#CholloRadar", message)
                self.assertNotIn("€", message)

    def test_site_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._site(root)
            slug, written = publish_next_article(
                self.campaign,
                root,
                ".state.json",
                dry_run=True,
                now=self.now,
            )
            self.assertEqual(slug, self.campaign.articles[0].slug)
            self.assertFalse(written)
            self.assertFalse((root / ".state.json").exists())
            self.assertFalse((root / "articulos" / f"{slug}.html").exists())

    def test_site_publishes_in_order_and_respects_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._site(root)
            first, written = publish_next_article(
                self.campaign,
                root,
                ".state.json",
                dry_run=False,
                now=self.now,
            )
            self.assertTrue(written)
            self.assertTrue((root / "articulos" / f"{first}.html").exists())
            index = (root / "index.html").read_text(encoding="utf-8")
            sitemap = (root / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn(first, index)
            self.assertIn(first, sitemap)

            slug, written = publish_next_article(
                self.campaign,
                root,
                ".state.json",
                dry_run=False,
                now=self.now + timedelta(hours=1),
            )
            self.assertEqual(slug, "")
            self.assertFalse(written)

            second, written = publish_next_article(
                self.campaign,
                root,
                ".state.json",
                dry_run=False,
                now=self.now
                + timedelta(hours=self.campaign.article_interval_hours),
            )
            self.assertTrue(written)
            self.assertEqual(second, self.campaign.articles[1].slug)

    def test_telegram_rotation_skips_recent_products(self):
        storage = FakeStorage()
        first = self.campaign.products[0]
        storage.recent.add(f"bootstrap:{first.product_id}")
        product_id, result, skipped = publish_telegram_recommendation(
            self.campaign,
            storage,
            FakePublisher(),
            dry_run=False,
        )
        self.assertEqual(product_id, self.campaign.products[1].product_id)
        self.assertTrue(result.delivered)
        self.assertEqual(skipped, 1)
        self.assertEqual(storage.products, [first.product_id, product_id])
        self.assertEqual(len(storage.publications), 1)


if __name__ == "__main__":
    unittest.main()
