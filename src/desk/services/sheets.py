"""Google Sheets API wrapper."""

import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from desk.links import format_markdown_link

# Narrow fields mask — only link metadata, no values or formatting. Covers
# whole-cell hyperlinks, rich-text inline links (textFormatRuns), and Drive/
# Docs smart chips (chipRuns), whose target lives in richLinkProperties.
_HYPERLINK_FIELDS = (
    "sheets.data("
    "startRow,startColumn,"
    "rowData(values("
    "hyperlink,"
    "textFormatRuns(startIndex,format(link(uri))),"
    "chipRuns(startIndex,chip(richLinkProperties(uri)))"
    "))"
    ")"
)


class SheetsClient:
    """Client for Google Sheets API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("sheets", "v4", credentials=credentials)

    # ------------------------------------------------------------------
    # Hyperlink helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_link_runs(text: str, runs: list[dict], get_uri) -> str:
        """Wrap linked segments of *text* as ``[segment](url)``.

        Shared by textFormatRuns and chipRuns handling: *runs* is a list of
        run dicts covering ``[startIndex, next_startIndex)`` slices of *text*,
        and *get_uri* extracts a run's link target (or ``None``).
        """
        if not runs:
            return text

        # Ensure runs are sorted by startIndex
        runs = sorted(runs, key=lambda r: r.get("startIndex", 0))

        if not any(get_uri(r) for r in runs):
            return text

        parts: list[str] = []
        for i, run in enumerate(runs):
            start = run.get("startIndex", 0)
            end = runs[i + 1].get("startIndex", len(text)) if i + 1 < len(runs) else len(text)
            segment = text[start:end]
            link_uri = get_uri(run)

            if link_uri and segment:
                parts.append(format_markdown_link(segment, link_uri))
            else:
                parts.append(segment)

        # Handle text before the first run
        first_start = runs[0].get("startIndex", 0)
        if first_start > 0:
            parts.insert(0, text[:first_start])

        return "".join(parts)

    @staticmethod
    def _apply_text_format_runs(text: str, runs: list[dict]) -> str:
        """Apply textFormatRuns, converting linked runs to ``[text](url)``."""
        return SheetsClient._apply_link_runs(
            text, runs, lambda r: r.get("format", {}).get("link", {}).get("uri")
        )

    @staticmethod
    def _apply_chip_runs(text: str, runs: list[dict]) -> str:
        """Apply chipRuns, converting Drive/Docs smart chips to ``[text](url)``.

        Only rich-link chips carry a URI (``richLinkProperties.uri``); people
        chips and other chip kinds have no link and are left as-is.
        """
        return SheetsClient._apply_link_runs(
            text,
            runs,
            lambda r: r.get("chip", {}).get("richLinkProperties", {}).get("uri"),
        )

    @staticmethod
    def _extract_cell_hyperlink(cell: dict, display_value: str) -> str:
        """Return *display_value* with any hyperlinks applied as ``[text](url)``.

        Checks, in order of specificity: rich-text inline links
        (textFormatRuns), smart-chip links (chipRuns), then a whole-cell
        hyperlink. Falls through when a source is present but carries no link.
        """
        if not display_value:
            return display_value

        # Inline rich-text links.
        text_format_runs = cell.get("textFormatRuns")
        if text_format_runs:
            result = SheetsClient._apply_text_format_runs(display_value, text_format_runs)
            if result != display_value:
                return result

        # Smart chips (Drive/Docs link chips) — common in index sheets.
        chip_runs = cell.get("chipRuns")
        if chip_runs:
            result = SheetsClient._apply_chip_runs(display_value, chip_runs)
            if result != display_value:
                return result

        # Whole-cell hyperlink.
        hyperlink = cell.get("hyperlink")
        if hyperlink:
            # Skip redundant wrapping when display text is the URL itself
            if display_value == hyperlink:
                return display_value
            return format_markdown_link(display_value, hyperlink)

        return display_value

    @staticmethod
    def _enrich_values_with_hyperlinks(values: list[list], data_block: dict) -> None:
        """Merge hyperlink metadata from a grid data block into *values* in-place.

        Both the Values API result and the grid data block are 0-indexed
        relative to the same requested range, so no startRow/startColumn
        offset is applied.
        """
        for row_idx, row_data in enumerate(data_block.get("rowData", [])):
            if row_idx >= len(values):
                break
            for col_idx, cell in enumerate(row_data.get("values", [])):
                if col_idx >= len(values[row_idx]):
                    break
                original = str(values[row_idx][col_idx])
                enriched = SheetsClient._extract_cell_hyperlink(cell, original)
                if enriched != original:
                    values[row_idx][col_idx] = enriched

    def _fetch_hyperlinks(self, spreadsheet_id: str, ranges: list[str]) -> dict | None:
        """Best-effort fetch of hyperlink grid data for *ranges*."""
        try:
            return (
                self.service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    ranges=ranges,
                    fields=_HYPERLINK_FIELDS,
                )
                .execute()
            )
        except HttpError:
            return None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(
        self,
        spreadsheet_id: str,
        ranges: list[str] | None = None,
        sheet_id: int | None = None,
    ) -> dict:
        """Read data from a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            ranges: Optional list of A1 notation ranges (e.g., ["Sheet1!A1:B10"])
            sheet_id: Optional specific sheet ID

        Returns:
            Dict with spreadsheet title, sheet info, and values.
            Cell values that contain hyperlinks are emitted as
            ``[text](url)`` markdown.
        """
        try:
            if ranges:
                result = (
                    self.service.spreadsheets()
                    .values()
                    .batchGet(
                        spreadsheetId=spreadsheet_id,
                        ranges=ranges,
                    )
                    .execute()
                )
                range_results = [
                    {
                        "range": vr.get("range", ""),
                        "values": vr.get("values", []),
                    }
                    for vr in result.get("valueRanges", [])
                ]

                # Enrich each range individually to avoid ordering
                # mismatches when ranges span multiple sheets.
                for rr in range_results:
                    rng = rr.get("range")
                    if not rng or not rr.get("values"):
                        continue
                    grid = self._fetch_hyperlinks(spreadsheet_id, [rng])
                    if grid:
                        for sheet in grid.get("sheets", []):
                            for block in sheet.get("data", []):
                                self._enrich_values_with_hyperlinks(
                                    rr["values"], block
                                )

                return {
                    "spreadsheetId": spreadsheet_id,
                    "ranges": range_results,
                }
            else:
                # Get spreadsheet metadata first
                meta = (
                    self.service.spreadsheets()
                    .get(
                        spreadsheetId=spreadsheet_id,
                    )
                    .execute()
                )

                title = meta.get("properties", {}).get("title", "")
                sheets = meta.get("sheets", [])

                # Determine which sheet to read
                if sheet_id is not None:
                    target_sheet = None
                    for s in sheets:
                        if s["properties"]["sheetId"] == sheet_id:
                            target_sheet = s["properties"]["title"]
                            break
                    if not target_sheet:
                        raise RuntimeError(f"Sheet ID {sheet_id} not found")
                    read_range = target_sheet
                else:
                    read_range = sheets[0]["properties"]["title"] if sheets else "Sheet1"

                result = (
                    self.service.spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=spreadsheet_id,
                        range=read_range,
                    )
                    .execute()
                )

                values = result.get("values", [])

                # Enrich with hyperlinks
                enrich_range = result.get("range", read_range)
                grid = self._fetch_hyperlinks(spreadsheet_id, [enrich_range])
                if grid:
                    for sheet in grid.get("sheets", []):
                        for block in sheet.get("data", []):
                            self._enrich_values_with_hyperlinks(values, block)

                return {
                    "spreadsheetId": spreadsheet_id,
                    "title": title,
                    "sheets": [
                        {"id": s["properties"]["sheetId"], "title": s["properties"]["title"]}
                        for s in sheets
                    ],
                    "range": result.get("range", ""),
                    "values": values,
                }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def create(self, title: str) -> dict:
        """Create a new spreadsheet.

        Args:
            title: Spreadsheet title

        Returns:
            Dict with spreadsheetId, title, and spreadsheetUrl
        """
        try:
            result = (
                self.service.spreadsheets().create(body={"properties": {"title": title}}).execute()
            )
            return {
                "spreadsheetId": result["spreadsheetId"],
                "title": result["properties"]["title"],
                "spreadsheetUrl": result.get("spreadsheetUrl", ""),
            }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def write(self, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict:
        """Write a range of values to a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            range_: A1 notation range (e.g., "Sheet1!A1:C3")
            values: 2D list of values

        Returns:
            Update result dict
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                )
                .execute()
            )
            return {
                "updatedRange": result.get("updatedRange", ""),
                "updatedRows": result.get("updatedRows", 0),
                "updatedColumns": result.get("updatedColumns", 0),
                "updatedCells": result.get("updatedCells", 0),
            }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def append(self, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict:
        """Append rows to a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            range_: A1 notation range to append after (e.g., "Sheet1!A:Z")
            values: 2D list of row values to append

        Returns:
            Append result dict
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )
            updates = result.get("updates", {})
            return {
                "updatedRange": updates.get("updatedRange", ""),
                "updatedRows": updates.get("updatedRows", 0),
                "updatedCells": updates.get("updatedCells", 0),
            }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def clear(self, spreadsheet_id: str, range_: str) -> dict:
        """Clear values in a range.

        Args:
            spreadsheet_id: The spreadsheet ID
            range_: A1 notation range to clear (e.g., "Sheet1!A1:C10")

        Returns:
            Clear result dict
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    body={},
                )
                .execute()
            )
            return {"clearedRange": result.get("clearedRange", "")}
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def update_cell(self, spreadsheet_id: str, range_: str, value: str) -> dict:
        """Update a single cell value.

        Args:
            spreadsheet_id: The spreadsheet ID
            range_: Cell range in A1 notation (e.g., "Sheet1!A1")
            value: New cell value

        Returns:
            Update result dict
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    body={"values": [[value]]},
                )
                .execute()
            )
            return {
                "updatedRange": result.get("updatedRange", ""),
                "updatedRows": result.get("updatedRows", 0),
                "updatedColumns": result.get("updatedColumns", 0),
                "updatedCells": result.get("updatedCells", 0),
            }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def list_sheets(self, spreadsheet_id: str) -> list[dict]:
        """List all sheets (tabs) in a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID

        Returns:
            List of sheet info dicts with id, title, index, rowCount, columnCount
        """
        try:
            meta = (
                self.service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
                .execute()
            )
            sheets = []
            for s in meta.get("sheets", []):
                props = s.get("properties", {})
                grid = props.get("gridProperties", {})
                sheets.append({
                    "sheetId": props.get("sheetId"),
                    "title": props.get("title", ""),
                    "index": props.get("index", 0),
                    "rowCount": grid.get("rowCount", 0),
                    "columnCount": grid.get("columnCount", 0),
                })
            return sheets
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def add_sheet(
        self, spreadsheet_id: str, title: str, index: int | None = None
    ) -> dict:
        """Add a new sheet (tab) to a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            title: Name for the new sheet
            index: Optional position (0-based)

        Returns:
            New sheet info dict
        """
        request = {"addSheet": {"properties": {"title": title}}}
        if index is not None:
            request["addSheet"]["properties"]["index"] = index

        try:
            result = (
                self.service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [request]})
                .execute()
            )
            reply = result.get("replies", [{}])[0].get("addSheet", {})
            props = reply.get("properties", {})
            return {
                "sheetId": props.get("sheetId"),
                "title": props.get("title", ""),
                "index": props.get("index", 0),
            }
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    def delete_sheet(self, spreadsheet_id: str, sheet_id: int) -> None:
        """Delete a sheet (tab) from a spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_id: The sheet ID to delete
        """
        request = {"deleteSheet": {"sheetId": sheet_id}}

        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": [request]}
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

    # ------------------------------------------------------------------
    # Smart chips
    # ------------------------------------------------------------------

    @staticmethod
    def _column_to_index(letters: str) -> int:
        """Convert spreadsheet column letters (A, B, ..., AA) to a 0-based index."""
        index = 0
        for ch in letters.upper():
            index = index * 26 + (ord(ch) - ord("A") + 1)
        return index - 1

    @staticmethod
    def _parse_a1_cell(cell: str) -> tuple[str | None, int, int]:
        """Parse a single A1 cell reference into (sheet_name, row_index, col_index).

        Indices are 0-based. ``sheet_name`` is None when the reference has no
        ``SheetName!`` prefix. Ranges (containing ``:``) are rejected.
        """
        sheet_name: str | None = None
        ref = cell
        if "!" in cell:
            sheet_part, ref = cell.rsplit("!", 1)
            sheet_name = sheet_part.strip().strip("'")
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", ref.strip())
        if not match:
            raise ValueError(
                f"Invalid cell '{cell}': expected a single cell like 'Sheet1!D2'"
            )
        col_letters, row_num = match.group(1), int(match.group(2))
        if row_num < 1:
            raise ValueError(f"Invalid cell '{cell}': row must be >= 1")
        return sheet_name, row_num - 1, SheetsClient._column_to_index(col_letters)

    def _resolve_sheet_id(self, spreadsheet_id: str, sheet_name: str | None) -> int:
        """Resolve a sheet (tab) name to its numeric sheetId.

        Falls back to the first sheet when *sheet_name* is None.
        """
        meta = (
            self.service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties(sheetId,title)")
            .execute()
        )
        sheets = meta.get("sheets", [])
        if not sheets:
            raise RuntimeError("Spreadsheet has no sheets")
        if sheet_name is None:
            return sheets[0]["properties"]["sheetId"]
        for s in sheets:
            if s["properties"].get("title") == sheet_name:
                return s["properties"]["sheetId"]
        raise RuntimeError(f"Sheet '{sheet_name}' not found")

    def set_person_chip(
        self,
        spreadsheet_id: str,
        cell: str,
        email: str,
        display_format: str = "DEFAULT",
    ) -> dict:
        """Insert a person smart-chip into a single cell, replacing its contents.

        Args:
            spreadsheet_id: The spreadsheet ID
            cell: Single cell in A1 notation (e.g., "Sheet1!D2")
            email: Email address the chip links to
            display_format: DEFAULT | EMAIL | LAST_NAME_COMMA_FIRST_NAME

        Returns:
            Dict echoing the cell, email, and display format.
        """
        sheet_name, row_index, col_index = self._parse_a1_cell(cell)
        sheet_id = self._resolve_sheet_id(spreadsheet_id, sheet_name)

        request = {
            "updateCells": {
                "rows": [
                    {
                        "values": [
                            {
                                "userEnteredValue": {"stringValue": "@"},
                                "chipRuns": [
                                    {
                                        "startIndex": 0,
                                        "chip": {
                                            "personProperties": {
                                                "email": email,
                                                "displayFormat": display_format,
                                            }
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ],
                "fields": "userEnteredValue,chipRuns",
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": row_index,
                    "columnIndex": col_index,
                },
            }
        }

        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": [request]}
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")

        return {"cell": cell, "email": email, "displayFormat": display_format}

    def rename_sheet(self, spreadsheet_id: str, sheet_id: int, title: str) -> dict:
        """Rename a sheet (tab).

        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_id: The sheet ID to rename
            title: New name for the sheet

        Returns:
            Updated sheet info dict
        """
        request = {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "title": title},
                "fields": "title",
            }
        }

        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": [request]}
            ).execute()
            return {"sheetId": sheet_id, "title": title}
        except HttpError as error:
            raise RuntimeError(f"Sheets API error: {error}")
