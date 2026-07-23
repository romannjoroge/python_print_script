"""Receipt rendering: payload → ESC/POS byte output."""

from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path

from escpos.printer import Dummy


def render_receipt(payload) -> bytes:
    """Render a job payload into ESC/POS bytes.

    Handles two payload formats:
    - str: base64-encoded image data (JPEG/PNG)
    - dict: structured payload with "type", "content", etc.
    """
    p = Dummy(profile="POS-5890")
    p.set(align="left", bold=False)

    if isinstance(payload, str):
        _render_image(p, payload)
    elif isinstance(payload, dict):
        _render_dict(p, payload)
    else:
        p.text(f"{payload}\n")

    p.cut()
    return p.output


def _render_image(p: Dummy, b64_data: str) -> None:
    """Decode base64 image and print it."""
    try:
        img_bytes = base64.b64decode(b64_data)
    except Exception:
        p.text("(invalid image data)\n")
        return

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        p.image(img)
    except Exception:
        # Fallback: save to temp file and use path-based image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name
        try:
            p.image(tmp_path)
        except Exception:
            p.text(f"(failed to render image)\n")
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def _render_dict(p: Dummy, payload: dict) -> None:
    """Render a structured text payload."""
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
