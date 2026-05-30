import json
import base64
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

logger = structlog.get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
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
