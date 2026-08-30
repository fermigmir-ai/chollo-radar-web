from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .models import Offer, Query


class ProviderError(RuntimeError):
    pass


class OfferProvider(Protocol):
    def fetch(self, query: Query) -> list[Offer]: ...


class DemoProvider:
    """Proveedor local para probar toda la canalización sin credenciales."""

    def __init__(self, path: Path):
        self.path = path

    def fetch(self, query: Query) -> list[Offer]:
        if not self.path.exists():
            raise ProviderError(f"No existe el feed demo: {self.path}")
        items = json.loads(self.path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        offers: list[Offer] = []
        for item in items:
            category = str(item.get("category", "All"))
            if category not in {"All", query.search_index}:
                continue
            offers.append(
                Offer(
                    provider="demo",
                    product_id=str(item["product_id"]),
                    title=str(item["title"]),
                    url=str(item["url"]),
                    image_url=str(item.get("image_url", "")),
                    current_price=float(item["current_price"]),
                    reference_price=(
                        float(item["reference_price"])
                        if item.get("reference_price") is not None
                        else None
                    ),
                    discount_percent=float(item.get("discount_percent", 0)),
                    currency=str(item.get("currency", "EUR")),
                    merchant=str(item.get("merchant", "")),
                    category=category,
                    deal_type=str(item.get("deal_type", "")),
                    is_buy_box=bool(item.get("is_buy_box", False)),
                    observed_at=now,
                )
            )
        return offers


class AmazonCreatorsProvider:
    """Cliente HTTP directo para Amazon Creators API."""

    API_BASE = "https://creatorsapi.amazon/catalog/v1"
    TOKEN_ENDPOINTS = {
        "3.1": "https://api.amazon.com/auth/o2/token",
        "3.2": "https://api.amazon.co.uk/auth/o2/token",
        "3.3": "https://api.amazon.co.jp/auth/o2/token",
    }

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        credential_version: str,
        partner_tag: str,
        marketplace: str = "www.amazon.es",
        timeout: int = 20,
        request_delay_seconds: float = 1.1,
    ):
        missing = [
            name
            for name, value in {
                "AMAZON_CLIENT_ID": client_id,
                "AMAZON_CLIENT_SECRET": client_secret,
                "AMAZON_PARTNER_TAG": partner_tag,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Faltan variables: {', '.join(missing)}")
        if credential_version not in self.TOKEN_ENDPOINTS:
            raise ValueError("AMAZON_CREDENTIAL_VERSION debe ser 3.1, 3.2 o 3.3")
        self.client_id = client_id
        self.client_secret = client_secret
        self.credential_version = credential_version
        self.partner_tag = partner_tag
        self.marketplace = marketplace
        self.timeout = timeout
        self.request_delay_seconds = max(0.0, request_delay_seconds)
        self._token = ""
        self._token_expires_at = 0.0
        self._last_catalog_request = 0.0

    @classmethod
    def from_env(cls) -> "AmazonCreatorsProvider":
        return cls(
            client_id=os.getenv("AMAZON_CLIENT_ID", "").strip(),
            client_secret=os.getenv("AMAZON_CLIENT_SECRET", "").strip(),
            credential_version=os.getenv(
                "AMAZON_CREDENTIAL_VERSION", "3.2"
            ).strip(),
            partner_tag=os.getenv("AMAZON_PARTNER_TAG", "").strip(),
            marketplace=os.getenv("AMAZON_MARKETPLACE", "www.amazon.es").strip(),
            request_delay_seconds=float(
                os.getenv("AMAZON_REQUEST_DELAY_SECONDS", "1.1")
            ),
        )

    def _respect_catalog_rate(self) -> None:
        elapsed = time.monotonic() - self._last_catalog_request
        remaining = self.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _request_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        retries: int = 3,
    ) -> dict:
        body = json.dumps(payload).encode("utf-8")
        last_error = ""
        for attempt in range(retries):
            request = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {response_body[:500]}"
                if exc.code == 401 and url.startswith(self.API_BASE):
                    self._token = ""
                    self._token_expires_at = 0.0
                    break
                if exc.code not in {429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(min(delay, 15))
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
                time.sleep(min(2**attempt, 8))
        raise ProviderError(f"Error al consultar Amazon Creators API: {last_error}")

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token
        response = self._request_json(
            self.TOKEN_ENDPOINTS[self.credential_version],
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "creatorsapi::default",
            },
            {"Content-Type": "application/json"},
        )
        token = str(response.get("access_token", ""))
        if not token:
            raise ProviderError("Amazon no devolvió access_token")
        expires_in = int(response.get("expires_in", 3600))
        self._token = token
        self._token_expires_at = now + expires_in
        return token

    def fetch(self, query: Query) -> list[Offer]:
        results: list[Offer] = []
        for page in range(1, query.pages + 1):
            payload = {
                "partnerTag": self.partner_tag,
                "keywords": query.keywords,
                "searchIndex": query.search_index,
                "condition": "New",
                "itemCount": 10,
                "itemPage": page,
                "minSavingPercent": query.min_saving_percent,
                "marketplace": self.marketplace,
                "languagesOfPreference": ["es_ES"],
                "currencyOfPreference": "EUR",
                "resources": [
                    "images.primary.large",
                    "itemInfo.title",
                    "offersV2.listings.availability",
                    "offersV2.listings.condition",
                    "offersV2.listings.dealDetails",
                    "offersV2.listings.isBuyBoxWinner",
                    "offersV2.listings.merchantInfo",
                    "offersV2.listings.price",
                    "offersV2.listings.type",
                ],
            }
            response = self._catalog_request(payload)
            results.extend(self._parse_items(response, query.search_index))
        return results

    def _catalog_request(self, payload: dict) -> dict:
        last_error: Exception | None = None
        for auth_attempt in range(2):
            self._respect_catalog_rate()
            try:
                return self._request_json(
                    f"{self.API_BASE}/searchItems",
                    payload,
                    {
                        "Authorization": f"Bearer {self._access_token()}",
                        "Content-Type": "application/json",
                        "x-marketplace": self.marketplace,
                    },
                )
            except ProviderError as exc:
                last_error = exc
                if auth_attempt == 0 and "HTTP 401" in str(exc):
                    self._token = ""
                    self._token_expires_at = 0.0
                    continue
                raise
            finally:
                self._last_catalog_request = time.monotonic()
        raise ProviderError(str(last_error or "autenticación rechazada"))

    @staticmethod
    def _nested(mapping: dict, *keys, default=None):
        value = mapping
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
        return default if value is None else value

    def _parse_items(self, response: dict, category: str) -> list[Offer]:
        items = self._nested(response, "searchResult", "items", default=[])
        if not isinstance(items, list):
            return []
        now = datetime.now(timezone.utc)
        parsed: list[Offer] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            listings = self._nested(item, "offersV2", "listings", default=[])
            if not isinstance(listings, list) or not listings:
                continue
            listing = next(
                (x for x in listings if isinstance(x, dict) and x.get("isBuyBoxWinner")),
                listings[0],
            )
            if not isinstance(listing, dict):
                continue
            amount = self._nested(listing, "price", "money", "amount")
            if amount is None:
                continue
            reference = self._nested(
                listing, "price", "savingBasis", "money", "amount"
            )
            discount = self._nested(
                listing, "price", "savings", "percentage", default=0
            )
            title = self._nested(
                item, "itemInfo", "title", "displayValue", default=""
            )
            product_id = str(item.get("asin", ""))
            url = str(item.get("detailPageURL", ""))
            if not product_id or not title or not url:
                continue
            image = self._nested(
                item, "images", "primary", "large", "url", default=""
            )
            currency = self._nested(
                listing, "price", "money", "currency", default="EUR"
            )
            merchant = self._nested(
                listing, "merchantInfo", "name", default=""
            )
            parsed.append(
                Offer(
                    provider="amazon",
                    product_id=product_id,
                    title=str(title),
                    url=url,
                    image_url=str(image),
                    current_price=float(amount),
                    reference_price=float(reference) if reference is not None else None,
                    discount_percent=float(discount or 0),
                    currency=str(currency),
                    merchant=str(merchant),
                    category=category,
                    deal_type=str(listing.get("type", "")),
                    is_buy_box=bool(listing.get("isBuyBoxWinner", False)),
                    observed_at=now,
                )
            )
        return parsed
