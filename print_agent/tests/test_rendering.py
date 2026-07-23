"""Tests for receipt rendering (payload → ESC/POS bytes)."""

import pytest

from print_agent.rendering import render_receipt


class TestRenderReceipt:
    """Test that payloads produce valid ESC/POS byte output."""

    def test_simple_text_payload(self):
        payload = {
            "type": "text",
            "content": "Hello, World!",
        }
        output = render_receipt(payload)
        assert isinstance(output, bytes)
        assert len(output) > 0

    def test_text_contains_content_bytes(self):
        payload = {
            "type": "text",
            "content": "Test Receipt",
        }
        output = render_receipt(payload)
        assert b"Test Receipt" in output

    def test_esc_commands_present(self):
        """Every receipt contains ESC/POS formatting commands."""
        payload = {"type": "text", "content": "X"}
        output = render_receipt(payload)
        # Should contain ESC commands (0x1b prefix) and GS commands (0x1d)
        assert b"\x1b" in output
        assert b"\x1d" in output

    def test_cut_command_present(self):
        """Receipts should end with a cut command."""
        payload = {"type": "text", "content": "X"}
        output = render_receipt(payload)
        # GS V = 0x1d 0x56 followed by 0x00 (full cut)
        assert output[-3:] == b"\x1d\x56\x00"

    def test_bold_text(self):
        payload = {
            "type": "text",
            "content": "Bold",
            "bold": True,
        }
        output = render_receipt(payload)
        # ESC E 1 = 0x1b 0x45 0x01 (bold on)
        assert b"\x1b\x45\x01" in output

    def test_center_alignment(self):
        payload = {
            "type": "text",
            "content": "Center",
            "align": "center",
        }
        output = render_receipt(payload)
        # ESC a 1 = 0x1b 0x61 0x01 (center)
        assert b"\x1b\x61\x01" in output

    def test_right_alignment(self):
        payload = {
            "type": "text",
            "content": "Right",
            "align": "right",
        }
        output = render_receipt(payload)
        # ESC a 2 = 0x1b 0x61 0x02 (right)
        assert b"\x1b\x61\x02" in output

    def test_left_alignment(self):
        payload = {
            "type": "text",
            "content": "Left",
            "align": "left",
        }
        output = render_receipt(payload)
        # ESC a 0 = 0x1b 0x61 0x00 (left)
        assert b"\x1b\x61\x00" in output

    def test_newline_after_text(self):
        payload = {"type": "text", "content": "Line"}
        output = render_receipt(payload)
        assert b"Line\n" in output

    def test_multiple_lines(self):
        payload = {
            "type": "text",
            "content": "Line1\nLine2\nLine3",
        }
        output = render_receipt(payload)
        assert b"Line1\n" in output
        assert b"Line2\n" in output
        assert b"Line3\n" in output

    def test_empty_content(self):
        payload = {"type": "text", "content": ""}
        output = render_receipt(payload)
        assert isinstance(output, bytes)
        assert b"\x1b" in output

    def test_feed_lines(self):
        payload = {
            "type": "text",
            "content": "Before",
            "feed_lines": 3,
        }
        output = render_receipt(payload)
        # LF = 0x0a, three of them
        assert b"\x0a\x0a\x0a" in output

    def test_unknown_type_returns_esc_and_cut(self):
        payload = {"type": "unknown_format", "data": "something"}
        output = render_receipt(payload)
        assert b"\x1b" in output
        assert output[-3:] == b"\x1d\x56\x00"

    def test_missing_content_uses_empty_string(self):
        payload = {"type": "text"}
        output = render_receipt(payload)
        assert isinstance(output, bytes)
        assert b"\x1b" in output
