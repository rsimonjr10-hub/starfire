import json
import base64
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime, timedelta, timezone

logger = structlog.get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _build_credentials(token_json: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    data = json.loads(token_json)
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", SCOPES),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def get_gmail_service(token_json: str):
    from googleapiclient.discovery import build
    creds = _build_credentials(token_json)
    return build("gmail", "v1", credentials=creds)


def get_drive_service(token_json: str):
    from googleapiclient.discovery import build
    creds = _build_credentials(token_json)
    return build("drive", "v3", credentials=creds)


def get_docs_service(token_json: str):
    from googleapiclient.discovery import build
    creds = _build_credentials(token_json)
    return build("docs", "v1", credentials=creds)


def get_calendar_service(token_json: str):
    from googleapiclient.discovery import build
    creds = _build_credentials(token_json)
    return build("calendar", "v3", credentials=creds)


def get_sheets_service(token_json: str):
    from googleapiclient.discovery import build
    creds = _build_credentials(token_json)
    return build("sheets", "v4", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if "parts" in payload:
        for part in payload["parts"]:
            text = _decode_body(part)
            if text:
                return text
    return ""


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


class GmailService:
    def __init__(self, token_json: str):
        self._token_json = token_json
        self._svc = get_gmail_service(token_json)

    def list_unread(self, max_results: int = 10) -> list[dict]:
        try:
            res = self._svc.users().messages().list(
                userId="me",
                q="is:unread in:inbox",
                maxResults=max_results,
            ).execute()
            messages = res.get("messages", [])
            return [self._fetch_summary(m["id"]) for m in messages]
        except Exception as e:
            logger.error("gmail_list_unread_error", error=str(e))
            return []

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        try:
            res = self._svc.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
            messages = res.get("messages", [])
            return [self._fetch_summary(m["id"]) for m in messages]
        except Exception as e:
            logger.error("gmail_search_error", query=query, error=str(e))
            return []

    def read_thread(self, thread_id: str) -> Optional[str]:
        try:
            thread = self._svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
            parts = []
            for msg in thread.get("messages", []):
                headers = msg["payload"].get("headers", [])
                sender = _header(headers, "From")
                date = _header(headers, "Date")
                body = _decode_body(msg["payload"])[:1000]
                parts.append(f"From: {sender}\nDate: {date}\n\n{body}\n---")
            return "\n".join(parts)
        except Exception as e:
            logger.error("gmail_read_thread_error", thread_id=thread_id, error=str(e))
            return None

    def read_message(self, message_id: str) -> Optional[dict]:
        try:
            msg = self._svc.users().messages().get(userId="me", id=message_id, format="full").execute()
            headers = msg["payload"].get("headers", [])
            return {
                "id": msg["id"],
                "thread_id": msg.get("threadId"),
                "from": _header(headers, "From"),
                "to": _header(headers, "To"),
                "subject": _header(headers, "Subject"),
                "date": _header(headers, "Date"),
                "body": _decode_body(msg["payload"])[:3000],
            }
        except Exception as e:
            logger.error("gmail_read_message_error", message_id=message_id, error=str(e))
            return None

    def send_email(self, to: str, subject: str, body: str, reply_to_thread: Optional[str] = None) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            send_body = {"raw": raw}
            if reply_to_thread:
                send_body["threadId"] = reply_to_thread
            self._svc.users().messages().send(userId="me", body=send_body).execute()
            return True
        except Exception as e:
            logger.error("gmail_send_error", to=to, error=str(e))
            return False

    def _fetch_summary(self, message_id: str) -> dict:
        try:
            msg = self._svc.users().messages().get(
                userId="me", id=message_id, format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = msg["payload"].get("headers", [])
            return {
                "id": msg["id"],
                "thread_id": msg.get("threadId"),
                "from": _header(headers, "From"),
                "subject": _header(headers, "Subject"),
                "date": _header(headers, "Date"),
                "snippet": msg.get("snippet", ""),
            }
        except Exception as e:
            logger.error("gmail_fetch_summary_error", message_id=message_id, error=str(e))
            return {"id": message_id, "subject": "Error", "from": "", "snippet": ""}


class DriveService:
    def __init__(self, token_json: str):
        self._svc = get_drive_service(token_json)
        self._docs_svc = get_docs_service(token_json)

    def list_recent(self, max_results: int = 10) -> list[dict]:
        try:
            res = self._svc.files().list(
                pageSize=max_results,
                orderBy="modifiedTime desc",
                fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            ).execute()
            return res.get("files", [])
        except Exception as e:
            logger.error("drive_list_error", error=str(e))
            return []

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        try:
            res = self._svc.files().list(
                q=f"name contains '{query}' or fullText contains '{query}'",
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            ).execute()
            return res.get("files", [])
        except Exception as e:
            logger.error("drive_search_error", query=query, error=str(e))
            return []

    def read_doc(self, file_id: str) -> Optional[str]:
        try:
            import io
            from googleapiclient.http import MediaIoBaseDownload
            request = self._svc.files().export_media(fileId=file_id, mimeType="text/plain")
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue().decode("utf-8")[:5000]
        except Exception as e:
            logger.error("drive_read_doc_error", file_id=file_id, error=str(e))
            return None

    def create_doc(self, title: str, content: str) -> Optional[str]:
        """Create a Google Doc with given content. Returns the webViewLink."""
        try:
            doc = self._docs_svc.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]
            self._docs_svc.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
            ).execute()
            return f"https://docs.google.com/document/d/{doc_id}/edit"
        except Exception as e:
            logger.error("drive_create_doc_error", title=title, error=str(e))
            return None


class CalendarService:
    def __init__(self, token_json: str):
        self._token_json = token_json

    def _svc(self):
        return get_calendar_service(self._token_json)

    def create_event(
        self,
        title: str,
        start: str,
        end: Optional[str] = None,
        description: Optional[str] = None,
        tz: str = "America/New_York",
    ) -> Optional[dict]:
        try:
            if not end:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end = (start_dt + timedelta(hours=1)).isoformat()
            event = {
                "summary": title,
                "start": {"dateTime": start, "timeZone": tz},
                "end": {"dateTime": end, "timeZone": tz},
            }
            if description:
                event["description"] = description
            return self._svc().events().insert(calendarId="primary", body=event).execute()
        except Exception as e:
            logger.error("calendar_create_error", error=str(e))
            return None

    def list_upcoming(self, limit: int = 10) -> list[dict]:
        try:
            now = datetime.now(timezone.utc).isoformat()
            result = self._svc().events().list(
                calendarId="primary",
                timeMin=now,
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return result.get("items", [])
        except Exception as e:
            logger.error("calendar_list_error", error=str(e))
            return []


class SheetsService:
    # Expected columns: Date | Symbol | Type | Entry | Exit | Contracts | P/L | Notes
    HEADERS = ["Date", "Symbol", "Type", "Entry", "Exit", "Contracts", "P/L", "Notes"]
    DEFAULT_TAB = "Sheet1"

    def __init__(self, token_json: str):
        self._token_json = token_json

    def _svc(self):
        return get_sheets_service(self._token_json)

    @staticmethod
    def _range(tab: Optional[str]) -> str:
        tab = tab or SheetsService.DEFAULT_TAB
        # Quote tab names that contain spaces or special chars
        quoted = f"'{tab}'" if not tab.isidentifier() else tab
        return f"{quoted}!A:H"

    def create_spreadsheet(
        self,
        title: str,
        tab: Optional[str] = None,
        with_headers: bool = True,
    ) -> Optional[dict]:
        """Create a new spreadsheet. Returns {id, url}."""
        try:
            body: dict = {"properties": {"title": title}}
            if tab:
                body["sheets"] = [{"properties": {"title": tab}}]
            ss = self._svc().spreadsheets().create(
                body=body, fields="spreadsheetId,spreadsheetUrl",
            ).execute()
            sid = ss["spreadsheetId"]
            if with_headers:
                self.ensure_headers(sid, tab)
            return {"id": sid, "url": ss.get("spreadsheetUrl", "")}
        except Exception as e:
            logger.error("sheets_create_error", title=title, error=str(e))
            return None

    def add_tab(self, spreadsheet_id: str, tab: str, with_headers: bool = True) -> bool:
        """Add a new tab (worksheet) to an existing spreadsheet."""
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
            ).execute()
            if with_headers:
                self.ensure_headers(spreadsheet_id, tab)
            return True
        except Exception as e:
            logger.error("sheets_add_tab_error", tab=tab, error=str(e))
            return False

    def _grid_id(self, spreadsheet_id: str, tab: Optional[str]) -> Optional[int]:
        tab = tab or self.DEFAULT_TAB
        try:
            meta = self._svc().spreadsheets().get(
                spreadsheetId=spreadsheet_id, fields="sheets.properties",
            ).execute()
            for s in meta.get("sheets", []):
                if s["properties"]["title"] == tab:
                    return s["properties"]["sheetId"]
        except Exception as e:
            logger.error("sheets_grid_id_error", error=str(e))
        return None

    def delete_rows_matching(
        self,
        spreadsheet_id: str,
        symbol: Optional[str] = None,
        date: Optional[str] = None,
        tab: Optional[str] = None,
    ) -> int:
        """Delete data rows matching symbol and/or date prefix. Returns count removed."""
        try:
            grid_id = self._grid_id(spreadsheet_id, tab)
            if grid_id is None:
                return 0
            rows = self._svc().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=self._range(tab),
            ).execute().get("values", [])

            to_delete = []
            for i, row in enumerate(rows):
                if i == 0:  # header row
                    continue
                padded = row + [""] * (8 - len(row))
                r_date, r_symbol = padded[0], padded[1]
                if symbol and r_symbol.upper() != symbol.upper():
                    continue
                if date and not str(r_date).startswith(date):
                    continue
                to_delete.append(i)  # 0-based grid row index

            if not to_delete:
                return 0

            # Delete bottom-up so earlier indices stay valid
            requests = [
                {"deleteDimension": {"range": {
                    "sheetId": grid_id, "dimension": "ROWS",
                    "startIndex": idx, "endIndex": idx + 1,
                }}}
                for idx in sorted(to_delete, reverse=True)
            ]
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests},
            ).execute()
            return len(to_delete)
        except Exception as e:
            logger.error("sheets_delete_rows_error", error=str(e))
            return 0

    def trash_spreadsheet(self, spreadsheet_id: str) -> bool:
        """Move a spreadsheet to Drive trash (recoverable for 30 days)."""
        try:
            drive = get_drive_service(self._token_json)
            drive.files().update(fileId=spreadsheet_id, body={"trashed": True}).execute()
            return True
        except Exception as e:
            logger.error("sheets_trash_error", error=str(e))
            return False

    def find_spreadsheet_by_name(self, name: str) -> Optional[str]:
        """Resolve a spreadsheet ID from its name via Drive search."""
        try:
            drive = get_drive_service(self._token_json)
            safe = name.replace("'", "\\'")
            res = drive.files().list(
                q=(
                    "mimeType='application/vnd.google-apps.spreadsheet' "
                    f"and name contains '{safe}' and trashed=false"
                ),
                pageSize=10,
                orderBy="modifiedTime desc",
                fields="files(id, name)",
            ).execute()
            files = res.get("files", [])
            if not files:
                return None
            # Prefer an exact (case-insensitive) name match
            for f in files:
                if f.get("name", "").lower() == name.lower():
                    return f["id"]
            return files[0]["id"]
        except Exception as e:
            logger.error("sheets_find_error", name=name, error=str(e))
            return None

    def list_tabs(self, spreadsheet_id: str) -> list[str]:
        """Return the tab (worksheet) names in a spreadsheet."""
        try:
            meta = self._svc().spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties.title",
            ).execute()
            return [s["properties"]["title"] for s in meta.get("sheets", [])]
        except Exception as e:
            logger.error("sheets_list_tabs_error", error=str(e))
            return []

    def ensure_headers(self, spreadsheet_id: str, tab: Optional[str] = None) -> None:
        """Write the P/L header row if the tab's first row is empty."""
        try:
            rng = self._range(tab)
            existing = self._svc().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=rng,
            ).execute().get("values", [])
            if not existing:
                self._svc().spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=self._range(tab).replace(":H", "1:H1"),
                    valueInputOption="USER_ENTERED",
                    body={"values": [self.HEADERS]},
                ).execute()
        except Exception as e:
            logger.error("sheets_ensure_headers_error", error=str(e))

    def append_pl_row(
        self,
        spreadsheet_id: str,
        date: str,
        symbol: str,
        trade_type: str,
        entry: float,
        exit_price: float,
        contracts: int,
        pl: float,
        notes: str = "",
        tab: Optional[str] = None,
    ) -> bool:
        try:
            self.ensure_headers(spreadsheet_id, tab)
            values = [[date, symbol.upper(), trade_type.upper(), entry, exit_price, contracts, pl, notes]]
            self._svc().spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=self._range(tab),
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_append_error", error=str(e))
            return False

    def get_pl_summary(
        self,
        spreadsheet_id: str,
        date_prefix: Optional[str] = None,
        tab: Optional[str] = None,
    ) -> list[dict]:
        try:
            result = self._svc().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=self._range(tab),
            ).execute()
            rows = result.get("values", [])
            if len(rows) <= 1:
                return []
            headers = ["date", "symbol", "type", "entry", "exit", "contracts", "pl", "notes"]
            records = []
            for row in rows[1:]:
                padded = row + [""] * (8 - len(row))
                record = dict(zip(headers, padded))
                if not date_prefix or record["date"].startswith(date_prefix):
                    records.append(record)
            return records
        except Exception as e:
            logger.error("sheets_get_error", error=str(e))
            return []

    # ── READING ────────────────────────────────────────────────────────────

    def read_range(self, spreadsheet_id: str, range_a1: str) -> list[list]:
        """Read any A1-notation range. Returns list-of-rows."""
        try:
            result = self._svc().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_a1,
            ).execute()
            return result.get("values", [])
        except Exception as e:
            logger.error("sheets_read_range_error", error=str(e))
            return []

    def read_cell(self, spreadsheet_id: str, cell: str) -> Optional[str]:
        """Read a single cell, e.g. 'Sheet1!B3'."""
        rows = self.read_range(spreadsheet_id, cell)
        return rows[0][0] if rows and rows[0] else None

    def find_rows(
        self,
        spreadsheet_id: str,
        column: int,
        value: str,
        tab: Optional[str] = None,
        exact: bool = True,
    ) -> list[dict]:
        """Find all rows where column (0-based) matches value."""
        rows = self.read_range(spreadsheet_id, self._range(tab))
        if not rows:
            return []
        headers = ["date", "symbol", "type", "entry", "exit", "contracts", "pl", "notes"]
        matches = []
        for i, row in enumerate(rows):
            if i == 0:
                continue
            padded = row + [""] * (8 - len(row))
            cell_val = padded[column] if column < len(padded) else ""
            hit = (cell_val.lower() == value.lower()) if exact else (value.lower() in cell_val.lower())
            if hit:
                record = dict(zip(headers, padded))
                record["_row_index"] = i
                matches.append(record)
        return matches

    # ── EDITING ────────────────────────────────────────────────────────────

    def update_cell(
        self, spreadsheet_id: str, cell: str, value, tab: Optional[str] = None,
    ) -> bool:
        """Update a single cell. cell can be A1 notation (absolute) or 'B3'."""
        if tab and "!" not in cell:
            quoted = f"'{tab}'" if not tab.isidentifier() else tab
            cell = f"{quoted}!{cell}"
        try:
            self._svc().spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=cell,
                valueInputOption="USER_ENTERED",
                body={"values": [[value]]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_update_cell_error", error=str(e))
            return False

    def update_range(
        self, spreadsheet_id: str, range_a1: str, values: list[list],
    ) -> bool:
        """Write a 2D list of values to any A1-notation range."""
        try:
            self._svc().spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_update_range_error", error=str(e))
            return False

    def insert_row(
        self,
        spreadsheet_id: str,
        row_index: int,
        values: list,
        tab: Optional[str] = None,
    ) -> bool:
        """Insert a new row BEFORE row_index (1-based) and write values."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"insertDimension": {
                    "range": {
                        "sheetId": grid_id,
                        "dimension": "ROWS",
                        "startIndex": row_index - 1,
                        "endIndex": row_index,
                    },
                    "inheritFromBefore": False,
                }}]},
            ).execute()
            tab_str = f"'{tab}'" if tab and not tab.isidentifier() else (tab or "Sheet1")
            self._svc().spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_str}!A{row_index}",
                valueInputOption="USER_ENTERED",
                body={"values": [values]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_insert_row_error", error=str(e))
            return False

    def find_and_replace(
        self, spreadsheet_id: str, find: str, replace: str, tab: Optional[str] = None,
    ) -> int:
        """Replace all occurrences of find with replace. Returns replacement count."""
        try:
            body: dict = {
                "requests": [{
                    "findReplace": {
                        "find": find,
                        "replacement": replace,
                        "allSheets": tab is None,
                        "matchCase": False,
                        "matchEntireCell": False,
                    }
                }]
            }
            if tab:
                grid_id = self._grid_id(spreadsheet_id, tab)
                if grid_id is not None:
                    body["requests"][0]["findReplace"]["sheetId"] = grid_id
            result = self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body,
            ).execute()
            replies = result.get("replies", [{}])
            return replies[0].get("findReplace", {}).get("occurrencesChanged", 0)
        except Exception as e:
            logger.error("sheets_find_replace_error", error=str(e))
            return 0

    # ── CLEARING / DELETING ────────────────────────────────────────────────

    def clear_range(self, spreadsheet_id: str, range_a1: str) -> bool:
        """Clear values from a range (keeps formatting)."""
        try:
            self._svc().spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id, range=range_a1,
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_clear_range_error", error=str(e))
            return False

    def delete_tab(self, spreadsheet_id: str, tab: str) -> bool:
        """Delete a worksheet/tab from a spreadsheet."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": grid_id}}]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_delete_tab_error", error=str(e))
            return False

    def delete_columns(
        self, spreadsheet_id: str, start_col: int, end_col: int, tab: Optional[str] = None,
    ) -> bool:
        """Delete columns start_col..end_col (0-based, exclusive end)."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteDimension": {"range": {
                    "sheetId": grid_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_col,
                    "endIndex": end_col,
                }}}]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_delete_columns_error", error=str(e))
            return False

    # ── FORMATTING HELPERS ─────────────────────────────────────────────────

    @staticmethod
    def _rgb(hex_color: str) -> dict:
        """Convert #RRGGBB to Sheets API color object."""
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return {"red": r / 255, "green": g / 255, "blue": b / 255}

    @staticmethod
    def _cell_format(
        bg: Optional[str] = None,
        bold: bool = False,
        fg: Optional[str] = None,
        font_size: Optional[int] = None,
        h_align: Optional[str] = None,
        number_format: Optional[str] = None,
    ) -> dict:
        fmt: dict = {}
        if bg:
            fmt["backgroundColor"] = SheetsService._rgb(bg)
        text: dict = {}
        if bold:
            text["bold"] = True
        if fg:
            text["foregroundColor"] = SheetsService._rgb(fg)
        if font_size:
            text["fontSize"] = font_size
        if text:
            fmt["textFormat"] = text
        if h_align:
            fmt["horizontalAlignment"] = h_align.upper()
        if number_format:
            fmt["numberFormat"] = {"type": "NUMBER", "pattern": number_format}
        return fmt

    def _repeat_cell(
        self, grid_id: int, start_row: int, end_row: int,
        start_col: int, end_col: int, cell_format: dict,
    ) -> dict:
        return {
            "repeatCell": {
                "range": {
                    "sheetId": grid_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {"userEnteredFormat": cell_format},
                "fields": "userEnteredFormat(" + ",".join(cell_format.keys()) + ")",
            }
        }

    def format_range(
        self,
        spreadsheet_id: str,
        range_a1: str,
        bg: Optional[str] = None,
        bold: bool = False,
        fg: Optional[str] = None,
        font_size: Optional[int] = None,
        h_align: Optional[str] = None,
        number_format: Optional[str] = None,
        tab: Optional[str] = None,
    ) -> bool:
        """Apply arbitrary formatting to any A1-notation range."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        cell_fmt = self._cell_format(bg, bold, fg, font_size, h_align, number_format)
        if not cell_fmt:
            return True
        # Parse A1 to row/col indices
        try:
            rows, start_row, end_row, start_col, end_col = \
                self._a1_to_grid(range_a1, spreadsheet_id, tab)
            request = self._repeat_cell(grid_id, start_row, end_row, start_col, end_col, cell_fmt)
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": [request]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_format_range_error", error=str(e))
            return False

    def _a1_to_grid(self, range_a1: str, spreadsheet_id: str, tab: Optional[str]):
        """Convert A1 notation (e.g. 'A1:H1') to 0-based row/col grid indices."""
        import re
        # Strip sheet prefix
        if "!" in range_a1:
            range_a1 = range_a1.split("!")[-1]

        def col_to_idx(col: str) -> int:
            idx = 0
            for ch in col.upper():
                idx = idx * 26 + (ord(ch) - ord("A") + 1)
            return idx - 1

        m = re.match(r"([A-Za-z]+)(\d+)(?::([A-Za-z]+)(\d+))?", range_a1)
        if not m:
            raise ValueError(f"Cannot parse A1 range: {range_a1}")
        sc, sr, ec, er = m.group(1), m.group(2), m.group(3), m.group(4)
        start_row = int(sr) - 1
        start_col = col_to_idx(sc)
        end_row = (int(er) if er else int(sr))
        end_col = (col_to_idx(ec) + 1) if ec else (start_col + 1)
        return None, start_row, end_row, start_col, end_col

    def set_column_widths(
        self,
        spreadsheet_id: str,
        widths: dict,
        tab: Optional[str] = None,
    ) -> bool:
        """Set column widths. widths = {col_index: pixels, ...} (0-based)."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        requests = [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": grid_id,
                        "dimension": "COLUMNS",
                        "startIndex": col,
                        "endIndex": col + 1,
                    },
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize",
                }
            }
            for col, px in widths.items()
        ]
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_col_width_error", error=str(e))
            return False

    def freeze(
        self, spreadsheet_id: str, rows: int = 1, cols: int = 0, tab: Optional[str] = None,
    ) -> bool:
        """Freeze the top N rows (and optionally M columns)."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"updateSheetProperties": {
                    "properties": {
                        "sheetId": grid_id,
                        "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols},
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                }}]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_freeze_error", error=str(e))
            return False

    def add_conditional_formatting(
        self,
        spreadsheet_id: str,
        range_a1: str,
        positive_color: str = "#b7e1cd",
        negative_color: str = "#f4cccc",
        tab: Optional[str] = None,
    ) -> bool:
        """Add green/red conditional formatting for positive/negative numbers."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            _, start_row, end_row, start_col, end_col = \
                self._a1_to_grid(range_a1, spreadsheet_id, tab)
            cell_range = {
                "sheetId": grid_id,
                "startRowIndex": start_row,
                "endRowIndex": 1000,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            }
            requests = [
                {"addConditionalFormatRule": {
                    "rule": {
                        "ranges": [cell_range],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": self._rgb(positive_color)},
                        },
                    },
                    "index": 0,
                }},
                {"addConditionalFormatRule": {
                    "rule": {
                        "ranges": [cell_range],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": self._rgb(negative_color)},
                        },
                    },
                    "index": 1,
                }},
            ]
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_conditional_format_error", error=str(e))
            return False

    def rename_tab(self, spreadsheet_id: str, old_name: str, new_name: str) -> bool:
        """Rename a worksheet tab."""
        grid_id = self._grid_id(spreadsheet_id, old_name)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"updateSheetProperties": {
                    "properties": {"sheetId": grid_id, "title": new_name},
                    "fields": "title",
                }}]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_rename_tab_error", error=str(e))
            return False

    def auto_resize_columns(
        self, spreadsheet_id: str, start_col: int = 0, end_col: int = 8,
        tab: Optional[str] = None,
    ) -> bool:
        """Auto-resize columns to fit their content."""
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": grid_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_col,
                        "endIndex": end_col,
                    }
                }}]},
            ).execute()
            return True
        except Exception as e:
            logger.error("sheets_auto_resize_error", error=str(e))
            return False

    def apply_full_pl_formatting(
        self,
        spreadsheet_id: str,
        tab: Optional[str] = None,
        header_bg: str = "#1a3a5c",
        header_fg: str = "#ffffff",
        positive_color: str = "#b7e1cd",
        negative_color: str = "#f4cccc",
    ) -> bool:
        """
        One-shot full P/L sheet formatting:
        - Dark header row (bold, white text)
        - Currency format for Entry/Exit/P/L columns
        - Conditional green/red on P/L column
        - Freeze row 1
        - Auto-resize all columns
        - Alternating light row background
        """
        grid_id = self._grid_id(spreadsheet_id, tab)
        if grid_id is None:
            return False
        try:
            svc = self._svc()
            requests = [
                # Bold dark header row
                self._repeat_cell(
                    grid_id, 0, 1, 0, 8,
                    self._cell_format(
                        bg=header_bg, bold=True, fg=header_fg,
                        font_size=11, h_align="CENTER",
                    ),
                ),
                # Currency format — Entry (col 3), Exit (col 4), P/L (col 6)
                self._repeat_cell(
                    grid_id, 1, 1000, 3, 5,
                    self._cell_format(number_format='"$"#,##0.00'),
                ),
                self._repeat_cell(
                    grid_id, 1, 1000, 6, 7,
                    self._cell_format(number_format='"$"#,##0.00'),
                ),
                # Center-align: Date (0), Symbol (1), Type (2), Contracts (5)
                self._repeat_cell(
                    grid_id, 1, 1000, 0, 3,
                    self._cell_format(h_align="CENTER"),
                ),
                self._repeat_cell(
                    grid_id, 1, 1000, 5, 6,
                    self._cell_format(h_align="CENTER"),
                ),
                # Freeze row 1
                {"updateSheetProperties": {
                    "properties": {
                        "sheetId": grid_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }},
                # Auto-resize all columns
                {"autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": grid_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 8,
                    }
                }},
            ]
            svc.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests},
            ).execute()

            # Conditional formatting on P/L column (G = index 6) — separate call
            pl_range = f"G2:G1000"
            self.add_conditional_formatting(
                spreadsheet_id, pl_range,
                positive_color=positive_color,
                negative_color=negative_color,
                tab=tab,
            )
            return True
        except Exception as e:
            logger.error("sheets_full_format_error", error=str(e))
            return False
            return []
