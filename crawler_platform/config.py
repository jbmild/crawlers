from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from crawler_platform.models import ActionSpec, AppConfig, ConditionSpec, CrawlerSpec

MIN_INTERVAL_SECONDS = 60
_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_TRIGGERS = {"on_change", "while_true"}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Carga variables que todavía no están en el entorno."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config(path: Path) -> AppConfig:
    if not path.is_file():
        raise ValueError(f"No existe el archivo de configuración: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("crawlers")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} tiene que definir una lista 'crawlers'")

    crawlers: list[CrawlerSpec] = []
    seen: set[str] = set()
    for entry in entries:
        spec = _parse_crawler(entry, path)
        if spec.id in seen:
            raise ValueError(f"Hay dos crawlers con el id '{spec.id}'")
        seen.add(spec.id)
        crawlers.append(spec)
    return AppConfig(crawlers=crawlers)


def _parse_crawler(entry: object, path: Path) -> CrawlerSpec:
    if not isinstance(entry, dict):
        raise ValueError(f"Cada crawler en {path} tiene que ser un mapa")

    crawler_id = str(entry.get("id") or "").strip()
    if not _ID_RE.fullmatch(crawler_id):
        raise ValueError(
            f"Id de crawler inválido: '{crawler_id}'. Usá minúsculas, números y guiones."
        )

    interval = entry.get("interval_seconds")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise ValueError(f"{crawler_id}: interval_seconds tiene que ser un entero")
    if interval < MIN_INTERVAL_SECONDS:
        raise ValueError(
            f"{crawler_id}: interval_seconds tiene que ser >= {MIN_INTERVAL_SECONDS} "
            "para no martillar el sitio"
        )

    url = str(entry.get("url") or "").strip()
    if not url.startswith("https://"):
        raise ValueError(f"{crawler_id}: url tiene que empezar con https://")

    crawler_type = str(entry.get("type") or "").strip()
    if not crawler_type:
        raise ValueError(f"{crawler_id}: falta type")

    options = entry.get("options") or {}
    if not isinstance(options, dict):
        raise ValueError(f"{crawler_id}: options tiene que ser un mapa")

    error_after = entry.get("error_after", 5)
    if isinstance(error_after, bool) or not isinstance(error_after, int) or error_after < 0:
        raise ValueError(f"{crawler_id}: error_after tiene que ser un entero >= 0")

    actions_raw = entry.get("actions")
    if not isinstance(actions_raw, list) or not actions_raw:
        raise ValueError(f"{crawler_id}: definí al menos una acción")

    return CrawlerSpec(
        id=crawler_id,
        name=str(entry.get("name") or crawler_id).strip(),
        type=crawler_type,
        enabled=bool(entry.get("enabled", True)),
        interval_seconds=interval,
        url=url,
        options={str(k): v for k, v in options.items()},
        condition=_parse_condition(entry.get("condition"), crawler_id),
        actions=[_parse_action(item, crawler_id) for item in actions_raw],
        error_after=error_after,
    )


def _parse_condition(raw: object, crawler_id: str) -> ConditionSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"{crawler_id}: falta condition")
    condition_type = str(raw.get("type") or "").strip()
    field_name = str(raw.get("field") or "").strip()
    value = raw.get("value")
    trigger = str(raw.get("trigger") or "on_change").strip()
    if condition_type != "field_not_equals":
        raise ValueError(
            f"{crawler_id}: la condición '{condition_type}' no existe. "
            "Usá field_not_equals."
        )
    if not field_name:
        raise ValueError(f"{crawler_id}: condition.field es obligatorio")
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{crawler_id}: condition.value tiene que ser un texto")
    if trigger not in _TRIGGERS:
        raise ValueError(
            f"{crawler_id}: condition.trigger tiene que ser on_change o while_true"
        )
    return ConditionSpec(
        type=condition_type,
        field=field_name,
        value=value,
        trigger=trigger,
    )


def _parse_action(raw: object, crawler_id: str) -> ActionSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"{crawler_id}: cada acción tiene que ser un mapa")
    action_type = str(raw.get("type") or "").strip()
    if not action_type:
        raise ValueError(f"{crawler_id}: una acción no tiene type")
    chat_id = raw.get("chat_id")
    if chat_id is not None:
        chat_id = str(chat_id).strip() or None
    options = {
        str(key): str(value)
        for key, value in raw.items()
        if key not in {"type", "chat_id"} and value is not None
    }
    return ActionSpec(type=action_type, chat_id=chat_id, options=options)
