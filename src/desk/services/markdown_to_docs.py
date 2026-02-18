"""Convert markdown to Google Docs API batchUpdate requests.

Uses markdown-it-py to parse markdown into a flat token stream, then
generates batchUpdate requests for text insertion and formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desk.services.docs_editing import normalize_text, utf16_len


@dataclass
class StyleAnnotation:
    """A formatting annotation to apply after text insertion."""

    start: int  # UTF-16 offset from start of inserted text
    end: int  # UTF-16 offset from start of inserted text
    style_type: str  # "bold", "italic", "code", "link", "heading_N"
    url: str | None = None  # For links


@dataclass
class MarkdownConverter:
    """Converts markdown to Google Docs batchUpdate requests."""

    text_parts: list[str] = field(default_factory=list)
    annotations: list[StyleAnnotation] = field(default_factory=list)
    _current_utf16_offset: int = 0
    _style_stack: list[dict] = field(default_factory=list)

    def convert(self, markdown: str) -> tuple[str, list[StyleAnnotation]]:
        """Parse markdown and return (plain_text, annotations).

        Args:
            markdown: Markdown source text

        Returns:
            Tuple of (plain text string, list of style annotations)
        """
        from markdown_it import MarkdownIt

        md = MarkdownIt("commonmark")
        tokens = md.parse(markdown)

        self.text_parts = []
        self.annotations = []
        self._current_utf16_offset = 0
        self._style_stack = []

        for token in tokens:
            self._process_token(token)

        plain_text = "".join(self.text_parts)
        return plain_text, self.annotations

    def _process_token(self, token) -> None:
        """Process a single markdown-it token."""
        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            self._style_stack.append(
                {
                    "type": f"heading_{level}",
                    "start": self._current_utf16_offset,
                }
            )
        elif token.type == "heading_close":
            if self._style_stack and self._style_stack[-1]["type"].startswith("heading_"):
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type=info["type"],
                    )
                )
        elif token.type == "paragraph_open":
            pass  # Nothing to do on open
        elif token.type == "paragraph_close":
            self._add_text("\n")
        elif token.type == "inline":
            if token.children:
                for child in token.children:
                    self._process_inline_token(child)
        elif token.type == "fence":
            # Code block - insert text and mark as code
            code_text = token.content
            if not code_text.endswith("\n"):
                code_text += "\n"
            start = self._current_utf16_offset
            self._add_text(code_text)
            self.annotations.append(
                StyleAnnotation(
                    start=start,
                    end=self._current_utf16_offset,
                    style_type="code",
                )
            )
        elif token.type == "code_block":
            code_text = token.content
            if not code_text.endswith("\n"):
                code_text += "\n"
            start = self._current_utf16_offset
            self._add_text(code_text)
            self.annotations.append(
                StyleAnnotation(
                    start=start,
                    end=self._current_utf16_offset,
                    style_type="code",
                )
            )
        elif token.type == "hr":
            self._add_text("---\n")
        elif token.type in (
            "bullet_list_open",
            "bullet_list_close",
            "ordered_list_open",
            "ordered_list_close",
            "list_item_open",
            "list_item_close",
        ):
            # Lists are handled by their inline content
            if token.type == "list_item_open":
                self._add_text(
                    "  - " if not hasattr(token, "markup") or token.markup != "." else "  1. "
                )

    def _process_inline_token(self, token) -> None:
        """Process an inline token (child of an inline token)."""
        if token.type == "text":
            self._add_text(token.content)
        elif token.type == "softbreak":
            self._add_text("\n")
        elif token.type == "hardbreak":
            self._add_text("\n")
        elif token.type == "code_inline":
            start = self._current_utf16_offset
            self._add_text(token.content)
            self.annotations.append(
                StyleAnnotation(
                    start=start,
                    end=self._current_utf16_offset,
                    style_type="code",
                )
            )
        elif token.type == "strong_open":
            self._style_stack.append(
                {
                    "type": "bold",
                    "start": self._current_utf16_offset,
                }
            )
        elif token.type == "strong_close":
            if self._style_stack and self._style_stack[-1]["type"] == "bold":
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type="bold",
                    )
                )
        elif token.type == "em_open":
            self._style_stack.append(
                {
                    "type": "italic",
                    "start": self._current_utf16_offset,
                }
            )
        elif token.type == "em_close":
            if self._style_stack and self._style_stack[-1]["type"] == "italic":
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type="italic",
                    )
                )
        elif token.type == "link_open":
            url = ""
            if token.attrs:
                url = token.attrs.get("href", "")
            self._style_stack.append(
                {
                    "type": "link",
                    "start": self._current_utf16_offset,
                    "url": url,
                }
            )
        elif token.type == "link_close":
            if self._style_stack and self._style_stack[-1]["type"] == "link":
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type="link",
                        url=info.get("url"),
                    )
                )
        elif token.type == "image":
            # Insert alt text as placeholder
            alt = token.content or token.attrs.get("alt", "") if token.attrs else ""
            if alt:
                self._add_text(f"[{alt}]")

    def _add_text(self, text: str) -> None:
        """Add text and update the UTF-16 offset."""
        self.text_parts.append(text)
        self._current_utf16_offset += utf16_len(text)


def markdown_to_requests(
    markdown: str,
    base_index: int | None = None,
) -> list[dict]:
    """Convert markdown to Google Docs batchUpdate requests.

    Args:
        markdown: Markdown source text
        base_index: Document index where text will be inserted.
                   None means end of document (EndOfSegmentLocation).

    Returns:
        List of batchUpdate request dicts ready for the API.
    """
    markdown = normalize_text(markdown)
    converter = MarkdownConverter()
    plain_text, annotations = converter.convert(markdown)

    if not plain_text:
        return []

    requests: list[dict] = []

    # First request: insert the plain text
    if base_index is None:
        requests.append(
            {
                "insertText": {
                    "endOfSegmentLocation": {},
                    "text": plain_text,
                }
            }
        )
    else:
        requests.append(
            {
                "insertText": {
                    "location": {"index": base_index},
                    "text": plain_text,
                }
            }
        )

    # Calculate the actual base for style offsets
    # If inserting at end, we don't know the exact index yet, so we
    # need to use a two-pass approach. For now, when base_index is None,
    # we can't apply styles (they need absolute indices).
    # When base_index is provided, offset all annotations by it.
    if base_index is not None:
        offset = base_index
    else:
        # When appending, styles can't be applied without knowing the
        # document length. Return just the insert for now.
        # TODO: Support styled append by fetching doc length first
        return requests

    # Apply formatting annotations
    for ann in annotations:
        start = offset + ann.start
        end = offset + ann.end

        if ann.style_type == "bold":
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                }
            )
        elif ann.style_type == "italic":
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"italic": True},
                        "fields": "italic",
                    }
                }
            )
        elif ann.style_type == "code":
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Courier New"},
                        },
                        "fields": "weightedFontFamily",
                    }
                }
            )
        elif ann.style_type == "link":
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"link": {"url": ann.url}},
                        "fields": "link",
                    }
                }
            )
        elif ann.style_type.startswith("heading_"):
            level = int(ann.style_type.split("_")[1])
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
                        "fields": "namedStyleType",
                    }
                }
            )

    return requests
