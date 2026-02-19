"""Tests for src/ui/widgets.py — TUI box-drawing primitives."""
from src.ui.widgets import (
    C, strip_ansi, center, cols,
    box_top, box_mid, box_bot, box_row, box_kv, box_section,
)


class TestStripAnsi:
    def test_removes_color_codes(self):
        assert strip_ansi(f"{C.RED}hello{C.RST}") == "hello"

    def test_no_ansi_unchanged(self):
        assert strip_ansi("plain text") == "plain text"

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_multiple_codes(self):
        text = f"{C.BOLD}{C.GRN}bold green{C.RST}"
        assert strip_ansi(text) == "bold green"


class TestCenter:
    def test_centers_plain_text(self):
        result = center("hi", 10)
        assert len(result) == 10
        assert "hi" in result

    def test_centers_ansi_text(self):
        text = f"{C.RED}hi{C.RST}"
        result = center(text, 10)
        assert len(strip_ansi(result)) == 10

    def test_text_wider_than_width(self):
        result = center("hello world", 5)
        assert "hello world" in result


class TestCols:
    def test_returns_positive_int(self):
        w = cols()
        assert isinstance(w, int)
        assert w > 0


class TestBoxFunctions:
    def test_box_top_corners(self):
        raw = strip_ansi(box_top(20))
        assert raw.strip()[0] == '\u250c'
        assert raw.strip()[-1] == '\u2510'

    def test_box_bot_corners(self):
        raw = strip_ansi(box_bot(20))
        assert raw.strip()[0] == '\u2514'
        assert raw.strip()[-1] == '\u2518'

    def test_box_mid_corners(self):
        raw = strip_ansi(box_mid(20))
        assert raw.strip()[0] == '\u251c'
        assert raw.strip()[-1] == '\u2524'

    def test_box_row_wraps_content(self):
        raw = strip_ansi(box_row("test", 20))
        assert 'test' in raw
        assert raw.strip()[0] == '\u2502'
        assert raw.strip()[-1] == '\u2502'

    def test_box_kv_formats_key_value(self):
        raw = strip_ansi(box_kv("Key", "Value", 40))
        assert "Key:" in raw
        assert "Value" in raw

    def test_box_section_embeds_label(self):
        raw = strip_ansi(box_section("TOOLS", 40))
        assert "TOOLS" in raw
