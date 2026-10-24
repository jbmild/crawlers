from __future__ import annotations

import httpx

from crawler_platform.crawlers.brihet_variations import BrihetVariationsCrawler

REGISTRY = {
    BrihetVariationsCrawler.type_name: BrihetVariationsCrawler,
}


def get_crawler(type_name: str, client: httpx.AsyncClient):
    try:
        crawler_cls = REGISTRY[type_name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY)) or "(ninguno)"
        raise ValueError(
            f"Tipo de crawler desconocido: '{type_name}'. Tipos disponibles: {known}"
        ) from exc
    return crawler_cls(client)
