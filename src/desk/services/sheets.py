"""Google Sheets API wrapper."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class SheetsClient:
    """Client for Google Sheets API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("sheets", "v4", credentials=credentials)

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
            Dict with spreadsheet title, sheet info, and values
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
                return {
                    "spreadsheetId": spreadsheet_id,
                    "ranges": [
                        {
                            "range": vr.get("range", ""),
                            "values": vr.get("values", []),
                        }
                        for vr in result.get("valueRanges", [])
                    ],
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

                return {
                    "spreadsheetId": spreadsheet_id,
                    "title": title,
                    "sheets": [
                        {"id": s["properties"]["sheetId"], "title": s["properties"]["title"]}
                        for s in sheets
                    ],
                    "range": result.get("range", ""),
                    "values": result.get("values", []),
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
