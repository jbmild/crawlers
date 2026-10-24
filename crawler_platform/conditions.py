from __future__ import annotations

from crawler_platform.models import ConditionSpec, Item


def field_value(item: Item, field_name: str) -> str:
    if field_name == "status":
        return item.status
    if field_name == "label":
        return item.label
    return item.fields.get(field_name, "")


def matching_items(
    items: list[Item],
    previous: dict[str, dict[str, str]],
    condition: ConditionSpec,
) -> list[Item]:
    """Devuelve los ítems que cumplen la condición y hay que accionar.

    `on_change` avisa cuando el campo deja de valer `condition.value`
    (o cuando el ítem aparece por primera vez ya en ese estado).
    `while_true` avisa en cada ciclo mientras siga cumpliéndose.
    """
    if condition.type != "field_not_equals":
        raise ValueError(f"Condición desconocida: {condition.type}")
    if condition.trigger not in {"on_change", "while_true"}:
        raise ValueError(f"trigger desconocido: {condition.trigger}")

    matched: list[Item] = []
    for item in items:
        current = field_value(item, condition.field)
        if current == condition.value:
            continue
        if condition.trigger == "while_true":
            matched.append(item)
            continue
        prev = previous.get(item.key)
        if prev is None:
            matched.append(item)
            continue
        prev_value = prev.get(condition.field)
        if prev_value == condition.value:
            matched.append(item)
    return matched
