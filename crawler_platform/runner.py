from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from crawler_platform.conditions import matching_items
from crawler_platform.models import (
    ActionContext,
    ActionSpec,
    CrawlerSpec,
    Item,
    RunReport,
)
from crawler_platform.state import StateStore, snapshot

logger = logging.getLogger(__name__)

Collect = Callable[[CrawlerSpec], Awaitable[list[Item]]]
PerformActions = Callable[[list[ActionSpec], ActionContext], Awaitable[None]]


async def execute_crawler(
    spec: CrawlerSpec,
    state: StateStore,
    *,
    collect: Collect,
    perform_actions: PerformActions,
    dry_run: bool = False,
    now: datetime | None = None,
) -> RunReport:
    """Lee el crawler, evalúa la condición y dispara las acciones.

    El estado se guarda después de notificar. Si la acción falla, el estado
    anterior se conserva y el próximo ciclo vuelve a intentar el aviso.
    """
    moment = now or datetime.now(timezone.utc)
    try:
        items = await collect(spec)
    except Exception as exc:
        return await _record_failure(
            spec,
            state,
            exc,
            perform_actions=perform_actions,
            dry_run=dry_run,
            now=moment,
        )

    record = state.get(spec.id)
    matches = matching_items(items, record.items, spec.condition)
    notified = False
    if matches and not dry_run:
        await perform_actions(
            spec.actions,
            ActionContext(
                crawler_id=spec.id,
                crawler_name=spec.name,
                url=spec.url,
                matched_items=matches,
                all_items=items,
                kind="match",
            ),
        )
        notified = True

    if not dry_run:
        record.items = {item.key: snapshot(item) for item in items}
        record.consecutive_errors = 0
        record.last_error = None
        record.error_notified = False
        record.last_run = moment.isoformat()
        state.save()

    return RunReport(
        crawler_id=spec.id,
        items=items,
        matches=matches,
        notified=notified,
    )


async def _record_failure(
    spec: CrawlerSpec,
    state: StateStore,
    exc: Exception,
    *,
    perform_actions: PerformActions,
    dry_run: bool,
    now: datetime,
) -> RunReport:
    message = f"{type(exc).__name__}: {exc}"[:500]
    logger.warning("No se pudo leer %s: %s", spec.id, message)
    if dry_run:
        return RunReport(crawler_id=spec.id, items=[], matches=[], notified=False, error=message)

    record = state.get(spec.id)
    record.consecutive_errors += 1
    record.last_error = message
    record.last_run = now.isoformat()
    notified = False
    should_notify = (
        spec.error_after > 0
        and record.consecutive_errors >= spec.error_after
        and not record.error_notified
    )
    if should_notify:
        try:
            await perform_actions(
                spec.actions,
                ActionContext(
                    crawler_id=spec.id,
                    crawler_name=spec.name,
                    url=spec.url,
                    matched_items=[],
                    all_items=[],
                    kind="error",
                    error=message,
                    consecutive_errors=record.consecutive_errors,
                ),
            )
        except Exception:
            logger.exception("No se pudo avisar el fallo de %s", spec.id)
        else:
            record.error_notified = True
            notified = True
    state.save()
    return RunReport(
        crawler_id=spec.id,
        items=[],
        matches=[],
        notified=notified,
        error=message,
    )
