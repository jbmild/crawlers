import asyncio
from datetime import datetime, timezone

import pytest

from crawler_platform.models import ActionContext, CrawlerSpec, ConditionSpec, Item
from crawler_platform.runner import execute_crawler
from crawler_platform.state import StateStore


def _spec() -> CrawlerSpec:
    return CrawlerSpec(
        id="iron-man-mark-iii",
        name="Iron Man – Construí la armadura Mark III",
        type="brihet_variations",
        enabled=True,
        interval_seconds=300,
        url="https://brihet.com.ar/producto/iron-man-construi-la-armadura-mark-iii/",
        options={},
        condition=ConditionSpec("field_not_equals", "status", "agotado", "on_change"),
        actions=[],
        error_after=2,
    )


def _item(status: str) -> Item:
    return Item(
        key="339133",
        label="Fascículo N° 01 + piezas",
        status=status,
        fields={"button_text": "Agotado" if status == "agotado" else "Añadir al carrito", "price": "$4,500.00"},
    )


def test_sold_out_is_remembered_and_availability_notifies_once(tmp_path):
    state = StateStore(tmp_path / "state.json")
    sent: list[ActionContext] = []

    async def collect_sold_out(_spec):
        return [_item("agotado")]

    async def collect_available(_spec):
        return [_item("disponible")]

    async def perform(_actions, ctx):
        sent.append(ctx)

    spec = _spec()
    moment = datetime(2026, 10, 24, tzinfo=timezone.utc)

    first = asyncio.run(
        execute_crawler(spec, state, collect=collect_sold_out, perform_actions=perform, now=moment)
    )
    assert first.matches == []
    assert first.notified is False
    assert sent == []

    second = asyncio.run(
        execute_crawler(spec, state, collect=collect_available, perform_actions=perform, now=moment)
    )
    assert [item.key for item in second.matches] == ["339133"]
    assert second.notified is True
    assert sent[0].crawler_name.startswith("Iron Man")

    third = asyncio.run(
        execute_crawler(spec, state, collect=collect_available, perform_actions=perform, now=moment)
    )
    assert third.matches == []
    assert len(sent) == 1


def test_failed_notification_is_retried(tmp_path):
    state = StateStore(tmp_path / "state.json")
    attempts = {"count": 0}

    async def collect(_spec):
        return [_item("disponible")]

    async def perform(_actions, _ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("telegram down")

    spec = _spec()
    with pytest.raises(RuntimeError, match="telegram down"):
        asyncio.run(execute_crawler(spec, state, collect=collect, perform_actions=perform))

    assert not (tmp_path / "state.json").exists()

    report = asyncio.run(execute_crawler(spec, state, collect=collect, perform_actions=perform))
    assert report.notified is True
    assert attempts["count"] == 2


def test_dry_run_does_not_write_state_or_notify(tmp_path):
    state = StateStore(tmp_path / "state.json")
    sent: list[ActionContext] = []

    async def collect(_spec):
        return [_item("disponible")]

    async def perform(_actions, ctx):
        sent.append(ctx)

    report = asyncio.run(
        execute_crawler(
            _spec(),
            state,
            collect=collect,
            perform_actions=perform,
            dry_run=True,
        )
    )
    assert [item.key for item in report.matches] == ["339133"]
    assert report.notified is False
    assert sent == []
    assert not (tmp_path / "state.json").exists()


def test_read_errors_keep_previous_items_and_alert_once(tmp_path):
    state = StateStore(tmp_path / "state.json")
    sent: list[str] = []

    async def collect_ok(_spec):
        return [_item("agotado")]

    async def collect_bad(_spec):
        raise RuntimeError("timeout")

    async def perform(_actions, ctx):
        sent.append(ctx.kind)

    spec = _spec()
    asyncio.run(execute_crawler(spec, state, collect=collect_ok, perform_actions=perform))

    first_error = asyncio.run(
        execute_crawler(spec, state, collect=collect_bad, perform_actions=perform)
    )
    assert first_error.error is not None
    assert sent == []
    assert state.get(spec.id).items["339133"]["status"] == "agotado"

    second_error = asyncio.run(
        execute_crawler(spec, state, collect=collect_bad, perform_actions=perform)
    )
    assert second_error.notified is True
    assert sent == ["error"]

    third_error = asyncio.run(
        execute_crawler(spec, state, collect=collect_bad, perform_actions=perform)
    )
    assert third_error.notified is False
    assert sent == ["error"]
