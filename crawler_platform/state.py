from __future__ import annotations

import json
from pathlib import Path

from crawler_platform.models import CrawlerState, Item


class StateStore:
    """Estado por crawler para no repetir el mismo aviso en cada ciclo."""

    def __init__(self, path: Path):
        self.path = path
        self.crawlers: dict[str, CrawlerState] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self.crawlers = {}
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        loaded: dict[str, CrawlerState] = {}
        for crawler_id, data in raw.get("crawlers", {}).items():
            items = {
                key: {str(field): str(value) for field, value in fields.items()}
                for key, fields in data.get("items", {}).items()
            }
            loaded[str(crawler_id)] = CrawlerState(
                items=items,
                last_run=data.get("last_run"),
                last_error=data.get("last_error"),
                consecutive_errors=int(data.get("consecutive_errors") or 0),
                error_notified=bool(data.get("error_notified")),
            )
        self.crawlers = loaded

    def get(self, crawler_id: str) -> CrawlerState:
        if crawler_id not in self.crawlers:
            self.crawlers[crawler_id] = CrawlerState()
        return self.crawlers[crawler_id]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "crawlers": {
                crawler_id: {
                    "items": record.items,
                    "last_run": record.last_run,
                    "last_error": record.last_error,
                    "consecutive_errors": record.consecutive_errors,
                    "error_notified": record.error_notified,
                }
                for crawler_id, record in self.crawlers.items()
            },
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def snapshot(item: Item) -> dict[str, str]:
    data = {"status": item.status, "label": item.label}
    data.update(item.fields)
    return data
