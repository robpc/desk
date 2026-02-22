"""Tests for markdown-to-Google Docs converter."""

from desk.services.markdown_to_docs import (
    MarkdownConverter,
    TableData,
    _cell_empty_index,
    _empty_table_size,
    _table_total_size,
    markdown_to_requests,
)


class TestMarkdownConverterPlainText:
    """Tests for plain text extraction from markdown."""

    def test_simple_paragraph(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("Hello world")
        assert text == "Hello world\n"

    def test_multiple_paragraphs(self):
        converter = MarkdownConverter()
        text, _ = converter.convert("First paragraph\n\nSecond paragraph")
        assert text == "First paragraph\nSecond paragraph\n"

    def test_empty_input(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("")
        assert text == ""
        assert annotations == []

    def test_heading_text(self):
        converter = MarkdownConverter()
        text, _ = converter.convert("# Hello")
        assert "Hello" in text

    def test_softbreak_produces_newline(self):
        converter = MarkdownConverter()
        text, _ = converter.convert("line one\nline two")
        assert text == "line one\nline two\n"


class TestMarkdownConverterAnnotations:
    """Tests for style annotations produced by the converter."""

    def test_bold_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("**bold text**")
        assert text == "bold text\n"
        bold = [a for a in annotations if a.style_type == "bold"]
        assert len(bold) == 1
        assert bold[0].start == 0
        assert bold[0].end == 9  # len("bold text") in UTF-16

    def test_italic_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("*italic text*")
        assert text == "italic text\n"
        italic = [a for a in annotations if a.style_type == "italic"]
        assert len(italic) == 1
        assert italic[0].start == 0
        assert italic[0].end == 11

    def test_inline_code_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("use `code` here")
        assert text == "use code here\n"
        code = [a for a in annotations if a.style_type == "code"]
        assert len(code) == 1
        assert code[0].start == 4  # "use " = 4
        assert code[0].end == 8  # "use code" = 8

    def test_link_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("[click here](https://example.com)")
        assert text == "click here\n"
        links = [a for a in annotations if a.style_type == "link"]
        assert len(links) == 1
        assert links[0].url == "https://example.com"
        assert links[0].start == 0
        assert links[0].end == 10

    def test_heading_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("# Title")
        heading = [a for a in annotations if a.style_type.startswith("heading_")]
        assert len(heading) == 1
        assert heading[0].style_type == "heading_1"

    def test_h2_annotation(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("## Subtitle")
        heading = [a for a in annotations if a.style_type.startswith("heading_")]
        assert len(heading) == 1
        assert heading[0].style_type == "heading_2"

    def test_nested_bold_in_paragraph(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("before **bold** after")
        assert text == "before bold after\n"
        bold = [a for a in annotations if a.style_type == "bold"]
        assert len(bold) == 1
        assert bold[0].start == 7  # "before " = 7
        assert bold[0].end == 11  # "before bold" = 11

    def test_fenced_code_block(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("```\nprint('hi')\n```")
        assert "print('hi')" in text
        code = [a for a in annotations if a.style_type == "code"]
        assert len(code) == 1

    def test_image_alt_text(self):
        converter = MarkdownConverter()
        text, _ = converter.convert("![alt text](https://example.com/img.png)")
        assert "[alt text]" in text

    def test_horizontal_rule(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("---")
        assert "---" not in text
        hr = [a for a in annotations if a.style_type == "hr"]
        assert len(hr) == 1

    def test_heading_followed_by_paragraph(self):
        converter = MarkdownConverter()
        text, _ = converter.convert("# Title\n\nContent here")
        assert text == "Title\nContent here\n"

    def test_bullet_list_native(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("- item one\n- item two")
        assert "  - " not in text
        assert "item one" in text
        assert "item two" in text
        bullets = [a for a in annotations if a.style_type == "bullet_list"]
        assert len(bullets) == 1

    def test_ordered_list_native(self):
        converter = MarkdownConverter()
        text, annotations = converter.convert("1. first\n2. second")
        assert "first" in text
        assert "second" in text
        numbered = [a for a in annotations if a.style_type == "ordered_list"]
        assert len(numbered) == 1


class TestMarkdownConverterUTF16:
    """Tests for correct UTF-16 offset tracking with multi-byte characters."""

    def test_emoji_offset_tracking(self):
        converter = MarkdownConverter()
        # Emoji (like a smiley) takes 2 UTF-16 code units
        text, annotations = converter.convert("Hi! **bold**")
        assert text == "Hi! bold\n"
        bold = [a for a in annotations if a.style_type == "bold"]
        assert len(bold) == 1
        assert bold[0].start == 4
        assert bold[0].end == 8

    def test_surrogate_pair_character(self):
        converter = MarkdownConverter()
        # U+1F600 (grinning face) is a supplementary character = 2 UTF-16 code units
        text, annotations = converter.convert("\U0001f600 **bold**")
        assert "bold" in text
        bold = [a for a in annotations if a.style_type == "bold"]
        assert len(bold) == 1
        # "\U0001f600 " = 2 (surrogate pair) + 1 (space) = 3 UTF-16 code units
        assert bold[0].start == 3
        assert bold[0].end == 7


class TestMarkdownToRequests:
    """Tests for the markdown_to_requests top-level function."""

    def test_empty_markdown_returns_empty(self):
        result = markdown_to_requests("", base_index=1)
        assert result == []

    def test_plain_text_with_base_index(self):
        result = markdown_to_requests("Hello", base_index=1)
        assert len(result) >= 1
        insert = result[0]
        assert "insertText" in insert
        assert insert["insertText"]["location"]["index"] == 1
        assert insert["insertText"]["text"] == "Hello\n"

    def test_bold_request_with_base_index(self):
        result = markdown_to_requests("**bold**", base_index=1)
        assert len(result) == 2
        insert = result[0]
        assert insert["insertText"]["location"]["index"] == 1
        style = result[1]
        assert "updateTextStyle" in style
        assert style["updateTextStyle"]["textStyle"]["bold"] is True
        assert style["updateTextStyle"]["range"]["startIndex"] == 1
        assert style["updateTextStyle"]["range"]["endIndex"] == 5  # 1 + len("bold")

    def test_italic_request_with_base_index(self):
        result = markdown_to_requests("*italic*", base_index=1)
        style_reqs = [r for r in result if "updateTextStyle" in r]
        assert len(style_reqs) == 1
        assert style_reqs[0]["updateTextStyle"]["textStyle"]["italic"] is True

    def test_code_request_with_base_index(self):
        result = markdown_to_requests("`code`", base_index=1)
        style_reqs = [r for r in result if "updateTextStyle" in r]
        assert len(style_reqs) == 1
        ts = style_reqs[0]["updateTextStyle"]["textStyle"]
        assert ts["weightedFontFamily"]["fontFamily"] == "Courier New"

    def test_link_request_with_base_index(self):
        result = markdown_to_requests("[text](https://example.com)", base_index=1)
        style_reqs = [r for r in result if "updateTextStyle" in r]
        assert len(style_reqs) == 1
        ts = style_reqs[0]["updateTextStyle"]["textStyle"]
        assert ts["link"]["url"] == "https://example.com"

    def test_heading_request_with_base_index(self):
        result = markdown_to_requests("# Title", base_index=1)
        para_reqs = [r for r in result if "updateParagraphStyle" in r]
        assert len(para_reqs) == 1
        ps = para_reqs[0]["updateParagraphStyle"]["paragraphStyle"]
        assert ps["namedStyleType"] == "HEADING_1"

    def test_base_index_offsets_all_ranges(self):
        result = markdown_to_requests("**bold**", base_index=10)
        style = result[1]
        rng = style["updateTextStyle"]["range"]
        assert rng["startIndex"] == 10
        assert rng["endIndex"] == 14  # 10 + len("bold")

    def test_mixed_formatting(self):
        result = markdown_to_requests("**bold** and *italic*", base_index=1)
        text_styles = [r for r in result if "updateTextStyle" in r]
        assert len(text_styles) == 2
        bold = [r for r in text_styles if r["updateTextStyle"]["textStyle"].get("bold")]
        italic = [r for r in text_styles if r["updateTextStyle"]["textStyle"].get("italic")]
        assert len(bold) == 1
        assert len(italic) == 1

    def test_hr_request_produces_border(self):
        result = markdown_to_requests("---", base_index=1)
        para_reqs = [r for r in result if "updateParagraphStyle" in r]
        assert len(para_reqs) == 1
        ps = para_reqs[0]["updateParagraphStyle"]["paragraphStyle"]
        assert "borderBottom" in ps

    def test_bullet_list_request(self):
        result = markdown_to_requests("- one\n- two", base_index=1)
        bullet_reqs = [r for r in result if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        preset = bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
        assert preset == "BULLET_DISC_CIRCLE_SQUARE"

    def test_ordered_list_request(self):
        result = markdown_to_requests("1. one\n2. two", base_index=1)
        bullet_reqs = [r for r in result if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        preset = bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
        assert preset == "NUMBERED_DECIMAL_ALPHA_ROMAN"

    def test_crlf_normalized(self):
        result = markdown_to_requests("Hello\r\nWorld", base_index=1)
        insert_text = result[0]["insertText"]["text"]
        assert "\r" not in insert_text

    def test_tab_id_injected_into_insert_location(self):
        result = markdown_to_requests("Hello", base_index=1, tab_id="t.1")
        insert = result[0]["insertText"]
        assert insert["location"]["tabId"] == "t.1"
        assert insert["location"]["index"] == 1

    def test_tab_id_injected_into_style_ranges(self):
        result = markdown_to_requests("**bold**", base_index=1, tab_id="t.1")
        style = result[1]["updateTextStyle"]
        assert style["range"]["tabId"] == "t.1"

    def test_tab_id_injected_into_heading_ranges(self):
        result = markdown_to_requests("# Title", base_index=1, tab_id="t.1")
        para_reqs = [r for r in result if "updateParagraphStyle" in r]
        assert len(para_reqs) == 1
        assert para_reqs[0]["updateParagraphStyle"]["range"]["tabId"] == "t.1"

    def test_tab_id_injected_into_bullet_ranges(self):
        result = markdown_to_requests("- one\n- two", base_index=1, tab_id="t.1")
        bullet_reqs = [r for r in result if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        assert bullet_reqs[0]["createParagraphBullets"]["range"]["tabId"] == "t.1"

    def test_no_tab_id_when_none(self):
        result = markdown_to_requests("**bold**", base_index=1, tab_id=None)
        insert = result[0]["insertText"]
        assert "tabId" not in insert["location"]
        style = result[1]["updateTextStyle"]
        assert "tabId" not in style["range"]


class TestDocsEditingUtils:
    """Tests for the docs_editing utility functions."""

    def test_normalize_text_crlf(self):
        from desk.services.docs_editing import normalize_text

        assert normalize_text("a\r\nb") == "a\nb"

    def test_normalize_text_lone_cr(self):
        from desk.services.docs_editing import normalize_text

        assert normalize_text("a\rb") == "a\nb"

    def test_normalize_text_nfc(self):
        import unicodedata

        from desk.services.docs_editing import normalize_text

        # e + combining acute accent should become e-acute (NFC)
        decomposed = "e\u0301"
        result = normalize_text(decomposed)
        assert result == unicodedata.normalize("NFC", decomposed)

    def test_utf16_len_ascii(self):
        from desk.services.docs_editing import utf16_len

        assert utf16_len("hello") == 5

    def test_utf16_len_bmp_char(self):
        from desk.services.docs_editing import utf16_len

        # e-acute is BMP = 1 UTF-16 code unit
        assert utf16_len("\u00e9") == 1

    def test_utf16_len_supplementary(self):
        from desk.services.docs_editing import utf16_len

        # U+1F600 grinning face = 2 UTF-16 code units (surrogate pair)
        assert utf16_len("\U0001f600") == 2

    def test_utf16_len_empty(self):
        from desk.services.docs_editing import utf16_len

        assert utf16_len("") == 0

    def test_utf16_len_mixed(self):
        from desk.services.docs_editing import utf16_len

        # "a" (1) + U+1F600 (2) + "b" (1) = 4
        assert utf16_len("a\U0001f600b") == 4


# ── Table parsing tests ──────────────────────────────────────────────


class TestTableParsing:
    """Tests for markdown table parsing into segments."""

    def test_simple_table_produces_table_segment(self):
        converter = MarkdownConverter()
        segments = converter.convert_to_segments("| A | B |\n|---|---|\n| 1 | 2 |")
        table_segs = [s for s in segments if s.segment_type == "table"]
        assert len(table_segs) == 1
        table = table_segs[0].table
        assert table is not None
        assert table.headers == ["A", "B"]
        assert table.rows == [["1", "2"]]
        assert table.num_cols == 2
        assert table.num_rows == 2

    def test_table_with_multiple_body_rows(self):
        md = "| H1 | H2 |\n|---|---|\n| a | b |\n| c | d |\n| e | f |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        assert table.headers == ["H1", "H2"]
        assert table.rows == [["a", "b"], ["c", "d"], ["e", "f"]]
        assert table.num_rows == 4  # 1 header + 3 body

    def test_table_with_three_columns(self):
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        assert table.num_cols == 3
        assert table.headers == ["A", "B", "C"]
        assert table.rows == [["1", "2", "3"]]

    def test_text_before_table(self):
        md = "Hello world\n\n| A | B |\n|---|---|\n| 1 | 2 |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        assert len(segments) == 2
        assert segments[0].segment_type == "text"
        assert "Hello world" in segments[0].text
        assert segments[1].segment_type == "table"

    def test_text_after_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n\nGoodbye"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        assert len(segments) == 2
        assert segments[0].segment_type == "table"
        assert segments[1].segment_type == "text"
        assert "Goodbye" in segments[1].text

    def test_text_table_text(self):
        md = "Before\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        assert len(segments) == 3
        assert segments[0].segment_type == "text"
        assert segments[1].segment_type == "table"
        assert segments[2].segment_type == "text"

    def test_multiple_tables(self):
        md = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            "Some text\n\n"
            "| C | D |\n|---|---|\n| 3 | 4 |"
        )
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        tables = [s for s in segments if s.segment_type == "table"]
        assert len(tables) == 2

    def test_bold_in_cell(self):
        md = "| **Bold** | Normal |\n|---|---|\n| x | y |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        assert table.headers == ["Bold", "Normal"]
        # First header cell should have a bold annotation
        bold = [a for a in table.header_annotations[0] if a.style_type == "bold"]
        assert len(bold) == 1
        assert bold[0].start == 0
        assert bold[0].end == 4  # len("Bold")

    def test_italic_in_cell(self):
        md = "| *Italic* | Normal |\n|---|---|\n| x | y |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        italic = [a for a in table.header_annotations[0] if a.style_type == "italic"]
        assert len(italic) == 1

    def test_code_in_cell(self):
        md = "| `code` | Normal |\n|---|---|\n| x | y |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        code = [a for a in table.header_annotations[0] if a.style_type == "code"]
        assert len(code) == 1

    def test_link_in_cell(self):
        md = "| [link](http://x.com) | Normal |\n|---|---|\n| x | y |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        links = [a for a in table.header_annotations[0] if a.style_type == "link"]
        assert len(links) == 1
        assert links[0].url == "http://x.com"

    def test_empty_cell(self):
        md = "| A | |\n|---|---|\n| | B |"
        converter = MarkdownConverter()
        segments = converter.convert_to_segments(md)
        table = segments[0].table
        assert table is not None
        assert table.headers == ["A", ""]
        assert table.rows == [["", "B"]]

    def test_convert_backwards_compat_ignores_tables(self):
        """convert() returns flat text without table content."""
        converter = MarkdownConverter()
        text, annotations = converter.convert(
            "Hello\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nWorld"
        )
        assert "Hello" in text
        assert "World" in text
        # Table content should not appear in flat text
        assert "|" not in text


# ── Table index calculation tests ────────────────────────────────────


class TestTableIndexCalculation:
    """Tests for the deterministic cell index formula."""

    def test_empty_table_size_2x2(self):
        # 2 rows * (2*2 + 1) + 3 = 2*5 + 3 = 13
        assert _empty_table_size(2, 2) == 13

    def test_empty_table_size_3x3(self):
        # 3 * (2*3 + 1) + 3 = 3*7 + 3 = 24
        assert _empty_table_size(3, 3) == 24

    def test_empty_table_size_1x1(self):
        # 1 * (2*1 + 1) + 3 = 3 + 3 = 6
        assert _empty_table_size(1, 1) == 6

    def test_cell_index_2x2_at_index_1(self):
        """Verify against known indices from Google Docs API research."""
        # 2x2 table at index 1: cell(0,0)=5, cell(0,1)=7, cell(1,0)=10, cell(1,1)=12
        assert _cell_empty_index(1, 0, 0, 2) == 5
        assert _cell_empty_index(1, 0, 1, 2) == 7
        assert _cell_empty_index(1, 1, 0, 2) == 10
        assert _cell_empty_index(1, 1, 1, 2) == 12

    def test_cell_index_3x2_at_index_1(self):
        """3 rows, 2 columns at index 1."""
        # Row stride = 2*2 + 1 = 5
        # cell(0,0) = 1+4 = 5, cell(0,1) = 7
        # cell(1,0) = 1+4+5 = 10, cell(1,1) = 12
        # cell(2,0) = 1+4+10 = 15, cell(2,1) = 17
        assert _cell_empty_index(1, 0, 0, 2) == 5
        assert _cell_empty_index(1, 0, 1, 2) == 7
        assert _cell_empty_index(1, 1, 0, 2) == 10
        assert _cell_empty_index(1, 1, 1, 2) == 12
        assert _cell_empty_index(1, 2, 0, 2) == 15
        assert _cell_empty_index(1, 2, 1, 2) == 17

    def test_cell_index_with_offset_base(self):
        """Table at a non-1 base index."""
        # At index 20: cell(0,0) = 20+4 = 24
        assert _cell_empty_index(20, 0, 0, 2) == 24
        assert _cell_empty_index(20, 0, 1, 2) == 26

    def test_table_total_size_empty_cells(self):
        table = TableData(
            headers=["A", "B"],
            header_annotations=[[], []],
            rows=[["", ""]],
            row_annotations=[[[]]],
        )
        # Fix: row_annotations needs same shape
        table.row_annotations = [[[], []]]
        # empty size = 2*(2*2+1)+3 = 13, content = 1+1+0+0 = 2
        assert _table_total_size(table) == 13 + 2  # "A" + "B" = 2 chars

    def test_table_total_size_with_content(self):
        table = TableData(
            headers=["Name", "Age"],
            header_annotations=[[], []],
            rows=[["Alice", "30"]],
            row_annotations=[[[], []]],
        )
        # empty = 2*(2*2+1)+3 = 13
        # content = 4+3+5+2 = 14 (Name, Age, Alice, 30)
        assert _table_total_size(table) == 13 + 14


# ── Table request generation tests ───────────────────────────────────


class TestTableRequests:
    """Tests for batchUpdate request generation with tables."""

    def test_simple_table_generates_insert_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = markdown_to_requests(md, base_index=1)
        table_reqs = [r for r in result if "insertTable" in r]
        assert len(table_reqs) == 1
        req = table_reqs[0]["insertTable"]
        assert req["rows"] == 2
        assert req["columns"] == 2
        assert req["location"]["index"] == 1

    def test_table_cell_inserts_in_reverse_order(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = markdown_to_requests(md, base_index=1)
        cell_inserts = [r for r in result if "insertText" in r]
        # Should have 4 cell inserts (A, B, 1, 2) in reverse order
        assert len(cell_inserts) == 4
        indices = [r["insertText"]["location"]["index"] for r in cell_inserts]
        # Reverse order means indices should be descending
        assert indices == sorted(indices, reverse=True)

    def test_table_cell_indices_match_formula(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = markdown_to_requests(md, base_index=1)
        cell_inserts = [r for r in result if "insertText" in r]
        # Reverse order: cell(1,1)=12, cell(1,0)=10, cell(0,1)=7, cell(0,0)=5
        texts_and_indices = [
            (r["insertText"]["text"], r["insertText"]["location"]["index"])
            for r in cell_inserts
        ]
        assert ("2", 12) in texts_and_indices
        assert ("1", 10) in texts_and_indices
        assert ("B", 7) in texts_and_indices
        assert ("A", 5) in texts_and_indices

    def test_table_headers_are_bolded(self):
        md = "| H1 | H2 |\n|---|---|\n| a | b |"
        result = markdown_to_requests(md, base_index=1)
        bold_reqs = [
            r for r in result
            if "updateTextStyle" in r
            and r["updateTextStyle"]["textStyle"].get("bold") is True
        ]
        # Should have bold for H1 and H2
        assert len(bold_reqs) >= 2

    def test_text_before_table(self):
        md = "Hello\n\n| A | B |\n|---|---|\n| 1 | 2 |"
        result = markdown_to_requests(md, base_index=1)
        # First request should be insertText for "Hello\n"
        assert result[0]["insertText"]["text"] == "Hello\n"
        assert result[0]["insertText"]["location"]["index"] == 1
        # Then insertTable at cursor after text
        table_reqs = [r for r in result if "insertTable" in r]
        assert len(table_reqs) == 1
        # "Hello\n" = 6 UTF-16 units, so table starts at 1+6=7
        assert table_reqs[0]["insertTable"]["location"]["index"] == 7

    def test_text_after_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n\nGoodbye"
        result = markdown_to_requests(md, base_index=1)
        # Should have insertTable, cell inserts, and then insertText for "Goodbye\n"
        text_inserts = [
            r for r in result
            if "insertText" in r and r["insertText"]["text"] == "Goodbye\n"
        ]
        assert len(text_inserts) == 1

    def test_base_index_offsets_table(self):
        md = "| X |\n|---|\n| Y |"
        result = markdown_to_requests(md, base_index=10)
        table_req = [r for r in result if "insertTable" in r][0]
        assert table_req["insertTable"]["location"]["index"] == 10

    def test_empty_cell_no_insert(self):
        md = "| A | |\n|---|---|\n| | B |"
        result = markdown_to_requests(md, base_index=1)
        cell_inserts = [r for r in result if "insertText" in r]
        # Only cells with content get inserts: A and B
        texts = [r["insertText"]["text"] for r in cell_inserts]
        assert "A" in texts
        assert "B" in texts
        assert "" not in texts

    def test_formatting_in_body_cell(self):
        md = "| H |\n|---|\n| **bold** |"
        result = markdown_to_requests(md, base_index=1)
        bold_reqs = [
            r for r in result
            if "updateTextStyle" in r
            and r["updateTextStyle"]["textStyle"].get("bold") is True
        ]
        # Should have bold for header "H" AND for body cell "bold"
        assert len(bold_reqs) >= 2

    def test_multiple_tables(self):
        md = (
            "| A |\n|---|\n| 1 |\n\n"
            "Between\n\n"
            "| B |\n|---|\n| 2 |"
        )
        result = markdown_to_requests(md, base_index=1)
        table_reqs = [r for r in result if "insertTable" in r]
        assert len(table_reqs) == 2
        # Second table should be at a higher index than the first
        assert (
            table_reqs[1]["insertTable"]["location"]["index"]
            > table_reqs[0]["insertTable"]["location"]["index"]
        )
