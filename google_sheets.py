"""
google_sheets.py  –  Google Sheets as primary database for REIA Refund Tracker
-------------------------------------------------------------------------------
Sheet structure:
  Row 1-5: Title/header rows
  Row 6-7: Column headers
  Row 8+:  Data rows

Column order (0-indexed):
  0:No  1:Customer Name  2:Store Location  3:Email  4:Phone
  5:Account No  6:IFSC  7:Bank  8:Bank Name  9:Date
  10:Reason  11:Notes  12:Invoice  13:Received  14:Net
  15:Approved By  16:Refund Initiated  17:Days Out  18:Actual Date  19:Status
"""

import os
import json
from datetime import date, datetime

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

DATA_ROW_START = 8  # First row with actual data

def _clean_amount(val):
    """Convert '₹32,859.00' or '32859' to float."""
    if val is None or str(val).strip() == "":
        return 0.0
    cleaned = str(val).replace("₹", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except:
        return 0.0

def _clean_int(val):
    try:
        return int(float(str(val).strip())) if str(val).strip() else 0
    except:
        return 0

def _row_to_record(row, row_index):
    """Convert a sheet row (list) to a record dict."""
    def get(i):
        try:
            return str(row[i]).strip() if i < len(row) else ""
        except:
            return ""

    return {
        "no":              _clean_int(get(0)) or row_index,
        "name":            get(1),
        "store":           get(2),
        "email":           get(3),
        "phone":           get(4),
        "acc":             get(5),
        "ifsc":            get(6),
        "bank":            get(7),
        "bankname":        get(8),
        "date":            get(9),
        "reason":          get(10),
        "notes":           get(11),
        "invoice":         _clean_amount(get(12)),
        "received":        _clean_amount(get(13)),
        "net":             _clean_amount(get(14)),
        "approved_by":     get(15),
        "refund_initiated":get(16),
        "days_out":        _clean_int(get(17)),
        "actual_date":     get(18),
        "status":          get(19) or "Pending",
    }

def _record_to_row(record):
    """Convert a record dict to a sheet row list."""
    return [
        record.get("no", ""),
        record.get("name", ""),
        record.get("store", ""),
        record.get("email", ""),
        record.get("phone", ""),
        record.get("acc", ""),
        record.get("ifsc", ""),
        record.get("bank", ""),
        record.get("bankname", ""),
        record.get("date", ""),
        record.get("reason", ""),
        record.get("notes", ""),
        record.get("invoice", 0),
        record.get("received", 0),
        record.get("net", 0),
        record.get("approved_by", ""),
        record.get("refund_initiated", ""),
        record.get("days_out", 0),
        record.get("actual_date", ""),
        record.get("status", "Pending"),
    ]


class GoogleSheetsSync:
    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._worksheet = None

        self.credentials_json  = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
        self.credentials_file  = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
        self.spreadsheet_id    = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self.worksheet_name    = os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "Cx Refund details")

    def is_configured(self):
        if not GSPREAD_AVAILABLE:
            return False
        has_creds = bool(self.credentials_json or self.credentials_file)
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

        self._client      = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)
        try:
            self._worksheet = self._spreadsheet.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            raise RuntimeError(f"Sheet tab '{self.worksheet_name}' not found.")

    # ── READ ────────────────────────────────────────────────────────────────

    def load_all_records(self):
        """Load all records from Google Sheets. Returns list of dicts."""
        self._connect()
        all_values = self._worksheet.get_all_values()
        records = []
        counter = 1
        for i, row in enumerate(all_values):
            actual_row_num = i + 1
            if actual_row_num < DATA_ROW_START:
                continue
            # Skip empty rows (no name in column B)
            name = row[1].strip() if len(row) > 1 else ""
            if not name:
                continue
            record = _row_to_record(row, counter)
            records.append(record)
            counter += 1
        return records

    # ── WRITE ───────────────────────────────────────────────────────────────

    def _find_next_empty_row(self):
        """Find next empty row in sheet (col B = Customer Name is empty)."""
        col_b = self._worksheet.col_values(2)
        for i, val in enumerate(col_b):
            row_num = i + 1
            if row_num < DATA_ROW_START:
                continue
            if str(val).strip() == "":
                return row_num
        return len(col_b) + 1

    def append_row(self, record):
        """Append a new record to the next empty row."""
        self._connect()
        target_row = self._find_next_empty_row()
        row_data   = _record_to_row(record)
        self._worksheet.update(
            f"A{target_row}",
            [row_data],
            value_input_option="USER_ENTERED"
        )
        print(f"Google Sheets: wrote record #{record.get('no')} to row {target_row}")

    def update_record(self, record):
        """Find and update an existing record by 'no' in column A."""
        self._connect()
        col_a = self._worksheet.col_values(1)
        for i, val in enumerate(col_a):
            row_num = i + 1
            if row_num < DATA_ROW_START:
                continue
            if str(val).strip() == str(record.get("no", "")):
                row_data = _record_to_row(record)
                self._worksheet.update(
                    f"A{row_num}",
                    [row_data],
                    value_input_option="USER_ENTERED"
                )
                print(f"Google Sheets: updated record #{record.get('no')} at row {row_num}")
                return True
        return False

    def delete_row(self, record_no):
        """Clear the row matching record_no in column A."""
        self._connect()
        col_a = self._worksheet.col_values(1)
        for i, val in enumerate(col_a):
            row_num = i + 1
            if row_num < DATA_ROW_START:
                continue
            if str(val).strip() == str(record_no):
                # Clear columns A-T for that row
                self._worksheet.batch_clear([f"A{row_num}:T{row_num}"])
                print(f"Google Sheets: cleared row {row_num} for record #{record_no}")
                return True
        return False

    def full_sync(self, records):
        """Legacy compat — returns sheet URL."""
        self._connect()
        return self._spreadsheet.url
    