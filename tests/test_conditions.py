from crawler_platform.conditions import matching_items
from crawler_platform.models import ConditionSpec, Item


def _condition(trigger: str = "on_change") -> ConditionSpec:
    return ConditionSpec(
        type="field_not_equals",
        field="status",
        value="agotado",
        trigger=trigger,
    )


def _item(status: str, key: str = "339133") -> Item:
    return Item(key=key, label=f"Fascículo {key}", status=status, fields={"button_text": status})


def test_on_change_ignores_sold_out_and_alerts_when_it_becomes_available():
    sold_out = {"339133": {"status": "agotado", "label": "Fascículo 339133"}}

    assert matching_items([_item("agotado")], {}, _condition()) == []
    assert matching_items([_item("agotado")], sold_out, _condition()) == []

    first_seen_available = matching_items([_item("disponible")], {}, _condition())
    assert [item.key for item in first_seen_available] == ["339133"]

    changed = matching_items([_item("disponible")], sold_out, _condition())
    assert [item.key for item in changed] == ["339133"]

    already = {"339133": {"status": "disponible"}}
    assert matching_items([_item("disponible")], already, _condition()) == []


def test_while_true_alerts_on_every_cycle():
    previous = {"339133": {"status": "disponible"}}
    matches = matching_items([_item("disponible")], previous, _condition("while_true"))
    assert len(matches) == 1


def test_only_the_edition_that_changed_is_included():
    previous = {
        "1": {"status": "agotado"},
        "2": {"status": "disponible"},
    }
    items = [_item("disponible", "1"), _item("disponible", "2")]
    matches = matching_items(items, previous, _condition())
    assert [item.key for item in matches] == ["1"]
