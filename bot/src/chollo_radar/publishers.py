from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
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

    def publish_text(
        self, message: str, channel: str = "console-dry-run"
    ) -> PublishResult:
        print("\n" + "=" * 72)
        print(message)
        print("=" * 72)
        return PublishResult(channel=channel, delivered=False, message=message)


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

    def publish_text(
        self, message: str, channel: str = "telegram"
    ) -> PublishResult:
        response = self._post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": False,
            },
        )
        return PublishResult(
            channel=channel,
            delivered=True,
            external_message_id=str(
                response.get("result", {}).get("message_id", "")
            ),
            message=message,
        )


class XPublisher:
    endpoint = "https://api.x.com/2/tweets"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        timeout: int = 20,
    ):
        values = (api_key, api_secret, access_token, access_token_secret)
        if not all(values):
            raise ValueError(
                "Faltan X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN o "
                "X_ACCESS_TOKEN_SECRET"
            )
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.timeout = timeout

    @staticmethod
    def _encode(value: str) -> str:
        return urllib.parse.quote(str(value), safe="~-._")

    def _authorization_header(self, method: str, url: str) -> str:
        parameters = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }
        parameter_string = "&".join(
            f"{self._encode(key)}={self._encode(value)}"
            for key, value in sorted(parameters.items())
        )
        base_string = "&".join(
            (
                method.upper(),
                self._encode(url),
                self._encode(parameter_string),
            )
        )
        signing_key = (
            f"{self._encode(self.api_secret)}&"
            f"{self._encode(self.access_token_secret)}"
        )
        signature = base64.b64encode(
            hmac.new(
                signing_key.encode("utf-8"),
                base_string.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        parameters["oauth_signature"] = signature
        values = ", ".join(
            f'{self._encode(key)}="{self._encode(value)}"'
            for key, value in sorted(parameters.items())
        )
        return f"OAuth {values}"

    def publish_text(self, message: str, channel: str = "x") -> PublishResult:
        if not message.strip():
            raise ValueError("La publicación de X no puede estar vacía")
        if len(message) > 280:
            raise ValueError(
                f"La publicación de X supera 280 caracteres: {len(message)}"
            )
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"text": message}).encode("utf-8"),
            headers={
                "Authorization": self._authorization_header(
                    "POST", self.endpoint
                ),
                "Content-Type": "application/json",
                "User-Agent": "CholloRadarBot/0.4",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"X respondió HTTP {exc.code}: {body[:400]}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"No se pudo conectar con X: {exc}") from None
        post_id = str(result.get("data", {}).get("id", ""))
        if not post_id:
            raise RuntimeError("X no devolvió el identificador de la publicación")
        return PublishResult(
            channel=channel,
            delivered=True,
            external_message_id=post_id,
            message=message,
        )

    def send_test(self) -> PublishResult:
        return self.publish_text(
            "✅ Chollo Radar está conectado y listo para publicar en X. #CholloRadar",
            channel="x-test",
        )
