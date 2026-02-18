"""Tests for markdown-to-Google Docs converter."""

from desk.services.markdown_to_docs import (
    MarkdownConverter,
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
