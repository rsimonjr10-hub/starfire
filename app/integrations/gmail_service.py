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
