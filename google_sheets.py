"""
google_sheets.py  –  Google Sheets sync helper for REIA Refund Tracker
------------------------------------------------------------------------
Behaviour:
  - ONLY appends new entries to the existing sheet
  - Never clears or reformats the sheet
  - Matches the exact column order of 'Cx Refund details' tab
  - Delete in web app does NOT affect Google Sheets

Sheet column order (row 7 = headers):
  No | Customer Name | Store Location | Customer Email | Phone |
  Account No. | Ifsc | Bank | Bank Name | Refund Identified Date |
  Reason for Refund | Description / Notes | Total Invoice Amount |
  Total Amount Received | Net Refund Amount | Approved By |
  Refund initiated Date | Days Outstanding | Actual Payment Date | Status
"""

import os
import json

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Exact column order matching your sheet
SHEET_COLUMNS = [
    "no", "name", "store", "email", "phone",
    "acc", "ifsc", "bank", "bankname", "date",
    "reason", "notes", "invoice", "received", "net",
    "approved_by", "refund_initiated", "days_out", "actual_date", "status",
]

def _record_to_row(record: dict) -> list:
    """Convert a record dict to a list matching the sheet column order."""
    row = []
    for key in SHEET_COLUMNS:
        val = record.get(key, "")
        row.append(val if val != "" else "")
    return row


class GoogleSheetsSync:
    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._worksheet = None

        self.credentials_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
        self.credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self.worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "Cx Refund details")

    def is_configured(self) -> bool:
        if not GSPREAD_AVAILABLE:
            return False
        has_creds = bool(self.credentials_file or self.credentials_json)
        return has_creds and bool(self.spreadsheet_id)

    def _connect(self):
        if self._worksheet:
            return

        if self.credentials_json:
            info = json.loads(self.credentials_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        elif self.credentials_file:
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=SCOPES)
        else:
            raise RuntimeError("No Google credentials configured.")

        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)

        try:
            self._worksheet = self._spreadsheet.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            raise RuntimeError(
                f"Sheet tab '{self.worksheet_name}' not found. "
                f"Make sure the tab is named exactly '{self.worksheet_name}'."
            )

    def _get_sheet(self):
        self._connect()
        return self._worksheet

    def _find_next_empty_row(self, ws) -> int:
        """
        Find the next truly empty row in the sheet.
        Your sheet has pre-numbered rows (just a number in col A, rest empty).
        We look for the first row after row 7 (header) where col B (Name) is empty.
        Data starts at row 8.
        """
        col_b = ws.col_values(2)  # column B = Customer Name
        for i, val in enumerate(col_b):
            row_num = i + 1
            if row_num < 8:
                continue  # skip title rows and header
            if str(val).strip() == "":
                return row_num
        return len(col_b) + 1

    def append_row(self, record: dict) -> None:
        """
        Append a new record into the next empty row in the sheet.
        Preserves all existing formatting and data.
        """
        ws = self._get_sheet()
        target_row = self._find_next_empty_row(ws)
        row_data = _record_to_row(record)

        ws.update(
            f"A{target_row}",
            [row_data],
            value_input_option="USER_ENTERED"
        )
        print(f"Google Sheets: wrote record #{record.get('no')} to row {target_row}")

    def full_sync(self, records: list) -> str:
        """Kept for compatibility only — does nothing now."""
        if self._spreadsheet:
            return self._spreadsheet.url
        self._connect()
        return self._spreadsheet.url

    def delete_row(self, record_no: int) -> bool:
        """Delete is intentionally disabled — web app deletes locally only."""
        return False
    