import json
import structlog
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)


class GoogleDriveIntegration:
    """
    Optional Google Drive integration.
    Provides file search, metadata retrieval, and document summarization hooks.
    Requires GOOGLE_DRIVE_CREDENTIALS_JSON and GOOGLE_DRIVE_TOKEN_JSON in env.
    """

    def __init__(self):
        self._service = None
        self._enabled = bool(settings.google_drive_credentials_json)

    def is_enabled(self) -> bool:
        return self._enabled

    def _get_service(self):
        if self._service:
            return self._service

        if not self._enabled:
            raise RuntimeError("Google Drive integration not configured.")

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds_data = json.loads(settings.google_drive_credentials_json)
            token_data = json.loads(settings.google_drive_token_json or "{}")

            creds = Credentials.from_authorized_user_info(token_data or creds_data)
            self._service = build("drive", "v3", credentials=creds)
            return self._service
        except Exception as e:
            logger.error("google_drive_init_error", error=str(e))
            raise

    async def search_files(self, query: str, max_results: int = 10) -> list[dict]:
        """Search Google Drive files by name or content query."""
        try:
            service = self._get_service()
            results = service.files().list(
                q=f"name contains '{query}'",
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            ).execute()
            return results.get("files", [])
        except Exception as e:
            logger.error("gdrive_search_error", query=query, error=str(e))
            return []

    async def get_file_metadata(self, file_id: str) -> Optional[dict]:
        """Retrieve metadata for a specific file."""
        try:
            service = self._get_service()
            return service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, webViewLink, description",
            ).execute()
        except Exception as e:
            logger.error("gdrive_metadata_error", file_id=file_id, error=str(e))
            return None

    async def get_file_content(self, file_id: str) -> Optional[str]:
        """Download and return text content of a Google Doc."""
        try:
            from googleapiclient.http import MediaIoBaseDownload
            import io

            service = self._get_service()
            request = service.files().export_media(
                fileId=file_id,
                mimeType="text/plain",
            )
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue().decode("utf-8")
        except Exception as e:
            logger.error("gdrive_content_error", file_id=file_id, error=str(e))
            return None
