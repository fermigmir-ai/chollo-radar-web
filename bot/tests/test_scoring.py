import unittest

from chollo_radar.config import FilterConfig
from chollo_radar.models import Offer
from chollo_radar.scoring import evaluate


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.config = FilterConfig(
            min_discount_percent=15,
            min_savings_eur=5,
            min_score=55,
            min_price_eur=10,
            max_price_eur=1500,
            excluded_terms=("reacondicionado",),
        )

    def test_good_deal_is_eligible(self):
        offer = Offer(
            provider="test",
            product_id="1",
            title="Auriculares Pro",
            url="https://example.com/1",
            current_price=60,
            reference_price=100,
            discount_percent=40,
            merchant="Amazon.es",
            deal_type="DEAL",
            is_buy_box=True,
            image_url="https://example.com/image.jpg",
        )
        decision = evaluate(offer, self.config)
        self.assertTrue(decision.eligible)
        self.assertGreaterEqual(decision.score, 55)

    def test_excluded_title_is_rejected(self):
        offer = Offer(
            provider="test",
            product_id="2",
            title="Portátil reacondicionado",
            url="https://example.com/2",
            current_price=300,
            reference_price=600,
            discount_percent=50,
        )
        decision = evaluate(offer, self.config)
        self.assertFalse(decision.eligible)
        self.assertIn("término excluido", decision.reasons[0])


if __name__ == "__main__":
    unittest.main()

