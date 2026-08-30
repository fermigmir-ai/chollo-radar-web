from __future__ import annotations

from .config import FilterConfig
from .models import Decision, Offer


def evaluate(offer: Offer, config: FilterConfig) -> Decision:
    reasons: list[str] = []
    title = offer.title.casefold()

    for term in config.excluded_terms:
        if term and term in title:
            return Decision(False, 0, (f"término excluido: {term}",))

    if offer.currency != "EUR":
        return Decision(False, 0, (f"moneda no admitida: {offer.currency}",))
    if offer.current_price < config.min_price_eur:
        return Decision(False, 0, ("precio demasiado bajo",))
    if offer.current_price > config.max_price_eur:
        return Decision(False, 0, ("precio demasiado alto",))
    if offer.discount_percent < config.min_discount_percent:
        return Decision(False, 0, ("descuento insuficiente",))
    if offer.reference_price is not None and offer.savings < config.min_savings_eur:
        return Decision(False, 0, ("ahorro absoluto insuficiente",))

    discount_points = min(55, round(offer.discount_percent * 1.8))
    score = discount_points
    reasons.append(f"-{offer.discount_percent:.0f}%")

    if offer.reference_price is not None:
        savings_points = min(15, round(offer.savings / 3))
        score += savings_points
        reasons.append(f"ahorro {offer.savings:.2f} €")

    merchant = offer.merchant.casefold()
    if "amazon" in merchant:
        score += 10
        reasons.append("vendido por Amazon")
    elif offer.is_buy_box:
        score += 6
        reasons.append("oferta destacada")

    if offer.deal_type:
        score += 10
        reasons.append("promoción activa")
    if offer.image_url:
        score += 5
    if offer.reference_price is not None and offer.reference_price > offer.current_price:
        score += 5

    score = min(100, score)
    if score < config.min_score:
        return Decision(False, score, tuple(reasons + ["puntuación insuficiente"]))
    return Decision(True, score, tuple(reasons))

