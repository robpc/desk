"""Tests for link utilities: markdown escaping, HTML extraction, and URL classification."""


from desk.links import (
    classify_url,
    escape_link_text,
    escape_link_url,
    extract_links_from_html,
    filter_links_not_in_text,
    format_markdown_link,
)


class TestEscapeLinkText:
    """Tests for escape_link_text."""

    def test_plain_text_unchanged(self):
        assert escape_link_text("hello world") == "hello world"

    def test_escapes_closing_bracket(self):
        assert escape_link_text("foo]bar") == r"foo\]bar"

    def test_escapes_backslash(self):
        assert escape_link_text(r"a\b") == r"a\\b"

    def test_escapes_both(self):
        assert escape_link_text(r"a\]b") == r"a\\\]b"

    def test_empty_string(self):
        assert escape_link_text("") == ""


class TestEscapeLinkUrl:
    """Tests for escape_link_url."""

    def test_plain_url_unchanged(self):
        assert escape_link_url("https://example.com/page") == "https://example.com/page"

    def test_escapes_parentheses(self):
        assert escape_link_url("https://example.com/a(b)") == r"https://example.com/a\(b\)"

    def test_escapes_backslash(self):
        assert escape_link_url(r"https://example.com/a\b") == r"https://example.com/a\\b"

    def test_empty_string(self):
        assert escape_link_url("") == ""


class TestFormatMarkdownLink:
    """Tests for format_markdown_link."""

    def test_simple_link(self):
        assert format_markdown_link("Example", "https://example.com") == "[Example](https://example.com)"

    def test_escapes_text_and_url(self):
        result = format_markdown_link("foo]bar", "https://example.com/a(b)")
        assert result == r"[foo\]bar](https://example.com/a\(b\))"

    def test_empty_text(self):
        assert format_markdown_link("", "https://example.com") == "[](https://example.com)"

    def test_backslash_in_both(self):
        result = format_markdown_link(r"a\b", r"https://example.com/c\d")
        assert result == r"[a\\b](https://example.com/c\\d)"


class TestExtractLinksFromHtml:
    """Tests for extract_links_from_html."""

    def test_simple_link(self):
        html = '<a href="https://example.com">Example</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com"
        assert links[0]["text"] == "Example"
        assert links[0]["type"] == "external"

    def test_multiple_links(self):
        html = (
            '<a href="https://a.com">A</a> '
            '<a href="https://b.com">B</a>'
        )
        links = extract_links_from_html(html)
        assert len(links) == 2
        assert links[0]["url"] == "https://a.com"
        assert links[1]["url"] == "https://b.com"

    def test_deduplicates_by_url(self):
        html = (
            '<a href="https://example.com">First</a> '
            '<a href="https://example.com">Second</a>'
        )
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["text"] == "First"

    def test_filters_mailto(self):
        html = '<a href="mailto:user@example.com">Email</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_filters_tel(self):
        html = '<a href="tel:+1234567890">Call</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_filters_anchor(self):
        html = '<a href="#section">Section</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_filters_data_uri(self):
        html = '<a href="data:text/plain;base64,SGVsbG8=">Data</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_filters_javascript_uri(self):
        html = '<a href="javascript:void(0)">Click</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_empty_href_filtered(self):
        html = '<a href="">Empty</a>'
        links = extract_links_from_html(html)
        assert len(links) == 0

    def test_nested_tags_in_link(self):
        html = '<a href="https://example.com"><strong>Bold</strong> text</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["text"] == "Bold text"

    def test_google_redirect_unwrapped(self):
        html = '<a href="https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fpage&sa=D">Link</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com/page"

    def test_google_doc_link_classified(self):
        html = '<a href="https://docs.google.com/document/d/1abc123/edit">Notes</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-doc"
        assert links[0]["readable_via"] == "desk docs read 1abc123"

    def test_google_sheet_link_classified(self):
        html = '<a href="https://docs.google.com/spreadsheets/d/1xyz789/edit">Budget</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-sheet"
        assert links[0]["readable_via"] == "desk sheets read 1xyz789"

    def test_google_drive_file_classified(self):
        html = '<a href="https://drive.google.com/file/d/abc123/view">File</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-drive"
        assert links[0]["readable_via"] == "desk drive read abc123"

    def test_google_drive_open_classified(self):
        html = '<a href="https://drive.google.com/open?id=abc123">Open</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-drive"
        assert links[0]["readable_via"] == "desk drive read abc123"

    def test_google_slides_no_readable_via(self):
        html = '<a href="https://docs.google.com/presentation/d/1pres/edit">Slides</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-slides"
        assert links[0]["readable_via"] is None

    def test_google_forms_no_readable_via(self):
        html = '<a href="https://docs.google.com/forms/d/1form/viewform">Form</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["type"] == "google-form"
        assert links[0]["readable_via"] is None

    def test_empty_html(self):
        assert extract_links_from_html("") == []

    def test_no_links(self):
        html = "<p>Plain text with no links</p>"
        assert extract_links_from_html(html) == []

    def test_google_redirect_to_workspace_url(self):
        """Google redirect wrapping a Google Docs URL should unwrap and classify."""
        html = '<a href="https://www.google.com/url?q=https%3A%2F%2Fdocs.google.com%2Fdocument%2Fd%2F1abc%2Fedit&sa=D">Doc</a>'
        links = extract_links_from_html(html)
        assert len(links) == 1
        assert links[0]["url"] == "https://docs.google.com/document/d/1abc/edit"
        assert links[0]["type"] == "google-doc"
        assert links[0]["readable_via"] == "desk docs read 1abc"


class TestClassifyUrl:
    """Tests for classify_url."""

    def test_external_url(self):
        result = classify_url("https://example.com")
        assert result == {"type": "external", "readable_via": None}

    def test_google_doc(self):
        result = classify_url("https://docs.google.com/document/d/1abc-XYZ_123/edit")
        assert result["type"] == "google-doc"
        assert result["readable_via"] == "desk docs read 1abc-XYZ_123"

    def test_google_sheet(self):
        result = classify_url("https://docs.google.com/spreadsheets/d/1abc/edit#gid=0")
        assert result["type"] == "google-sheet"
        assert result["readable_via"] == "desk sheets read 1abc"

    def test_google_slides(self):
        result = classify_url("https://docs.google.com/presentation/d/1abc/edit")
        assert result["type"] == "google-slides"
        assert result["readable_via"] is None

    def test_google_form(self):
        result = classify_url("https://docs.google.com/forms/d/1abc/viewform")
        assert result["type"] == "google-form"
        assert result["readable_via"] is None

    def test_google_drive_file(self):
        result = classify_url("https://drive.google.com/file/d/abc123/view")
        assert result["type"] == "google-drive"
        assert result["readable_via"] == "desk drive read abc123"

    def test_google_drive_open(self):
        result = classify_url("https://drive.google.com/open?id=abc123")
        assert result["type"] == "google-drive"
        assert result["readable_via"] == "desk drive read abc123"


class TestFilterLinksNotInText:
    """Tests for filter_links_not_in_text."""

    def test_filters_links_present_in_text(self):
        links = [
            {"url": "https://example.com", "text": "Example", "type": "external", "readable_via": None},
            {"url": "https://hidden.com", "text": "Hidden", "type": "external", "readable_via": None},
        ]
        plain_text = "Check out https://example.com for details."
        result = filter_links_not_in_text(links, plain_text)
        assert len(result) == 1
        assert result[0]["url"] == "https://hidden.com"

    def test_all_links_hidden(self):
        links = [
            {"url": "https://a.com", "text": "A", "type": "external", "readable_via": None},
            {"url": "https://b.com", "text": "B", "type": "external", "readable_via": None},
        ]
        plain_text = "No URLs here."
        result = filter_links_not_in_text(links, plain_text)
        assert len(result) == 2

    def test_all_links_visible(self):
        links = [
            {"url": "https://a.com", "text": "A", "type": "external", "readable_via": None},
        ]
        plain_text = "Visit https://a.com"
        result = filter_links_not_in_text(links, plain_text)
        assert len(result) == 0

    def test_empty_plain_text(self):
        links = [
            {"url": "https://a.com", "text": "A", "type": "external", "readable_via": None},
        ]
        result = filter_links_not_in_text(links, "")
        assert len(result) == 1

    def test_empty_links(self):
        result = filter_links_not_in_text([], "some text")
        assert result == []
