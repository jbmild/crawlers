from __future__ import annotations

from crawler_platform.models import ActionContext, Item


def render_message(ctx: ActionContext) -> str:
    if ctx.kind == "error":
        return _render_error(ctx)
    return _render_match(ctx)


def _render_match(ctx: ActionContext) -> str:
    lines = [
        ctx.crawler_name,
        "",
        "Ya no figura como Agotado:",
    ]
    for item in ctx.matched_items:
        lines.append(_format_item(item))
    lines.append("")
    lines.append(ctx.url)
    return "\n".join(lines)


def _format_item(item: Item) -> str:
    price = item.fields.get("price", "")
    button = item.fields.get("button_text", "")
    extra = f" — {price}" if price else ""
    line = f"• {item.label}{extra}"
    if button:
        line += f"\n  Botón: {button}"
    return line


def _render_error(ctx: ActionContext) -> str:
    detail = (ctx.error or "error desconocido")[:500]
    return (
        f"{ctx.crawler_name}\n\n"
        f"El crawler falló {ctx.consecutive_errors} veces seguidas y no pude leer la página.\n"
        f"{detail}\n\n"
        f"{ctx.url}"
    )
