from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from crawler_platform.models import CrawlerSpec, Item

logger = logging.getLogger(__name__)

USER_AGENT = "crawlers-platform/1.0 (monitor personal de stock; contacto local)"


class ParseError(Exception):
    """La página cargó, pero no tiene la tabla de fascículos esperada."""


class BrihetVariationsCrawler:
    """Lee la tabla de fascículos de una ficha de Brihet.

    El botón se publica como "Añadir al carrito". Si está deshabilitado, un
    script de la página le cambia el texto a "Agotado" en el navegador. Acá
    el estado agotado es el atributo disabled o el texto Agotado.
    """

    type_name = "brihet_variations"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def collect(self, spec: CrawlerSpec) -> list[Item]:
        response = await self.client.get(
            spec.url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-AR,es;q=0.9",
            },
            follow_redirects=True,
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} al leer {spec.url}")
        return parse_variations_table(response.text)


def parse_variations_table(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.variations-table")
    if not tables:
        raise ParseError(
            "No se encontró la tabla de fascículos (table.variations-table)"
        )

    items: list[Item] = []
    seen: set[str] = set()
    for table in tables:
        for row in table.select("tr"):
            item = _parse_row(row)
            if item is None:
                continue
            if item.key in seen:
                logger.warning("Fila duplicada en la tabla de fascículos: %s", item.key)
                continue
            seen.add(item.key)
            items.append(item)
    return items


def _parse_row(row) -> Item | None:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 4:
        return None
    label = _clean(cells[1].get_text("", strip=True))
    price = _clean(cells[2].get_text("", strip=True))
    button = cells[3].find("button", class_="add-to-cart-button") or cells[3].find("button")
    if button is None or not label:
        return None

    raw_text = _clean(button.get_text("", strip=True))
    sold_out = _is_sold_out(button, raw_text)
    visible = "Agotado" if sold_out else raw_text
    product_input = cells[3].find("input", attrs={"name": "add-to-cart"})
    product_id = ""
    if product_input is not None and product_input.get("value"):
        product_id = str(product_input["value"]).strip()

    fields = {
        "price": price,
        "button_text": visible,
        "product_id": product_id,
    }
    if raw_text and raw_text != visible:
        fields["html_button_text"] = raw_text

    return Item(
        key=product_id or label,
        label=label,
        status="agotado" if sold_out else "disponible",
        fields=fields,
    )


def _clean(text: str) -> str:
    return " ".join(text.split())


def _is_sold_out(button, raw_text: str) -> bool:
    if raw_text.casefold() == "agotado":
        return True
    if button.has_attr("disabled"):
        return True
    classes = button.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return any(str(css_class).casefold() == "disabled" for css_class in classes)
