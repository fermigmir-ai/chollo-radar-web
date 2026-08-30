from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import Query


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "si", "sí", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} debe ser true o false")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga un .env sencillo sin ejecutar contenido como código de shell."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class FilterConfig:
    min_discount_percent: float
    min_savings_eur: float
    min_score: int
    min_price_eur: float
    max_price_eur: float
    excluded_terms: tuple[str, ...]


@dataclass(frozen=True)
class PublishingConfig:
    max_posts_per_run: int
    cooldown_hours: int
    disclosure: str


@dataclass(frozen=True)
class AppConfig:
    source: str
    dry_run: bool
    interval_minutes: int
    database_path: Path
    demo_feed_path: Path
    query_batch_size: int
    queries: tuple[Query, ...]
    filters: FilterConfig
    publishing: PublishingConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"No existe {config_path}. Copia config.example.json como config.json."
        )
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    queries = tuple(
        Query(
            keywords=str(item["keywords"]).strip(),
            search_index=str(item.get("search_index", "All")).strip(),
            min_saving_percent=int(item.get("min_saving_percent", 15)),
            pages=max(1, min(10, int(item.get("pages", 1)))),
        )
        for item in raw.get("queries", [])
    )
    if not queries:
        raise ValueError("config.json debe contener al menos una búsqueda")

    filters_raw = raw.get("filters", {})
    publishing_raw = raw.get("publishing", {})
    filters = FilterConfig(
        min_discount_percent=float(filters_raw.get("min_discount_percent", 15)),
        min_savings_eur=float(filters_raw.get("min_savings_eur", 5)),
        min_score=int(filters_raw.get("min_score", 55)),
        min_price_eur=float(filters_raw.get("min_price_eur", 10)),
        max_price_eur=float(filters_raw.get("max_price_eur", 1500)),
        excluded_terms=tuple(
            str(term).casefold() for term in filters_raw.get("excluded_terms", [])
        ),
    )
    publishing = PublishingConfig(
        max_posts_per_run=max(1, int(publishing_raw.get("max_posts_per_run", 3))),
        cooldown_hours=max(1, int(publishing_raw.get("cooldown_hours", 168))),
        disclosure=str(
            publishing_raw.get(
                "disclosure",
                "Enlace de afiliado: podemos recibir una comisión sin coste extra para ti.",
            )
        ).strip(),
    )

    source = os.getenv("BOT_SOURCE", "demo").strip().casefold()
    if source not in {"demo", "amazon"}:
        raise ValueError("BOT_SOURCE debe ser demo o amazon")
    interval = _env_int("INTERVAL_MINUTES", 30)
    if interval < 5:
        raise ValueError("INTERVAL_MINUTES debe ser al menos 5")

    return AppConfig(
        source=source,
        dry_run=_env_bool("DRY_RUN", True),
        interval_minutes=interval,
        database_path=Path(os.getenv("DATABASE_PATH", "runtime/chollo_radar.db")),
        demo_feed_path=Path(os.getenv("DEMO_FEED_PATH", "data/demo_offers.json")),
        query_batch_size=max(1, int(raw.get("query_batch_size", 3))),
        queries=queries,
        filters=filters,
        publishing=publishing,
    )

