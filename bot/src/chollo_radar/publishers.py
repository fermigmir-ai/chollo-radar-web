from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol

from .models import Offer, PublishResult


class Publisher(Protocol):
    def publish(self, offer: Offer, score: int, disclosure: str) -> PublishResult: ...


def format_offer(offer: Offer, score: int, disclosure: str) -> str:
    price = f"{offer.current_price:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    lines = [f"🔥 CHOLLO: {offer.title}", "", f"💶 {price}"]
    if offer.reference_price is not None:
        reference = f"{offer.reference_price:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        lines[-1] += f" · antes {reference} · -{offer.discount_percent:.0f}%"
    elif offer.discount_percent:
        lines[-1] += f" · -{offer.discount_percent:.0f}%"
    if offer.merchant:
        lines.append(f"🏪 {offer.merchant}")
    lines.extend(
        [
            f"⭐ Selección Chollo Radar: {score}/100",
            "",
            f"🛒 {offer.url}",
            "",
            "⏳ El precio y la disponibilidad pueden cambiar.",
            f"#ad · {disclosure}",
        ]
    )
    return "\n".join(lines)


class ConsolePublisher:
    def publish(self, offer: Offer, score: int, disclosure: str) -> PublishResult:
        message = format_offer(offer, score, disclosure)
        print("\n" + "=" * 72)
        print(message)
        print("=" * 72)
        return PublishResult(
            channel="console-dry-run",
            delivered=False,
            message=message,
        )


class TelegramPublisher:
    def __init__(self, token: str, chat_id: str, timeout: int = 20):
        if not token or not chat_id:
            raise ValueError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _post(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram respondió HTTP {exc.code}: {body[:400]}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"No se pudo conectar con Telegram: {exc}") from None
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rechazó el mensaje: {result.get('description', 'sin detalle')}")
        return result

    def send_test(self) -> None:
        self._post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": "✅ Chollo Radar Bot está conectado y listo para publicar.",
                "disable_web_page_preview": True,
            },
        )

    def publish(self, offer: Offer, score: int, disclosure: str) -> PublishResult:
        text = format_offer(offer, score, disclosure)
        if offer.image_url and len(text) <= 1024:
            try:
                response = self._post(
                    "sendPhoto",
                    {
                        "chat_id": self.chat_id,
                        "photo": offer.image_url,
                        "caption": text,
                    },
                )
                return PublishResult(
                    channel="telegram",
                    delivered=True,
                    external_message_id=str(
                        response.get("result", {}).get("message_id", "")
                    ),
                    message=text,
                )
            except RuntimeError:
                pass
        response = self._post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
        )
        return PublishResult(
            channel="telegram",
            delivered=True,
            external_message_id=str(
                response.get("result", {}).get("message_id", "")
            ),
            message=text,
        )
