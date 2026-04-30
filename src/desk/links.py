"""Link utilities: markdown escaping, HTML extraction, and Workspace URL classification.

Provides shared helpers for emitting markdown ``[text](url)`` links with
properly escaped delimiters, extracting ``<a href>`` links from email HTML
bodies, and classifying Google Workspace URLs.
"""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

# ------------------------------------------------------------------
# Markdown link escaping
# ------------------------------------------------------------------

def escape_link_text(text: str) -> str:
    """Escape markdown link text delimiters (``\\`` and ``]``)."""
    return text.replace("\\", "\\\\").replace("]", "\\]")


def escape_link_url(url: str) -> str:
    """Escape markdown link URL delimiters (``\\``, ``(``, and ``)``).`"""
    return url.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def format_markdown_link(text: str, url: str) -> str:
    """Format a markdown link with properly escaped text and URL."""
    return f"[{escape_link_text(text)}]({escape_link_url(url)})"


class _LinkExtractor(HTMLParser):
    """HTMLParser subclass that extracts <a href> tags."""

    def __init__(self):
        super().__init__()
        self.links: list[dict] = []
        self._current_href: str | None = None
        self._current_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attr_dict = dict(attrs)
            href = attr_dict.get("href")
            if href:
                self._current_href = href
                self._current_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            text = "".join(self._current_text_parts).strip()
            # Collapse internal whitespace
            text = " ".join(text.split())
            self.links.append({"url": self._current_href, "text": text})
            self._current_href = None
            self._current_text_parts = []


def _unwrap_google_redirect(url: str) -> str:
    """Unwrap Google redirect URLs to their actual destination.

    Google often wraps links in emails as:
      https://www.google.com/url?q=<actual_url>&...
    """
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.endswith("google.com") and parsed.path == "/url":
        params = parse_qs(parsed.query)
        if "q" in params:
            return unquote(params["q"][0])
    return url


def _should_skip_url(url: str) -> bool:
    """Return True for URLs that should be filtered out."""
    if not url or url.startswith(("#", "mailto:", "tel:", "data:")):
        return True
    # Skip javascript: URIs
    if url.lower().startswith("javascript:"):
        return True
    return False


# Patterns for extracting Google Workspace document IDs
_WORKSPACE_PATTERNS: list[tuple[str, str, str]] = [
    # Google Docs
    (r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", "google-doc", "desk docs read {}"),
    # Google Sheets
    (r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", "google-sheet", "desk sheets read {}"),
    # Google Slides
    (r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", "google-slides", None),
    # Google Forms
    (r"docs\.google\.com/forms/d/([a-zA-Z0-9_-]+)", "google-form", None),
    # Google Drive file
    (r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", "google-drive", "desk drive read {}"),
    # Google Drive open
    (r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)", "google-drive", "desk drive read {}"),
]


def classify_url(url: str) -> dict:
    """Classify a URL and identify Google Workspace resources.

    Returns:
        Dict with 'type' and 'readable_via' (desk command to read the resource,
        or None if not directly readable).
    """
    for pattern, url_type, command_template in _WORKSPACE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            doc_id = match.group(1)
            readable_via = command_template.format(doc_id) if command_template else None
            return {"type": url_type, "readable_via": readable_via}

    return {"type": "external", "readable_via": None}


def extract_links_from_html(html: str) -> list[dict]:
    """Extract and deduplicate links from HTML content.

    Args:
        html: HTML string (e.g., email body)

    Returns:
        List of dicts with 'url', 'text', 'type', 'readable_via'.
        Deduplicated by URL (first occurrence wins for text).
    """
    parser = _LinkExtractor()
    parser.feed(html)

    seen_urls: set[str] = set()
    results: list[dict] = []

    for link in parser.links:
        url = _unwrap_google_redirect(link["url"])

        if _should_skip_url(url):
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        classification = classify_url(url)
        results.append({
            "url": url,
            "text": link["text"],
            **classification,
        })

    return results


def filter_links_not_in_text(links: list[dict], plain_text: str) -> list[dict]:
    """Return only links whose URL doesn't already appear in the plain text body.

    For text-mode output, we only show links that are "hidden" — i.e., present
    in the HTML but not visible in the plain text version.
    """
    if not plain_text:
        return links
    return [link for link in links if link["url"] not in plain_text]
