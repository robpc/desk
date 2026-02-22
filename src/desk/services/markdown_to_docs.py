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
class TableData:
    """A parsed markdown table."""

    headers: list[str] = field(default_factory=list)
    header_annotations: list[list[StyleAnnotation]] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    row_annotations: list[list[list[StyleAnnotation]]] = field(default_factory=list)

    @property
    def num_cols(self) -> int:
        if self.headers:
            return len(self.headers)
        if self.rows:
            return len(self.rows[0])
        return 0

    @property
    def num_rows(self) -> int:
        """Total rows including header."""
        return (1 if self.headers else 0) + len(self.rows)

    def all_cells_flat(self) -> list[tuple[int, int, str, list[StyleAnnotation]]]:
        """Return all cells as (row, col, text, annotations) in row-major order."""
        cells = []
        if self.headers:
            for j, text in enumerate(self.headers):
                cells.append((0, j, text, self.header_annotations[j]))
        for i, row in enumerate(self.rows):
            row_idx = i + (1 if self.headers else 0)
            for j, text in enumerate(row):
                cells.append((row_idx, j, text, self.row_annotations[i][j]))
        return cells


@dataclass
class ContentSegment:
    """A segment of document content — either text or a table."""

    segment_type: str  # "text" or "table"
    text: str = ""
    annotations: list[StyleAnnotation] = field(default_factory=list)
    table: TableData | None = None


def _empty_table_size(num_rows: int, num_cols: int) -> int:
    """Calculate the number of document indices consumed by an empty table.

    An empty table with R rows and C columns consumes:
    1 (pre-newline) + 1 (table start) + R * (1 row + C * 2 cells) + 1 (end)
    = R * (2C + 1) + 3
    """
    return num_rows * (2 * num_cols + 1) + 3


def _cell_empty_index(table_start: int, row: int, col: int, num_cols: int) -> int:
    """Calculate the insertion index for a cell in an empty table.

    Formula: table_start + 4 + row * (2 * num_cols + 1) + col * 2
    """
    return table_start + 4 + row * (2 * num_cols + 1) + col * 2


@dataclass
class MarkdownConverter:
    """Converts markdown to Google Docs batchUpdate requests."""

    text_parts: list[str] = field(default_factory=list)
    annotations: list[StyleAnnotation] = field(default_factory=list)
    _current_utf16_offset: int = 0
    _style_stack: list[dict] = field(default_factory=list)

    # Table parsing state
    _in_table: bool = False
    _current_table: TableData | None = None
    _current_cell_text: list[str] = field(default_factory=list)
    _current_cell_offset: int = 0
    _current_cell_annotations: list[StyleAnnotation] = field(default_factory=list)
    _in_header: bool = False
    _current_row_cells: list[str] = field(default_factory=list)
    _current_row_annotations: list[list[StyleAnnotation]] = field(default_factory=list)

    # Segments output
    _segments: list[ContentSegment] = field(default_factory=list)

    def convert(self, markdown: str) -> tuple[str, list[StyleAnnotation]]:
        """Parse markdown and return (plain_text, annotations).

        For backwards compatibility. Tables are silently omitted from the
        flat text output. Use convert_to_segments() for full table support.

        Args:
            markdown: Markdown source text

        Returns:
            Tuple of (plain text string, list of style annotations)
        """
        segments = self.convert_to_segments(markdown)

        text_parts = []
        annotations: list[StyleAnnotation] = []
        offset = 0
        for seg in segments:
            if seg.segment_type == "text":
                text_parts.append(seg.text)
                for ann in seg.annotations:
                    annotations.append(
                        StyleAnnotation(
                            start=ann.start + offset,
                            end=ann.end + offset,
                            style_type=ann.style_type,
                            url=ann.url,
                        )
                    )
                offset += utf16_len(seg.text)

        return "".join(text_parts), annotations

    def convert_to_segments(self, markdown: str) -> list[ContentSegment]:
        """Parse markdown and return content segments (text and tables).

        Args:
            markdown: Markdown source text

        Returns:
            List of ContentSegment objects
        """
        from markdown_it import MarkdownIt

        md = MarkdownIt("commonmark")
        md.enable("table")
        tokens = md.parse(markdown)

        self.text_parts = []
        self.annotations = []
        self._current_utf16_offset = 0
        self._style_stack = []
        self._in_table = False
        self._current_table = None
        self._segments = []

        for token in tokens:
            self._process_token(token)

        # Flush any remaining text
        self._flush_text_segment()

        return self._segments

    def _flush_text_segment(self) -> None:
        """Flush accumulated text as a ContentSegment."""
        text = "".join(self.text_parts)
        if text:
            self._segments.append(
                ContentSegment(
                    segment_type="text",
                    text=text,
                    annotations=list(self.annotations),
                )
            )
        self.text_parts = []
        self.annotations = []
        self._current_utf16_offset = 0

    def _process_token(self, token) -> None:
        """Process a single markdown-it token."""
        # Table tokens
        if token.type == "table_open":
            self._flush_text_segment()
            self._in_table = True
            self._current_table = TableData()
            return
        elif token.type == "table_close":
            if self._current_table is not None:
                self._segments.append(
                    ContentSegment(
                        segment_type="table",
                        table=self._current_table,
                    )
                )
            self._in_table = False
            self._current_table = None
            return
        elif token.type == "thead_open":
            self._in_header = True
            return
        elif token.type == "thead_close":
            self._in_header = False
            return
        elif token.type in ("tbody_open", "tbody_close"):
            return
        elif token.type == "tr_open":
            self._current_row_cells = []
            self._current_row_annotations = []
            return
        elif token.type == "tr_close":
            if self._current_table is not None:
                if self._in_header:
                    self._current_table.headers = self._current_row_cells
                    self._current_table.header_annotations = self._current_row_annotations
                else:
                    self._current_table.rows.append(self._current_row_cells)
                    self._current_table.row_annotations.append(
                        self._current_row_annotations
                    )
            return
        elif token.type in ("th_open", "td_open"):
            self._current_cell_text = []
            self._current_cell_offset = 0
            self._current_cell_annotations = []
            return
        elif token.type in ("th_close", "td_close"):
            cell_text = "".join(self._current_cell_text)
            self._current_row_cells.append(cell_text)
            self._current_row_annotations.append(list(self._current_cell_annotations))
            return

        # Inline content inside table cells
        if self._in_table and token.type == "inline":
            if token.children:
                for child in token.children:
                    self._process_inline_token(child)
            return

        # Non-table tokens (existing logic)
        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            self._style_stack.append(
                {
                    "type": f"heading_{level}",
                    "start": self._current_utf16_offset,
                }
            )
        elif token.type == "heading_close":
            self._add_text("\n")
            if self._style_stack and self._style_stack[-1]["type"].startswith(
                "heading_"
            ):
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
            start = self._current_utf16_offset
            self._add_text("\n")
            self.annotations.append(
                StyleAnnotation(
                    start=start,
                    end=self._current_utf16_offset,
                    style_type="hr",
                )
            )
        elif token.type == "bullet_list_open":
            self._style_stack.append(
                {"type": "bullet_list", "start": self._current_utf16_offset}
            )
        elif token.type == "bullet_list_close":
            if self._style_stack and self._style_stack[-1]["type"] == "bullet_list":
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type="bullet_list",
                    )
                )
        elif token.type == "ordered_list_open":
            self._style_stack.append(
                {"type": "ordered_list", "start": self._current_utf16_offset}
            )
        elif token.type == "ordered_list_close":
            if self._style_stack and self._style_stack[-1]["type"] == "ordered_list":
                info = self._style_stack.pop()
                self.annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._current_utf16_offset,
                        style_type="ordered_list",
                    )
                )
        elif token.type in ("list_item_open", "list_item_close"):
            pass

    def _process_inline_token(self, token) -> None:
        """Process an inline token (child of an inline token)."""
        if token.type == "text":
            self._add_text(token.content)
        elif token.type == "softbreak":
            self._add_text("\n")
        elif token.type == "hardbreak":
            self._add_text("\n")
        elif token.type == "code_inline":
            start = self._active_offset
            self._add_text(token.content)
            self._active_annotations.append(
                StyleAnnotation(
                    start=start,
                    end=self._active_offset,
                    style_type="code",
                )
            )
        elif token.type == "strong_open":
            self._style_stack.append(
                {
                    "type": "bold",
                    "start": self._active_offset,
                }
            )
        elif token.type == "strong_close":
            if self._style_stack and self._style_stack[-1]["type"] == "bold":
                info = self._style_stack.pop()
                self._active_annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._active_offset,
                        style_type="bold",
                    )
                )
        elif token.type == "em_open":
            self._style_stack.append(
                {
                    "type": "italic",
                    "start": self._active_offset,
                }
            )
        elif token.type == "em_close":
            if self._style_stack and self._style_stack[-1]["type"] == "italic":
                info = self._style_stack.pop()
                self._active_annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._active_offset,
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
                    "start": self._active_offset,
                    "url": url,
                }
            )
        elif token.type == "link_close":
            if self._style_stack and self._style_stack[-1]["type"] == "link":
                info = self._style_stack.pop()
                self._active_annotations.append(
                    StyleAnnotation(
                        start=info["start"],
                        end=self._active_offset,
                        style_type="link",
                        url=info.get("url"),
                    )
                )
        elif token.type == "image":
            # Insert alt text as placeholder
            alt = token.content or token.attrs.get("alt", "") if token.attrs else ""
            if alt:
                self._add_text(f"[{alt}]")

    @property
    def _active_offset(self) -> int:
        """Current UTF-16 offset — cell offset when in table, main offset otherwise."""
        if self._in_table:
            return self._current_cell_offset
        return self._current_utf16_offset

    @property
    def _active_annotations(self) -> list[StyleAnnotation]:
        """Current annotation list — cell list when in table, main list otherwise."""
        if self._in_table:
            return self._current_cell_annotations
        return self.annotations

    def _add_text(self, text: str) -> None:
        """Add text and update the UTF-16 offset."""
        length = utf16_len(text)
        if self._in_table:
            self._current_cell_text.append(text)
            self._current_cell_offset += length
        else:
            self.text_parts.append(text)
            self._current_utf16_offset += length


def _make_range(start: int, end: int, tab_id: str | None = None) -> dict:
    """Build a range object, optionally scoped to a tab."""
    r: dict = {"startIndex": start, "endIndex": end}
    if tab_id:
        r["tabId"] = tab_id
    return r


def _make_location(index: int, tab_id: str | None = None) -> dict:
    """Build a location object, optionally scoped to a tab."""
    loc: dict = {"index": index}
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _annotation_to_requests(
    ann: StyleAnnotation, start: int, end: int, tab_id: str | None = None
) -> list[dict]:
    """Convert a StyleAnnotation to batchUpdate request(s)."""
    range_obj = _make_range(start, end, tab_id)
    if ann.style_type == "bold":
        return [
            {
                "updateTextStyle": {
                    "range": range_obj,
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            }
        ]
    elif ann.style_type == "italic":
        return [
            {
                "updateTextStyle": {
                    "range": range_obj,
                    "textStyle": {"italic": True},
                    "fields": "italic",
                }
            }
        ]
    elif ann.style_type == "code":
        return [
            {
                "updateTextStyle": {
                    "range": range_obj,
                    "textStyle": {
                        "weightedFontFamily": {"fontFamily": "Courier New"},
                    },
                    "fields": "weightedFontFamily",
                }
            }
        ]
    elif ann.style_type == "link":
        return [
            {
                "updateTextStyle": {
                    "range": range_obj,
                    "textStyle": {"link": {"url": ann.url}},
                    "fields": "link",
                }
            }
        ]
    elif ann.style_type.startswith("heading_"):
        level = int(ann.style_type.split("_")[1])
        return [
            {
                "updateParagraphStyle": {
                    "range": range_obj,
                    "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
                    "fields": "namedStyleType",
                }
            }
        ]
    elif ann.style_type == "hr":
        return [
            {
                "updateParagraphStyle": {
                    "range": range_obj,
                    "paragraphStyle": {
                        "borderBottom": {
                            "color": {
                                "color": {
                                    "rgbColor": {
                                        "red": 0.8,
                                        "green": 0.8,
                                        "blue": 0.8,
                                    }
                                }
                            },
                            "width": {"magnitude": 1, "unit": "PT"},
                            "padding": {"magnitude": 6, "unit": "PT"},
                            "dashStyle": "SOLID",
                        }
                    },
                    "fields": "borderBottom",
                }
            }
        ]
    elif ann.style_type == "bullet_list":
        return [
            {
                "createParagraphBullets": {
                    "range": range_obj,
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            }
        ]
    elif ann.style_type == "ordered_list":
        return [
            {
                "createParagraphBullets": {
                    "range": range_obj,
                    "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
                }
            }
        ]
    return []


def _text_segment_to_requests(
    segment: ContentSegment, cursor: int, tab_id: str | None = None
) -> list[dict]:
    """Generate batchUpdate requests for a text segment."""
    if not segment.text:
        return []

    requests: list[dict] = []
    requests.append(
        {
            "insertText": {
                "location": _make_location(cursor, tab_id),
                "text": segment.text,
            }
        }
    )

    for ann in segment.annotations:
        start = cursor + ann.start
        end = cursor + ann.end
        requests.extend(_annotation_to_requests(ann, start, end, tab_id))

    return requests


def _table_segment_to_requests(
    segment: ContentSegment, cursor: int, tab_id: str | None = None
) -> list[dict]:
    """Generate batchUpdate requests for a table segment.

    Creates the table and populates cells in a single batch. Cell content
    is inserted in reverse row-major order so each insertion at an earlier
    index only shifts cells that have already been processed.
    """
    table = segment.table
    if table is None or table.num_rows == 0 or table.num_cols == 0:
        return []

    requests: list[dict] = []

    # 1. Insert the empty table
    requests.append(
        {
            "insertTable": {
                "location": _make_location(cursor, tab_id),
                "rows": table.num_rows,
                "columns": table.num_cols,
            }
        }
    )

    # 2. Insert cell content in reverse row-major order
    cells = table.all_cells_flat()
    cell_insert_requests = []
    for row, col, text, _annotations in reversed(cells):
        if not text:
            continue
        idx = _cell_empty_index(cursor, row, col, table.num_cols)
        cell_insert_requests.append(
            {
                "insertText": {
                    "location": _make_location(idx, tab_id),
                    "text": text,
                }
            }
        )
    requests.extend(cell_insert_requests)

    # 3. Apply formatting to cells
    # After all reverse-order inserts, compute final positions for formatting.
    # final_pos(i,j) = empty_index(i,j) + sum(utf16_len(text) for all cells
    #                   before (i,j) in row-major order)
    cumulative_shift = 0
    for row, col, text, cell_annotations in cells:
        if cell_annotations:
            empty_idx = _cell_empty_index(cursor, row, col, table.num_cols)
            final_start = empty_idx + cumulative_shift
            for ann in cell_annotations:
                abs_start = final_start + ann.start
                abs_end = final_start + ann.end
                requests.extend(
                    _annotation_to_requests(ann, abs_start, abs_end, tab_id)
                )
        cumulative_shift += utf16_len(text)

    # 4. Bold header cells
    if table.headers:
        cumulative_shift = 0
        for j, header_text in enumerate(table.headers):
            if header_text:
                empty_idx = _cell_empty_index(cursor, 0, j, table.num_cols)
                final_start = empty_idx + cumulative_shift
                final_end = final_start + utf16_len(header_text)
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _make_range(final_start, final_end, tab_id),
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    }
                )
            cumulative_shift += utf16_len(header_text)

    return requests


def _table_total_size(table: TableData) -> int:
    """Total document indices consumed by a table (structure + content)."""
    empty = _empty_table_size(table.num_rows, table.num_cols)
    content = sum(utf16_len(text) for _, _, text, _ in table.all_cells_flat())
    return empty + content


def markdown_to_requests(
    markdown: str,
    base_index: int,
    tab_id: str | None = None,
) -> list[dict]:
    """Convert markdown to Google Docs batchUpdate requests.

    Args:
        markdown: Markdown source text
        base_index: Document index where text will be inserted.
                   Callers must resolve the concrete index before calling
                   (e.g. by fetching the document length for appends).
        tab_id: Optional tab ID to inject into all location/range objects.

    Returns:
        List of batchUpdate request dicts ready for the API.
    """
    markdown = normalize_text(markdown)
    converter = MarkdownConverter()
    segments = converter.convert_to_segments(markdown)

    if not segments:
        return []

    requests: list[dict] = []
    cursor = base_index

    for segment in segments:
        if segment.segment_type == "text":
            requests.extend(_text_segment_to_requests(segment, cursor, tab_id))
            cursor += utf16_len(segment.text)
        elif segment.segment_type == "table":
            requests.extend(_table_segment_to_requests(segment, cursor, tab_id))
            if segment.table:
                cursor += _table_total_size(segment.table)

    return requests
