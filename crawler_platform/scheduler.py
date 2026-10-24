from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from pathlib import Path

import httpx

from crawler_platform.actions import REGISTRY as ACTION_TYPES
from crawler_platform.actions import get_action
from crawler_platform.crawlers import REGISTRY as CRAWLER_TYPES
from crawler_platform.crawlers import get_crawler
from crawler_platform.config import AppConfig, load_config
from crawler_platform.models import ActionContext, ActionSpec, CrawlerSpec, RunReport
from crawler_platform.runner import execute_crawler
from crawler_platform.state import StateStore

logger = logging.getLogger(__name__)


def validate_runtime(config: AppConfig, *, require_secrets: bool) -> None:
    if not config.crawlers:
        raise ValueError("No hay crawlers configurados")

    enabled = [spec for spec in config.crawlers if spec.enabled]
    needs_default_chat = False
    for spec in config.crawlers:
        if spec.type not in CRAWLER_TYPES:
            known = ", ".join(sorted(CRAWLER_TYPES))
            raise ValueError(
                f"{spec.id}: tipo '{spec.type}' desconocido. Disponibles: {known}"
            )
        for action in spec.actions:
            if action.type not in ACTION_TYPES:
                known = ", ".join(sorted(ACTION_TYPES))
                raise ValueError(
                    f"{spec.id}: acción '{action.type}' desconocida. Disponibles: {known}"
                )
            if spec.enabled and action.type == "telegram" and not action.chat_id:
                needs_default_chat = True

    if not require_secrets:
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    uses_telegram = any(
        action.type == "telegram" for spec in enabled for action in spec.actions
    )
    if uses_telegram and not token:
        raise ValueError(
            "Falta TELEGRAM_BOT_TOKEN. Copiá .env.example a .env y completá el token del bot."
        )
    if uses_telegram and needs_default_chat and not chat_id:
        raise ValueError(
            "Falta TELEGRAM_CHAT_ID. Enviá /start al bot y corré: "
            "python -m crawler_platform --print-chat-id"
        )


def describe_report(report: RunReport) -> str:
    if report.error:
        return f"{report.crawler_id}: error: {report.error}"
    editions = len(report.items)
    available = sum(1 for item in report.items if item.status != "agotado")
    pending = ", ".join(item.label for item in report.matches) or "ninguno"
    edition_label = "edición" if editions == 1 else "ediciones"
    available_label = "disponible" if available == 1 else "disponibles"
    return (
        f"{report.crawler_id}: {editions} {edition_label}, "
        f"{available} {available_label}, a notificar: {pending}"
    )


def log_report(report: RunReport) -> None:
    if report.error:
        logger.error(describe_report(report))
        return
    logger.info(describe_report(report))
    for item in report.items:
        logger.info(
            "%s | %s | %s | botón=%s",
            report.crawler_id,
            item.label,
            item.status,
            item.fields.get("button_text", ""),
        )
    if report.notified:
        logger.info("%s: aviso enviado", report.crawler_id)
    elif report.matches:
        logger.info("%s: la condición se cumple; no se envió aviso (prueba)", report.crawler_id)


async def perform_actions(
    client: httpx.AsyncClient,
    actions: list[ActionSpec],
    ctx: ActionContext,
) -> None:
    for action in actions:
        await get_action(action.type, client).run(action, ctx)


async def run_spec(
    spec: CrawlerSpec,
    state: StateStore,
    client: httpx.AsyncClient,
    *,
    dry_run: bool,
) -> RunReport:
    crawler = get_crawler(spec.type, client)

    async def perform(actions: list[ActionSpec], ctx: ActionContext) -> None:
        await perform_actions(client, actions, ctx)

    return await execute_crawler(
        spec,
        state,
        collect=crawler.collect,
        perform_actions=perform,
        dry_run=dry_run,
    )


async def serve(config_path: Path, state_path: Path) -> None:
    config = load_config(config_path)
    validate_runtime(config, require_secrets=True)
    state = StateStore(state_path)
    next_run: dict[str, float] = {}
    config_mtime = config_path.stat().st_mtime
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        logger.info(
            "Plataforma iniciada. %s crawlers, estado en %s",
            len(config.crawlers),
            state_path,
        )
        for spec in config.crawlers:
            logger.info(
                "Crawler %s cada %ss (%s)",
                spec.id,
                spec.interval_seconds,
                "activo" if spec.enabled else "pausado",
            )
        while not stop.is_set():
            config, config_mtime = _reload_if_changed(config_path, config, config_mtime)
            now = time.monotonic()
            due = [
                spec
                for spec in config.crawlers
                if spec.enabled and now >= next_run.get(spec.id, 0)
            ]
            for spec in due:
                if stop.is_set():
                    break
                await _run_and_log(spec, state, client, dry_run=False)
                next_run[spec.id] = time.monotonic() + spec.interval_seconds
            if stop.is_set():
                break
            wait = _seconds_until_next(config, next_run)
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
    logger.info("Plataforma detenida")


def _reload_if_changed(
    config_path: Path,
    config: AppConfig,
    config_mtime: float,
) -> tuple[AppConfig, float]:
    try:
        current = config_path.stat().st_mtime
    except OSError:
        logger.exception("No pude leer la fecha de %s", config_path)
        return config, config_mtime
    if current == config_mtime:
        return config, config_mtime
    try:
        loaded = load_config(config_path)
        validate_runtime(loaded, require_secrets=True)
    except Exception:
        logger.exception("La configuración nueva es inválida; sigo con la anterior")
        return config, current
    logger.info("Configuración recargada: %s", config_path)
    return loaded, current


def _seconds_until_next(config: AppConfig, next_run: dict[str, float]) -> float:
    enabled = {spec.id for spec in config.crawlers if spec.enabled}
    upcoming = [moment for crawler_id, moment in next_run.items() if crawler_id in enabled]
    if not upcoming:
        return 30.0
    return max(0.5, min(30.0, min(upcoming) - time.monotonic()))


async def _run_and_log(
    spec: CrawlerSpec,
    state: StateStore,
    client: httpx.AsyncClient,
    *,
    dry_run: bool,
) -> RunReport:
    try:
        report = await run_spec(spec, state, client, dry_run=dry_run)
    except Exception:
        logger.exception(
            "No se pudo notificar %s. Se reintenta en el próximo ciclo.",
            spec.id,
        )
        return RunReport(crawler_id=spec.id, items=[], matches=[], notified=False)
    log_report(report)
    return report
