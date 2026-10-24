from __future__ import annotations

import httpx

from crawler_platform.actions.telegram import TelegramAction

REGISTRY = {
    TelegramAction.type_name: TelegramAction,
}


def get_action(type_name: str, client: httpx.AsyncClient):
    try:
        action_cls = REGISTRY[type_name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY)) or "(ninguna)"
        raise ValueError(
            f"Tipo de acción desconocido: '{type_name}'. Acciones disponibles: {known}"
        ) from exc
    return action_cls(client)
