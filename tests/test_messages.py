from crawler_platform.messages import render_message
from crawler_platform.models import ActionContext, Item


def test_stock_message_names_the_edition_and_the_page():
    text = render_message(
        ActionContext(
            crawler_id="iron-man-mark-iii",
            crawler_name="Iron Man – Construí la armadura Mark III",
            url="https://brihet.com.ar/producto/iron-man-construi-la-armadura-mark-iii/",
            matched_items=[
                Item(
                    key="339133",
                    label="Fascículo N° 01 + piezas",
                    status="disponible",
                    fields={"price": "$4,500.00", "button_text": "Añadir al carrito"},
                )
            ],
            all_items=[],
        )
    )
    assert "Iron Man" in text
    assert "Fascículo N° 01 + piezas" in text
    assert "$4,500.00" in text
    assert "Añadir al carrito" in text
    assert text.endswith("https://brihet.com.ar/producto/iron-man-construi-la-armadura-mark-iii/")
