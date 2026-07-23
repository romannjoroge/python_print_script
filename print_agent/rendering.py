"""Receipt rendering: payload → ESC/POS byte output."""

from __future__ import annotations

from escpos.printer import Dummy


def render_receipt(payload: dict) -> bytes:
    """Render a job payload into ESC/POS bytes.

    The Dummy printer captures output as bytes without needing a device.
    """
    p = Dummy()

    # Init
    p.set(align="left", bold=False)

    content = payload.get("content", "")
    text_type = payload.get("type", "text")

    if text_type == "text":
        bold = payload.get("bold", False)
        align = payload.get("align", "left")
        feed = payload.get("feed_lines", 0)

        if bold:
            p.set(bold=True)

        if align in ("left", "center", "right"):
            p.set(align=align)

        if content:
            p.text(f"{content}\n")

        if feed > 0:
            p.ln(feed)

        p.set(bold=False)
        p.set(align="left")

    elif content:
        p.text(f"{content}\n")

    # Cut
    p.cut()

    return p.output
