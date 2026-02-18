"""Tests for docs editing utilities and markdown conversion."""

import pytest

from desk.services.docs_editing import normalize_text, utf16_len, utf16_offset


class TestUtf16Len:
    """Tests for UTF-16 code unit length calculation."""

    def test_ascii_string(self):
        assert utf16_len("hello") == 5

    def test_empty_string(self):
        assert utf16_len("") == 0

    def test_bmp_character(self):
        # e-acute (U+00E9) is 1 UTF-16 code unit
        assert utf16_len("\u00e9") == 1

    def test_emoji_supplementary(self):
        # Grinning face (U+1F600) is 2 UTF-16 code units (surrogate pair)
        assert utf16_len("\U0001F600") == 2

    def test_mixed_content(self):
        # "hello " (6) + emoji (2) + " world" (6) = 14
        assert utf16_len("hello \U0001F600 world") == 14

    def test_multiple_emoji(self):
        # Each emoji is 2 code units
        assert utf16_len("\U0001F600\U0001F601\U0001F602") == 6

    def test_newlines(self):
        assert utf16_len("a\nb\nc") == 5

    def test_cjk_bmp(self):
        # CJK characters in BMP are 1 code unit each
        assert utf16_len("\u4e2d\u6587") == 2  # 中文


class TestUtf16Offset:
    """Tests for Python index to UTF-16 offset conversion."""

    def test_ascii_offset(self):
        assert utf16_offset("hello world", 5) == 5

    def test_offset_after_emoji(self):
        # "X" + emoji(2 units) = offset at index 2 is 3
        text = "X\U0001F600Y"
        assert utf16_offset(text, 0) == 0
        assert utf16_offset(text, 1) == 1   # after "X"
        assert utf16_offset(text, 2) == 3   # after emoji (2 code units)


class TestNormalizeText:
    """Tests for text normalization."""

    def test_crlf_to_lf(self):
        assert normalize_text("hello\r\nworld") == "hello\nworld"

    def test_lone_cr_to_lf(self):
        assert normalize_text("hello\rworld") == "hello\nworld"

    def test_lf_unchanged(self):
        assert normalize_text("hello\nworld") == "hello\nworld"

    def test_mixed_line_endings(self):
        assert normalize_text("a\r\nb\rc\n") == "a\nb\nc\n"


class TestMarkdownToRequests:
    """Tests for markdown to batchUpdate conversion."""

    def test_plain_text(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("Hello world", base_index=1)
        assert len(requests) >= 1
        assert requests[0]["insertText"]["location"]["index"] == 1
        assert "Hello world" in requests[0]["insertText"]["text"]

    def test_bold_text(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("**bold**", base_index=1)
        # Should have insertText + updateTextStyle(bold)
        assert len(requests) >= 2
        bold_req = [r for r in requests if "updateTextStyle" in r]
        assert len(bold_req) >= 1
        assert bold_req[0]["updateTextStyle"]["textStyle"]["bold"] is True

    def test_italic_text(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("*italic*", base_index=1)
        italic_req = [r for r in requests if "updateTextStyle" in r]
        assert len(italic_req) >= 1
        assert italic_req[0]["updateTextStyle"]["textStyle"]["italic"] is True

    def test_heading(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("# Heading 1", base_index=1)
        heading_req = [r for r in requests if "updateParagraphStyle" in r]
        assert len(heading_req) >= 1
        assert heading_req[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"

    def test_code_inline(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("Use `code` here", base_index=1)
        code_req = [r for r in requests if "updateTextStyle" in r]
        assert len(code_req) >= 1
        assert "weightedFontFamily" in code_req[0]["updateTextStyle"]["textStyle"]

    def test_link(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("[click](https://example.com)", base_index=1)
        link_req = [r for r in requests if "updateTextStyle" in r]
        assert len(link_req) >= 1
        assert link_req[0]["updateTextStyle"]["textStyle"]["link"]["url"] == "https://example.com"

    def test_empty_markdown(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("", base_index=1)
        assert requests == []

    def test_end_of_segment_no_styles(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        # When base_index is None (append), should return just insert
        requests = markdown_to_requests("**bold**", base_index=None)
        assert len(requests) == 1
        assert "endOfSegmentLocation" in requests[0]["insertText"]

    def test_base_index_offsets_styles(self):
        from desk.services.markdown_to_docs import markdown_to_requests

        requests = markdown_to_requests("**bold**", base_index=10)
        bold_req = [r for r in requests if "updateTextStyle" in r]
        assert len(bold_req) >= 1
        # Range should be offset by base_index
        assert bold_req[0]["updateTextStyle"]["range"]["startIndex"] >= 10
