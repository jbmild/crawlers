from pathlib import Path

import pytest

from crawler_platform.crawlers.brihet_variations import ParseError, parse_variations_table

FIXTURE = Path(__file__).parent / "fixtures" / "variations.html"


def test_disabled_button_is_agotado_and_enabled_button_is_available():
    items = parse_variations_table(FIXTURE.read_text(encoding="utf-8"))

    assert [item.label for item in items] == [
        "Fascículo N° 01 + piezas",
        "Fascículo N° 02 + piezas",
    ]
    sold_out, available = items
    assert sold_out.key == "339133"
    assert sold_out.status == "agotado"
    assert sold_out.fields["button_text"] == "Agotado"
    assert sold_out.fields["html_button_text"] == "Añadir al carrito"
    assert sold_out.fields["price"] == "$4,500.00"

    assert available.key == "339134"
    assert available.status == "disponible"
    assert available.fields["button_text"] == "Añadir al carrito"
    assert "html_button_text" not in available.fields


def test_explicit_agotado_text_is_sold_out():
    html = """
    <table class="variations-table"><tr>
      <td></td><td>Fascículo N° 03</td><td>$1</td>
      <td><button class="add-to-cart-button">Agotado</button></td>
    </tr></table>
    """
    items = parse_variations_table(html)
    assert items[0].status == "agotado"
    assert items[0].fields["button_text"] == "Agotado"


def test_missing_table_is_an_error_not_an_empty_catalog():
    with pytest.raises(ParseError):
        parse_variations_table("<html><body><p>Agotado</p></body></html>")
