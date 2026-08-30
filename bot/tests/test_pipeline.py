import tempfile
import unittest
from pathlib import Path

from chollo_radar.config import AppConfig, FilterConfig, PublishingConfig
from chollo_radar.models import Offer, PublishResult, Query
from chollo_radar.pipeline import run_once
from chollo_radar.storage import Storage


class FakeProvider:
    def fetch(self, query):
        return [
            Offer(
                provider="fake",
                product_id="A1",
                title="Producto excelente",
                url="https://example.com/A1",
                current_price=50,
                reference_price=100,
                discount_percent=50,
                merchant="Amazon.es",
                deal_type="DEAL",
                is_buy_box=True,
                image_url="https://example.com/a.jpg",
            )
        ]


class FakePublisher:
    def __init__(self):
        self.calls = 0

    def publish(self, offer, score, disclosure):
        self.calls += 1
        return PublishResult(channel="fake", delivered=True)


class PipelineTests(unittest.TestCase):
    def test_pipeline_publishes_once_and_deduplicates(self):
        config = AppConfig(
            source="demo",
            dry_run=False,
            interval_minutes=30,
            database_path=Path("unused"),
            demo_feed_path=Path("unused"),
            query_batch_size=1,
            queries=(Query("producto", "All"),),
            filters=FilterConfig(15, 5, 55, 10, 1500, ()),
            publishing=PublishingConfig(3, 168, "aviso"),
        )
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "test.db")
            publisher = FakePublisher()
            try:
                first = run_once(config, FakeProvider(), publisher, storage)
                second = run_once(config, FakeProvider(), publisher, storage)
            finally:
                storage.close()
        self.assertEqual(first.published, 1)
        self.assertEqual(second.published, 0)
        self.assertEqual(second.skipped_recent, 1)
        self.assertEqual(publisher.calls, 1)


if __name__ == "__main__":
    unittest.main()

