from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    """Una observación de un crawler. `status` es el valor que evalúa la condición."""

    key: str
    label: str
    status: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ConditionSpec:
    type: str
    field: str
    value: str
    trigger: str


@dataclass
class ActionSpec:
    type: str
    chat_id: str | None = None
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class CrawlerSpec:
    id: str
    name: str
    type: str
    enabled: bool
    interval_seconds: int
    url: str
    options: dict
    condition: ConditionSpec
    actions: list[ActionSpec]
    error_after: int = 5


@dataclass
class AppConfig:
    crawlers: list[CrawlerSpec]


@dataclass
class ActionContext:
    crawler_id: str
    crawler_name: str
    url: str
    matched_items: list[Item]
    all_items: list[Item]
    kind: str = "match"
    error: str | None = None
    consecutive_errors: int = 0


@dataclass
class CrawlerState:
    items: dict[str, dict[str, str]] = field(default_factory=dict)
    last_run: str | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    error_notified: bool = False


@dataclass
class RunReport:
    crawler_id: str
    items: list[Item]
    matches: list[Item]
    notified: bool
    error: str | None = None
