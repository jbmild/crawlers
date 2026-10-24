from pathlib import Path

import pytest

from crawler_platform.config import load_config
from crawler_platform.models import Item, RunReport
from crawler_platform.scheduler import describe_report, validate_runtime

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "config" / "crawlers.yaml"


def test_shipped_config_is_valid():
    config = load_config(CONFIG)
    assert [crawler.id for crawler in config.crawlers] == ["iron-man-mark-iii"]
    crawler = config.crawlers[0]
    assert crawler.type == "brihet_variations"
    assert crawler.interval_seconds == 300
    assert crawler.url.endswith("/iron-man-construi-la-armadura-mark-iii/")
    assert crawler.condition.field == "status"
    assert crawler.condition.value == "agotado"
    assert crawler.condition.trigger == "on_change"
    assert crawler.actions[0].type == "telegram"
    validate_runtime(config, require_secrets=False)


def test_status_line_uses_singular_for_one_edition():
    report = RunReport(
        crawler_id="iron-man-mark-iii",
        items=[Item(key="1", label="Fascículo N° 01 + piezas", status="agotado")],
        matches=[],
        notified=False,
    )
    assert describe_report(report) == (
        "iron-man-mark-iii: 1 edición, 0 disponibles, a notificar: ninguno"
    )


def test_interval_cannot_hammer_the_site(tmp_path):
    path = tmp_path / "crawlers.yaml"
    path.write_text(
        """
crawlers:
  - id: demasiado-rapido
    type: brihet_variations
    interval_seconds: 5
    url: https://example.com/item
    condition:
      type: field_not_equals
      field: status
      value: agotado
    actions:
      - type: telegram
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="interval_seconds"):
        load_config(path)
