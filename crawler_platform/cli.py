from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

from crawler_platform import __version__
from crawler_platform.config import load_config, load_dotenv
from crawler_platform.messages import render_message
from crawler_platform.models import ActionContext
from crawler_platform.scheduler import describe_report, run_spec, serve, validate_runtime
from crawler_platform.state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crawler_platform",
        description="Corre crawlers cada cierto tiempo y ejecuta una acción cuando se cumple una condición.",
    )
    parser.add_argument("--config", default=os.environ.get("CRAWLERS_CONFIG", "config/crawlers.yaml"))
    parser.add_argument("--state", default=os.environ.get("CRAWLERS_STATE", "data/state.json"))
    parser.add_argument("--once", metavar="ID", help="Ejecuta un crawler una vez y termina")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lee la página y muestra qué haría, sin avisar ni guardar estado",
    )
    parser.add_argument("--test-telegram", action="store_true", help="Envía un mensaje de prueba")
    parser.add_argument(
        "--print-chat-id",
        action="store_true",
        help="Muestra los chat_id que le escribieron al bot",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    load_dotenv(Path(".env"))
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # El token del bot va en la URL de Telegram. Estos loggers no tienen que imprimirla.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    try:
        if args.print_chat_id:
            asyncio.run(_print_chat_ids())
            return 0
        if args.test_telegram:
            asyncio.run(_send_test())
            return 0
        if args.once:
            return asyncio.run(_run_once(Path(args.config), Path(args.state), args.once, args.dry_run))
        asyncio.run(serve(Path(args.config), Path(args.state)))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def _run_once(config_path: Path, state_path: Path, crawler_id: str, dry_run: bool) -> int:
    config = load_config(config_path)
    validate_runtime(config, require_secrets=not dry_run)
    spec = next((item for item in config.crawlers if item.id == crawler_id), None)
    if spec is None:
        known = ", ".join(item.id for item in config.crawlers)
        raise ValueError(f"No existe el crawler '{crawler_id}'. Ids: {known}")

    state = StateStore(state_path)
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        report = await run_spec(spec, state, client, dry_run=dry_run)

    print(describe_report(report))
    for item in report.items:
        price = item.fields.get("price", "")
        print(f"- {item.label} | {item.status} | botón={item.fields.get('button_text', '')} | {price}")
    if dry_run and report.matches:
        preview = render_message(
            ActionContext(
                crawler_id=spec.id,
                crawler_name=spec.name,
                url=spec.url,
                matched_items=report.matches,
                all_items=report.items,
            )
        )
        print("\nMensaje que se enviaría:\n")
        print(preview)
    if report.error:
        return 1
    return 0


async def _print_chat_ids() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("Falta TELEGRAM_BOT_TOKEN en el entorno o en .env")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getUpdates")
        payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo contactar a Telegram ({type(exc).__name__})") from None
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or "Telegram rechazó getUpdates")

    seen: dict[int, dict] = {}
    for update in payload.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if "id" in chat:
            seen[chat["id"]] = chat
    if not seen:
        print("No hay mensajes. Abrí el bot en Telegram, enviá /start y volvé a correr este comando.")
        return
    for chat in seen.values():
        name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
        print(f"chat_id={chat['id']} tipo={chat.get('type', '')} nombre={name}")


async def _send_test() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise ValueError("Completá TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")
    text = "Prueba de la plataforma de crawlers. Si leés esto, el aviso de Telegram está bien configurado."
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo contactar a Telegram ({type(exc).__name__})") from None
    if response.status_code != 200 or not payload.get("ok"):
        raise RuntimeError(payload.get("description") or f"HTTP {response.status_code}")
    print(f"Mensaje de prueba enviado a chat_id={chat_id}")
