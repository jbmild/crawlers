from __future__ import annotations

import logging
import os

import httpx

from crawler_platform.messages import render_message
from crawler_platform.models import ActionContext, ActionSpec

logger = logging.getLogger(__name__)


class TelegramAction:
    type_name = "telegram"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def run(self, action: ActionSpec, ctx: ActionContext) -> None:
        token_env = action.options.get("token_env", "TELEGRAM_BOT_TOKEN")
        chat_env = action.options.get("chat_id_env", "TELEGRAM_CHAT_ID")
        token = os.environ.get(token_env, "").strip()
        chat_id = (action.chat_id or os.environ.get(chat_env, "")).strip()
        if not token or not chat_id:
            raise RuntimeError(
                f"Faltan {token_env} o el chat de destino ({chat_env} o chat_id de la acción)"
            )

        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": render_message(ctx)[:4096],
                    "disable_web_page_preview": False,
                },
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"No se pudo contactar a Telegram ({type(exc).__name__})"
            ) from None
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Telegram respondió {response.status_code} sin JSON"
            ) from exc
        if response.status_code != 200 or not payload.get("ok"):
            description = payload.get("description") or "sin detalle"
            raise RuntimeError(f"Telegram rechazó el mensaje: {description}")
        logger.info("Aviso enviado a Telegram chat_id=%s", chat_id)
