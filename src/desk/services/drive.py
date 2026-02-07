"""Google Drive API wrapper."""

import io
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


class DriveClient:
    """Client for Google Drive API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("drive", "v3", credentials=credentials)

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Search for files matching query.

        Args:
            query: Drive search query (e.g., "name contains 'report'")
            max_results: Maximum number of results

        Returns:
            List of file metadata dicts
        """
        try:
            results = (
                self.service.files()
                .list(
                    q=query,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, size, owners, webViewLink)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )
            return results.get("files", [])
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def read(self, file_id: str) -> str:
        """Read file content as text (exports Google Docs/Sheets as plain text).

        Args:
            file_id: The file ID

        Returns:
            File content as string
        """
        try:
            # First get file metadata to determine type
            meta = self.service.files().get(fileId=file_id, fields="mimeType, name").execute()
            mime = meta["mimeType"]

            # Google Workspace files need export
            if mime == "application/vnd.google-apps.document":
                return self._export(file_id, "text/plain")
            elif mime == "application/vnd.google-apps.spreadsheet":
                return self._export(file_id, "text/csv")
            elif mime == "application/vnd.google-apps.presentation":
                return self._export(file_id, "text/plain")
            else:
                # Check file size before downloading (50MB limit)
                size_meta = self.service.files().get(fileId=file_id, fields="size").execute()
                size = int(size_meta.get("size", 0))
                if size > 50 * 1024 * 1024:
                    raise RuntimeError(
                        f"File is {size // (1024 * 1024)}MB — too large to read as text. "
                        "Use 'desk drive download' for large files."
                    )
                content = self.service.files().get_media(fileId=file_id).execute()
                if isinstance(content, bytes):
                    return content.decode("utf-8", errors="replace")
                return str(content)
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def info(self, file_id: str) -> dict:
        """Get detailed file metadata.

        Args:
            file_id: The file ID

        Returns:
            File metadata dict
        """
        try:
            return (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, modifiedTime, createdTime, size, owners, "
                    "parents, webViewLink, description, starred",
                )
                .execute()
            )
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def recent(self, max_results: int = 20) -> list[dict]:
        """List recently modified files.

        Args:
            max_results: Maximum number of results

        Returns:
            List of file metadata dicts
        """
        try:
            results = (
                self.service.files()
                .list(
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, webViewLink)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )
            return results.get("files", [])
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def upload(self, local_path: str, folder_id: str | None = None) -> dict:
        """Upload a local file to Drive.

        Args:
            local_path: Path to local file
            folder_id: Optional parent folder ID

        Returns:
            File metadata dict
        """
        path = Path(local_path)
        if not path.exists():
            raise RuntimeError(f"File not found: {local_path}")

        file_metadata = {"name": path.name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        try:
            media = MediaFileUpload(str(path))
            result = (
                self.service.files()
                .create(body=file_metadata, media_body=media, fields="id, name, webViewLink")
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def download(self, file_id: str, dest_path: str) -> str:
        """Download a file to local filesystem.

        Args:
            file_id: The file ID
            dest_path: Local directory or file path to save to

        Returns:
            Path to downloaded file
        """
        try:
            meta = self.service.files().get(fileId=file_id, fields="name, mimeType").execute()
            name = meta["name"]
            mime = meta["mimeType"]

            dest = Path(dest_path)
            # Sanitize filename to prevent path traversal
            safe_name = Path(name).name
            if dest.is_dir():
                dest = dest / safe_name

            # Google Workspace files need export
            export_map = {
                "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
                "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
                "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
            }

            if mime in export_map:
                export_mime, ext = export_map[mime]
                if not dest.suffix:
                    dest = dest.with_suffix(ext)
                request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
            else:
                request = self.service.files().get_media(fileId=file_id)

            with io.FileIO(str(dest), "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            return str(dest)
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def mkdir(self, name: str, parent_id: str | None = None) -> dict:
        """Create a folder in Drive.

        Args:
            name: Folder name
            parent_id: Optional parent folder ID

        Returns:
            Folder metadata dict
        """
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]

        try:
            result = (
                self.service.files()
                .create(body=file_metadata, fields="id, name, webViewLink")
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def move(self, file_id: str, folder_id: str) -> dict:
        """Move a file to a different folder.

        Args:
            file_id: The file to move
            folder_id: Destination folder ID

        Returns:
            Updated file metadata
        """
        try:
            # Get current parents to remove
            file = self.service.files().get(fileId=file_id, fields="parents").execute()
            previous_parents = ",".join(file.get("parents", []))

            result = (
                self.service.files()
                .update(
                    fileId=file_id,
                    addParents=folder_id,
                    removeParents=previous_parents,
                    fields="id, name, parents, webViewLink",
                )
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def trash(self, file_id: str) -> dict:
        """Move a file to trash.

        Args:
            file_id: The file ID

        Returns:
            Updated file metadata
        """
        try:
            result = (
                self.service.files()
                .update(fileId=file_id, body={"trashed": True}, fields="id, name, trashed")
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def share(self, file_id: str, email: str, role: str = "writer") -> dict:
        """Share a file with someone.

        Args:
            file_id: The file ID
            email: Email address to share with
            role: Permission role (reader, commenter, writer)

        Returns:
            Permission dict
        """
        try:
            permission = (
                self.service.permissions()
                .create(
                    fileId=file_id,
                    body={"type": "user", "role": role, "emailAddress": email},
                    sendNotificationEmail=True,
                    fields="id, role, emailAddress",
                )
                .execute()
            )
            return permission
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def star(self, file_id: str, starred: bool = True) -> dict:
        """Star or unstar a file.

        Args:
            file_id: The file ID
            starred: True to star, False to unstar

        Returns:
            Updated file metadata
        """
        try:
            result = (
                self.service.files()
                .update(
                    fileId=file_id,
                    body={"starred": starred},
                    fields="id, name, starred",
                )
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def copy(
        self, file_id: str, name: str | None = None, folder_id: str | None = None
    ) -> dict:
        """Copy a file in Drive.

        Args:
            file_id: The file ID to copy
            name: Optional new name for the copy
            folder_id: Optional destination folder ID

        Returns:
            New file metadata dict
        """
        try:
            body = {}
            if name:
                body["name"] = name
            if folder_id:
                body["parents"] = [folder_id]

            result = (
                self.service.files()
                .copy(
                    fileId=file_id,
                    body=body if body else None,
                    fields="id, name, webViewLink, parents",
                )
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Drive API error: {error}")

    def _export(self, file_id: str, mime_type: str) -> str:
        """Export a Google Workspace file."""
        content = self.service.files().export(fileId=file_id, mimeType=mime_type).execute()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return str(content)
