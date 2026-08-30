from __future__ import annotations

from .config import AppConfig
from .models import Offer, RunSummary
from .providers import OfferProvider
from .publishers import Publisher
from .scoring import evaluate
from .storage import StorageBackend


def _select_queries(config: AppConfig, storage: StorageBackend):
    total = len(config.queries)
    cursor = storage.get_cursor() % total
    count = min(config.query_batch_size, total)
    selected = tuple(config.queries[(cursor + offset) % total] for offset in range(count))
    storage.set_cursor((cursor + count) % total)
    return selected


def run_once(
    config: AppConfig,
    provider: OfferProvider,
    publisher: Publisher,
    storage: StorageBackend,
) -> RunSummary:
    queries = _select_queries(config, storage)
    errors: list[str] = []
    unique: dict[str, Offer] = {}
    fetched = 0

    for query in queries:
        try:
            offers = provider.fetch(query)
            fetched += len(offers)
            for offer in offers:
                previous = unique.get(offer.key)
                if previous is None or offer.discount_percent > previous.discount_percent:
                    unique[offer.key] = offer
        except Exception as exc:  # mantiene vivas las demás búsquedas
            errors.append(f"{query.key}: {exc}")

    ranked = []
    for offer in unique.values():
        try:
            storage.observe(offer)
        except Exception as exc:
            # Sin persistencia no se publica: así la deduplicación nunca falla abierta.
            errors.append(f"persistencia {offer.key}: {exc}")
            continue
        decision = evaluate(offer, config.filters)
        if decision.eligible:
            ranked.append((decision.score, offer))
    ranked.sort(key=lambda item: (item[0], item[1].discount_percent), reverse=True)

    published = 0
    previewed = 0
    processed = 0
    skipped_recent = 0
    eligible = len(ranked)
    for score, offer in ranked:
        if processed >= config.publishing.max_posts_per_run:
            break
        try:
            is_recent = storage.recently_published(
                offer.key, config.publishing.cooldown_hours
            )
        except Exception as exc:
            errors.append(f"deduplicación {offer.key}: {exc}")
            continue
        if is_recent:
            skipped_recent += 1
            continue
        try:
            result = publisher.publish(
                offer, score, config.publishing.disclosure
            )
        except Exception as exc:
            errors.append(f"publicación {offer.key}: {exc}")
            continue
        processed += 1
        if result.delivered:
            try:
                storage.record_publication(
                    offer=offer,
                    score=score,
                    channel=result.channel,
                    message=result.message,
                    external_message_id=result.external_message_id,
                )
            except Exception as exc:
                errors.append(f"registro publicación {offer.key}: {exc}")
            published += 1
        else:
            previewed += 1

    return RunSummary(
        queries=len(queries),
        fetched=fetched,
        eligible=eligible,
        published=published,
        skipped_recent=skipped_recent,
        previewed=previewed,
        errors=tuple(errors),
    )
