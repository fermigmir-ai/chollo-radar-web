from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Offer, PublishResult
from .storage import StorageBackend


AUTO_INDEX_START = "<!-- CHOLLO_RADAR_AUTO_ARTICLES_START -->"
AUTO_INDEX_END = "<!-- CHOLLO_RADAR_AUTO_ARTICLES_END -->"
AUTO_SITEMAP_START = "<!-- CHOLLO_RADAR_AUTO_SITEMAP_START -->"
AUTO_SITEMAP_END = "<!-- CHOLLO_RADAR_AUTO_SITEMAP_END -->"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BootstrapProduct:
    product_id: str
    title: str
    affiliate_url: str
    image_url: str
    image_source_url: str
    category: str
    best_for: str
    summary: str
    specs: tuple[str, ...]
    pros: tuple[str, ...]
    considerations: tuple[str, ...]
    guide_path: str

    def as_offer(self) -> Offer:
        return Offer(
            provider="bootstrap",
            product_id=self.product_id,
            title=self.title,
            url=self.affiliate_url,
            current_price=0,
            image_url=self.image_url,
            merchant="Amazon.es",
            category=self.category,
        )


@dataclass(frozen=True)
class BootstrapArticle:
    slug: str
    title: str
    description: str
    kicker: str
    lead: str
    product_ids: tuple[str, ...]
    introduction: tuple[str, ...]
    checklist: tuple[str, ...]
    verdict: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapCampaign:
    site_base_url: str
    disclosure: str
    article_interval_hours: int
    telegram_cooldown_hours: int
    products: tuple[BootstrapProduct, ...]
    articles: tuple[BootstrapArticle, ...]

    @property
    def product_map(self) -> dict[str, BootstrapProduct]:
        return {product.product_id: product for product in self.products}


@dataclass(frozen=True)
class BootstrapResult:
    article_slug: str = ""
    article_written: bool = False
    telegram_product_id: str = ""
    telegram_result: PublishResult | None = None
    skipped_recent: int = 0


def load_campaign(path: str | Path) -> BootstrapCampaign:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    products = tuple(
        BootstrapProduct(
            product_id=str(item["id"]).strip(),
            title=str(item["title"]).strip(),
            affiliate_url=str(item["affiliate_url"]).strip(),
            image_url=str(item.get("image_url", "")).strip(),
            image_source_url=str(item.get("image_source_url", "")).strip(),
            category=str(item.get("category", "Selección")).strip(),
            best_for=str(item["best_for"]).strip(),
            summary=str(item["summary"]).strip(),
            specs=tuple(str(value).strip() for value in item.get("specs", [])),
            pros=tuple(str(value).strip() for value in item.get("pros", [])),
            considerations=tuple(
                str(value).strip() for value in item.get("considerations", [])
            ),
            guide_path=str(item.get("guide_path", "")).strip(),
        )
        for item in raw["products"]
    )
    articles = tuple(
        BootstrapArticle(
            slug=str(item["slug"]).strip(),
            title=str(item["title"]).strip(),
            description=str(item["description"]).strip(),
            kicker=str(item.get("kicker", "Guía de compra")).strip(),
            lead=str(item["lead"]).strip(),
            product_ids=tuple(str(value).strip() for value in item["product_ids"]),
            introduction=tuple(
                str(value).strip() for value in item.get("introduction", [])
            ),
            checklist=tuple(str(value).strip() for value in item.get("checklist", [])),
            verdict=tuple(str(value).strip() for value in item.get("verdict", [])),
        )
        for item in raw["articles"]
    )
    campaign = BootstrapCampaign(
        site_base_url=str(raw["site_base_url"]).rstrip("/"),
        disclosure=str(raw["disclosure"]).strip(),
        article_interval_hours=max(1, int(raw.get("article_interval_hours", 48))),
        telegram_cooldown_hours=max(
            1, int(raw.get("telegram_cooldown_hours", 72))
        ),
        products=products,
        articles=articles,
    )
    _validate_campaign(campaign)
    return campaign


def _validate_campaign(campaign: BootstrapCampaign) -> None:
    product_ids = [product.product_id for product in campaign.products]
    if not product_ids or len(product_ids) != len(set(product_ids)):
        raise ValueError("La campaña necesita productos con identificadores únicos")
    if not campaign.articles:
        raise ValueError("La campaña necesita al menos un artículo")
    slugs = [article.slug for article in campaign.articles]
    if len(slugs) != len(set(slugs)) or any(
        not SLUG_PATTERN.fullmatch(slug) for slug in slugs
    ):
        raise ValueError("Los slugs de la campaña deben ser únicos y seguros")
    available = set(product_ids)
    for article in campaign.articles:
        missing = set(article.product_ids) - available
        if missing:
            raise ValueError(
                f"El artículo {article.slug} referencia productos inexistentes: "
                + ", ".join(sorted(missing))
            )
    for product in campaign.products:
        if not product.affiliate_url.startswith("https://"):
            raise ValueError(f"Enlace no seguro para {product.product_id}")


def format_bootstrap_message(
    product: BootstrapProduct,
    campaign: BootstrapCampaign,
) -> str:
    guide_url = (
        f"{campaign.site_base_url}/{product.guide_path.lstrip('/')}"
        if product.guide_path
        else campaign.site_base_url
    )
    highlights = "\n".join(f"✅ {value}" for value in product.pros[:2])
    return "\n".join(
        [
            f"🎯 RECOMENDACIÓN CHOLLO RADAR: {product.title}",
            "",
            f"👤 Ideal para: {product.best_for}",
            highlights,
            "",
            f"📖 Guía completa: {guide_url}",
            f"🛒 Ver precio actual en Amazon: {product.affiliate_url}",
            "",
            "⏳ Comprueba precio, variante, vendedor y disponibilidad antes de comprar.",
            f"#ad · {campaign.disclosure}",
        ]
    )


def publish_telegram_recommendation(
    campaign: BootstrapCampaign,
    storage: StorageBackend,
    publisher,
    *,
    dry_run: bool,
) -> tuple[str, PublishResult | None, int]:
    skipped = 0
    for product in campaign.products:
        offer = product.as_offer()
        if not dry_run:
            storage.ensure_product(offer)
        if storage.recently_published(
            offer.key, campaign.telegram_cooldown_hours
        ):
            skipped += 1
            continue
        message = format_bootstrap_message(product, campaign)
        result = publisher.publish_text(message, channel="telegram-bootstrap")
        if result.delivered:
            storage.record_publication(
                offer,
                score=0,
                channel=result.channel,
                message=result.message,
                external_message_id=result.external_message_id,
            )
        return product.product_id, result, skipped
    return "", None, skipped


def publish_next_article(
    campaign: BootstrapCampaign,
    site_root: str | Path,
    state_path: str | Path,
    *,
    dry_run: bool,
    force: bool = False,
    now: datetime | None = None,
) -> tuple[str, bool]:
    current = now or _utc_now()
    root = Path(site_root)
    state_file = Path(state_path)
    if not state_file.is_absolute():
        state_file = root / state_file
    state = _load_state(state_file)
    published = {
        str(item.get("slug", "")) for item in state.get("published_articles", [])
    }
    next_article = next(
        (article for article in campaign.articles if article.slug not in published),
        None,
    )
    if next_article is None or not _article_due(
        state, current, campaign.article_interval_hours, force
    ):
        return "", False
    if dry_run:
        return next_article.slug, False

    article_path = root / "articulos" / f"{next_article.slug}.html"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_text(
        render_article(next_article, campaign, current), encoding="utf-8"
    )
    state.setdefault("published_articles", []).append(
        {"slug": next_article.slug, "published_at": current.isoformat()}
    )
    state["last_article_at"] = current.isoformat()
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _refresh_index(root / "index.html", campaign, state)
    _refresh_sitemap(root / "sitemap.xml", campaign, state, current)
    return next_article.slug, True


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"published_articles": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(
        raw.get("published_articles", []), list
    ):
        raise ValueError("El estado de la campaña no es válido")
    return raw


def _article_due(
    state: dict,
    now: datetime,
    interval_hours: int,
    force: bool,
) -> bool:
    if force:
        return True
    value = str(state.get("last_article_at", "")).strip()
    if not value:
        return True
    last = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now >= last + timedelta(hours=interval_hours)


def _replace_between(text: str, start: str, end: str, content: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"No se encontraron marcadores únicos: {start} / {end}")
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    body = f"\n{content.rstrip()}\n" if content.strip() else "\n"
    return f"{before}{start}{body}{end}{after}"


def _published_articles(campaign: BootstrapCampaign, state: dict):
    article_map = {article.slug: article for article in campaign.articles}
    result = []
    for item in reversed(state.get("published_articles", [])):
        article = article_map.get(str(item.get("slug", "")))
        if article:
            result.append((article, str(item.get("published_at", ""))))
    return result


def _refresh_index(path: Path, campaign: BootstrapCampaign, state: dict) -> None:
    cards = []
    for article, published_at in _published_articles(campaign, state):
        date = published_at[:10]
        cards.append(
            "\n".join(
                [
                    f'<a class="card" href="articulos/{html.escape(article.slug)}.html">',
                    f'<span class="tag">Nueva guía · {html.escape(date)}</span>',
                    f"<h3>{html.escape(article.title)}</h3>",
                    f'<p class="muted">{html.escape(article.description)}</p>',
                    "<b>Leer guía →</b></a>",
                ]
            )
        )
    original = path.read_text(encoding="utf-8")
    path.write_text(
        _replace_between(original, AUTO_INDEX_START, AUTO_INDEX_END, "\n".join(cards)),
        encoding="utf-8",
    )


def _refresh_sitemap(
    path: Path,
    campaign: BootstrapCampaign,
    state: dict,
    now: datetime,
) -> None:
    urls = []
    for article, _ in _published_articles(campaign, state):
        urls.append(
            "  <url>"
            f"<loc>{html.escape(campaign.site_base_url)}/articulos/"
            f"{html.escape(article.slug)}.html</loc>"
            f"<lastmod>{now.date().isoformat()}</lastmod></url>"
        )
    original = path.read_text(encoding="utf-8")
    path.write_text(
        _replace_between(
            original, AUTO_SITEMAP_START, AUTO_SITEMAP_END, "\n".join(urls)
        ),
        encoding="utf-8",
    )


def render_article(
    article: BootstrapArticle,
    campaign: BootstrapCampaign,
    published_at: datetime,
) -> str:
    products = [campaign.product_map[value] for value in article.product_ids]
    canonical = f"{campaign.site_base_url}/articulos/{article.slug}.html"
    date = published_at.date().isoformat()
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": article.title,
            "description": article.description,
            "datePublished": date,
            "dateModified": date,
            "author": {"@type": "Organization", "name": "Chollo Radar"},
            "publisher": {"@type": "Organization", "name": "Chollo Radar"},
            "mainEntityOfPage": canonical,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    introductions = "\n".join(
        f"<p>{html.escape(paragraph)}</p>" for paragraph in article.introduction
    )
    checklist = "\n".join(
        f"<li>{html.escape(value)}</li>" for value in article.checklist
    )
    product_sections = "\n".join(
        _render_product(product, position) for position, product in enumerate(products, 1)
    )
    verdict = "\n".join(
        f"<p>{html.escape(paragraph)}</p>" for paragraph in article.verdict
    )
    return f'''<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(article.title)} | Chollo Radar</title>
<meta name="description" content="{html.escape(article.description, quote=True)}">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
<meta property="og:title" content="{html.escape(article.title, quote=True)}">
<meta property="og:description" content="{html.escape(article.description, quote=True)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{html.escape(canonical, quote=True)}">
<link rel="stylesheet" href="../styles.css">
<script type="application/ld+json">{json_ld}</script>
</head><body>
<header><div class="wrap nav"><a class="brand" href="../">⚡ Chollo Radar</a><nav><a href="../#selecciones">Selecciones</a><a href="../#guias">Guías</a><a href="../legal.html">Legal</a></nav></div></header>
<main class="article">
<span class="tag">{html.escape(article.kicker)} · {published_at.strftime('%d/%m/%Y')}</span>
<h1>{html.escape(article.title)}</h1>
<p class="lead">{html.escape(article.lead)}</p>
<div class="disclosure"><strong>Transparencia:</strong> {html.escape(campaign.disclosure)} Los botones que llevan a Amazon son enlaces pagados. No mostramos precios manuales porque pueden cambiar.</div>
{introductions}
<h2>Qué conviene comprobar antes de elegir</h2>
<div class="box checklist"><ul>{checklist}</ul></div>
<h2>Nuestra selección razonada</h2>
{product_sections}
<h2>Conclusión</h2>
{verdict}
<div class="notice"><strong>Nota editorial:</strong> comprueba siempre el precio actual, la variante, el vendedor, la devolución y la disponibilidad en Amazon antes de pagar.</div>
</main>
<footer><div class="wrap"><div>© 2026 Chollo Radar</div><div class="footer-disclosure">{html.escape(campaign.disclosure)}</div></div></footer>
</body></html>'''


def _render_product(product: BootstrapProduct, position: int) -> str:
    specs = " · ".join(product.specs)
    pros = "".join(f"<li>{html.escape(value)}</li>" for value in product.pros)
    considerations = "".join(
        f"<li>{html.escape(value)}</li>" for value in product.considerations
    )
    source = (
        f'<div class="source">Imagen alojada por el fabricante. '
        f'<a href="{html.escape(product.image_source_url, quote=True)}" '
        'target="_blank" rel="noopener">Fuente</a>.</div>'
        if product.image_source_url
        else ""
    )
    image = (
        f'<a href="{html.escape(product.affiliate_url, quote=True)}" '
        'rel="nofollow sponsored noopener" target="_blank">'
        f'<img loading="lazy" src="{html.escape(product.image_url, quote=True)}" '
        f'alt="{html.escape(product.title, quote=True)}"></a>'
        if product.image_url
        else ""
    )
    return f'''<section class="product">
<div class="product-media{' no-image' if not image else ''}">
{image}
<div class="product-body">
<span class="tag">Opción {position} · {html.escape(product.best_for)}</span>
<h2>{html.escape(product.title)}</h2>
<p>{html.escape(product.summary)}</p>
<p class="muted">{html.escape(specs)}</p>
<div class="procon"><div><strong>✓ Lo mejor</strong><ul>{pros}</ul></div><div><strong>△ A tener en cuenta</strong><ul>{considerations}</ul></div></div>
<div class="buttons"><a class="button" href="{html.escape(product.affiliate_url, quote=True)}" rel="nofollow sponsored noopener" target="_blank">Ver precio actual en Amazon</a></div>
<div class="cta-note">(enlace pagado) · El precio y la disponibilidad se comprueban al abrir Amazon.</div>
{source}
</div></div></section>'''
