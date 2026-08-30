from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Query:
    keywords: str
    search_index: str = "All"
    min_saving_percent: int = 15
    pages: int = 1

    @property
    def key(self) -> str:
        return f"{self.search_index}:{self.keywords}".casefold()


@dataclass(frozen=True)
class Offer:
    provider: str
    product_id: str
    title: str
    url: str
    current_price: float
    reference_price: float | None = None
    discount_percent: float = 0.0
    currency: str = "EUR"
    image_url: str = ""
    merchant: str = ""
    category: str = "All"
    deal_type: str = ""
    is_buy_box: bool = False
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.product_id}"

    @property
    def savings(self) -> float:
        if self.reference_price is None:
            return 0.0
        return max(0.0, self.reference_price - self.current_price)


@dataclass(frozen=True)
class Decision:
    eligible: bool
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PublishResult:
    channel: str
    delivered: bool
    external_message_id: str = ""
    message: str = ""


@dataclass(frozen=True)
class RunSummary:
    queries: int
    fetched: int
    eligible: int
    published: int
    skipped_recent: int
    previewed: int = 0
    errors: tuple[str, ...] = ()
