from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .models import Offer, RunSummary


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StorageBackend(Protocol):
    def close(self) -> None: ...

    def ensure_product(self, offer: Offer) -> None: ...

    def observe(self, offer: Offer) -> None: ...

    def recently_published(self, offer_key: str, cooldown_hours: int) -> bool: ...

    def record_publication(
        self,
        offer: Offer,
        score: int,
        channel: str,
        message: str,
        external_message_id: str = "",
    ) -> None: ...

    def get_cursor(self) -> int: ...

    def set_cursor(self, value: int) -> None: ...

    def start_run(self, source: str, dry_run: bool) -> str: ...

    def finish_run(
        self,
        run_id: str,
        summary: RunSummary | None,
        error: str = "",
    ) -> None: ...

    def stats(self) -> dict: ...


class Storage:
    """Almacenamiento local para desarrollo y para el modo demostración."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_key TEXT NOT NULL,
                product_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL,
                score INTEGER,
                price REAL,
                message TEXT,
                external_message_id TEXT,
                published_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_publications_offer_time
                ON publications(offer_key, published_at);

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._ensure_column("publications", "score", "INTEGER")
        self._ensure_column("publications", "price", "REAL")
        self._ensure_column("publications", "message", "TEXT")
        self._ensure_column("publications", "external_message_id", "TEXT")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, data_type: str) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {data_type}"
            )

    def close(self) -> None:
        self.connection.close()

    def observe(self, offer: Offer) -> None:
        # El feed demo no necesita persistir catálogo ni histórico de precios.
        return None

    def ensure_product(self, offer: Offer) -> None:
        # SQLite solo conserva publicaciones; no mantiene un catálogo separado.
        return None

    def recently_published(self, offer_key: str, cooldown_hours: int) -> bool:
        cutoff = _utc_now() - timedelta(hours=cooldown_hours)
        row = self.connection.execute(
            """
            SELECT 1 FROM publications
            WHERE offer_key = ? AND published_at >= ?
            LIMIT 1
            """,
            (offer_key, cutoff.isoformat()),
        ).fetchone()
        return row is not None

    def record_publication(
        self,
        offer: Offer,
        score: int,
        channel: str,
        message: str,
        external_message_id: str = "",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO publications
                (offer_key, product_id, provider, channel, score, price,
                 message, external_message_id, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer.key,
                offer.product_id,
                offer.provider,
                channel,
                score,
                offer.current_price if offer.current_price > 0 else None,
                message,
                external_message_id or None,
                _utc_now().isoformat(),
            ),
        )
        self.connection.commit()

    def get_cursor(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM state WHERE key = 'query_cursor'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def set_cursor(self, value: int) -> None:
        self.connection.execute(
            """
            INSERT INTO state(key, value) VALUES('query_cursor', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(value),),
        )
        self.connection.commit()

    def start_run(self, source: str, dry_run: bool) -> str:
        return ""

    def finish_run(
        self,
        run_id: str,
        summary: RunSummary | None,
        error: str = "",
    ) -> None:
        return None

    def stats(self) -> dict:
        count = self.connection.execute(
            "SELECT COUNT(*) AS value FROM publications"
        ).fetchone()["value"]
        last_rows = self.connection.execute(
            """
            SELECT product_id, provider, channel, score, price, published_at
            FROM publications ORDER BY id DESC LIMIT 10
            """
        ).fetchall()
        return {
            "backend": "sqlite",
            "publications": count,
            "query_cursor": self.get_cursor(),
            "last": [dict(row) for row in last_rows],
        }


class SupabaseRestClient:
    """Cliente mínimo de PostgREST compatible con claves secretas nuevas y legacy."""

    def __init__(self, url: str, key: str, timeout: int = 25):
        self.base_url = url.rstrip("/") + "/rest/v1"
        self.key = key
        self.timeout = timeout

    def _headers(self, prefer: str = "") -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CholloRadarBot/0.2",
        }
        # Las nuevas sb_secret_* no son JWT y no deben enviarse como Bearer.
        if not self.key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        query: list[tuple[str, str]] | None = None,
        payload: dict | list | None = None,
        prefer: str = "",
        retries: int = 3,
    ):
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        last_error = ""
        for attempt in range(retries):
            request = urllib.request.Request(
                url,
                data=data,
                headers=self._headers(prefer),
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    if not body:
                        return None
                    return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {body[:600]}"
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After")
                delay = (
                    int(retry_after)
                    if retry_after and retry_after.isdigit()
                    else 2**attempt
                )
                time.sleep(min(delay, 12))
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"Error de Supabase en {method} {path}: {last_error}")


class SupabaseStorage:
    """Persistencia compartida para ejecuciones programadas en GitHub Actions."""

    def __init__(self, url: str, key: str):
        if not url or not key:
            raise ValueError("Faltan SUPABASE_URL o SUPABASE_SECRET_KEY")
        self.client = SupabaseRestClient(url, key)
        self._product_ids: dict[str, str] = {}

    @classmethod
    def from_env(cls) -> "SupabaseStorage":
        key = (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        return cls(os.getenv("SUPABASE_URL", "").strip(), key)

    def close(self) -> None:
        return None

    @staticmethod
    def _external_id(offer_key: str) -> str:
        return offer_key.split(":", 1)[-1]

    def _lookup_product_id(self, external_id: str) -> str | None:
        rows = self.client.request(
            "GET",
            "products",
            query=[
                ("select", "id"),
                ("external_id", f"eq.{external_id}"),
                ("limit", "1"),
            ],
        )
        if isinstance(rows, list) and rows:
            return str(rows[0]["id"])
        return None

    def _product_id_for_key(self, offer_key: str) -> str | None:
        cached = self._product_ids.get(offer_key)
        if cached:
            return cached
        product_id = self._lookup_product_id(self._external_id(offer_key))
        if product_id:
            self._product_ids[offer_key] = product_id
        return product_id

    def ensure_product(self, offer: Offer) -> None:
        rows = self.client.request(
            "POST",
            "products",
            query=[("on_conflict", "external_id")],
            payload={
                "external_id": offer.product_id,
                "title": offer.title,
                "url": offer.url,
                "category": offer.category,
                "image_url": offer.image_url or None,
                "active": True,
                "updated_at": _utc_now().isoformat(),
            },
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Supabase no devolvió el producto guardado")
        product_id = str(rows[0]["id"])
        self._product_ids[offer.key] = product_id

    def observe(self, offer: Offer) -> None:
        self.ensure_product(offer)
        product_id = self._product_id_for_key(offer.key)
        if not product_id:
            raise RuntimeError("No se puede guardar el precio sin producto")
        self.client.request(
            "POST",
            "price_observations",
            payload={
                "product_id": product_id,
                "price": offer.current_price,
                "currency": offer.currency,
                "available": True,
                "observed_at": offer.observed_at.isoformat(),
            },
            prefer="return=minimal",
        )

    def recently_published(self, offer_key: str, cooldown_hours: int) -> bool:
        product_id = self._product_id_for_key(offer_key)
        if not product_id:
            return False
        cutoff = (_utc_now() - timedelta(hours=cooldown_hours)).isoformat()
        rows = self.client.request(
            "GET",
            "publications",
            query=[
                ("select", "id"),
                ("product_id", f"eq.{product_id}"),
                ("published_at", f"gte.{cutoff}"),
                ("limit", "1"),
            ],
        )
        return bool(rows)

    def record_publication(
        self,
        offer: Offer,
        score: int,
        channel: str,
        message: str,
        external_message_id: str = "",
    ) -> None:
        product_id = self._product_id_for_key(offer.key)
        if not product_id:
            raise RuntimeError("No se puede registrar una publicación sin producto")
        self.client.request(
            "POST",
            "publications",
            payload={
                "product_id": product_id,
                "channel": channel,
                "score": score,
                "price": offer.current_price if offer.current_price > 0 else None,
                "message": message,
                "external_message_id": external_message_id or None,
                "published_at": _utc_now().isoformat(),
            },
            prefer="return=minimal",
        )

    def get_cursor(self) -> int:
        rows = self.client.request(
            "GET",
            "bot_state",
            query=[
                ("select", "value"),
                ("key", "eq.query_cursor"),
                ("limit", "1"),
            ],
        )
        return int(rows[0]["value"]) if isinstance(rows, list) and rows else 0

    def set_cursor(self, value: int) -> None:
        self.client.request(
            "POST",
            "bot_state",
            query=[("on_conflict", "key")],
            payload={
                "key": "query_cursor",
                "value": str(value),
                "updated_at": _utc_now().isoformat(),
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def start_run(self, source: str, dry_run: bool) -> str:
        rows = self.client.request(
            "POST",
            "bot_runs",
            payload={
                "source": source,
                "dry_run": dry_run,
                "status": "running",
                "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None,
            },
            prefer="return=representation",
        )
        if isinstance(rows, list) and rows:
            return str(rows[0]["id"])
        return ""

    def finish_run(
        self,
        run_id: str,
        summary: RunSummary | None,
        error: str = "",
    ) -> None:
        if not run_id:
            return
        payload: dict = {
            "finished_at": _utc_now().isoformat(),
            "status": "failed" if error else "completed",
            "errors": [error] if error else list(summary.errors if summary else ()),
        }
        if summary:
            payload.update(
                {
                    "queries": summary.queries,
                    "fetched": summary.fetched,
                    "eligible": summary.eligible,
                    "published": summary.published,
                    "previewed": summary.previewed,
                    "skipped_recent": summary.skipped_recent,
                }
            )
        self.client.request(
            "PATCH",
            "bot_runs",
            query=[("id", f"eq.{run_id}")],
            payload=payload,
            prefer="return=minimal",
        )

    def stats(self) -> dict:
        state = self.client.request(
            "GET",
            "bot_state",
            query=[("select", "key,value,updated_at"), ("order", "key.asc")],
        )
        runs = self.client.request(
            "GET",
            "bot_runs",
            query=[
                (
                    "select",
                    "id,status,source,dry_run,started_at,finished_at,queries,"
                    "fetched,eligible,published,previewed,skipped_recent,errors",
                ),
                ("order", "started_at.desc"),
                ("limit", "10"),
            ],
        )
        return {"backend": "supabase", "state": state or [], "runs": runs or []}


def create_storage(database_path: Path) -> StorageBackend:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if url or key:
        if not url or not key:
            raise ValueError(
                "Configura juntos SUPABASE_URL y SUPABASE_SECRET_KEY "
                "(o SUPABASE_SERVICE_ROLE_KEY)."
            )
        return SupabaseStorage(url, key)
    return Storage(database_path)
