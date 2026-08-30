import unittest

from chollo_radar.providers import AmazonCreatorsProvider


class AmazonProviderTests(unittest.TestCase):
    def test_parse_search_items_response(self):
        provider = AmazonCreatorsProvider(
            client_id="id",
            client_secret="secret",
            credential_version="3.2",
            partner_tag="tag-21",
            request_delay_seconds=0,
        )
        response = {
            "searchResult": {
                "items": [
                    {
                        "asin": "B000TEST",
                        "detailPageURL": "https://www.amazon.es/dp/B000TEST?tag=tag-21",
                        "images": {
                            "primary": {
                                "large": {"url": "https://example.com/image.jpg"}
                            }
                        },
                        "itemInfo": {
                            "title": {"displayValue": "Producto de prueba"}
                        },
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "merchantInfo": {"name": "Amazon.es"},
                                    "type": "LIGHTNING_DEAL",
                                    "price": {
                                        "money": {
                                            "amount": 79.99,
                                            "currency": "EUR",
                                        },
                                        "savingBasis": {
                                            "money": {"amount": 119.99}
                                        },
                                        "savings": {"percentage": 33},
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        }
        offers = provider._parse_items(response, "Electronics")
        self.assertEqual(len(offers), 1)
        offer = offers[0]
        self.assertEqual(offer.product_id, "B000TEST")
        self.assertEqual(offer.current_price, 79.99)
        self.assertEqual(offer.reference_price, 119.99)
        self.assertEqual(offer.discount_percent, 33)
        self.assertTrue(offer.is_buy_box)


if __name__ == "__main__":
    unittest.main()
