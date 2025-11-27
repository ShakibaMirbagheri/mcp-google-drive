"""Google Drive MCP Server implementation."""
import io
import pickle
import argparse
from typing import Any, Optional
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth.exceptions import RefreshError
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
class GoogleDriveClient:
    """Client for interacting with Google Drive."""
    def __init__(self, token_path: Optional[str] = None):
        """Initialize the Google Drive client.
        Args:
            token_path: Path to the token file. If None, defaults to 'tokens.json' in current directory.
        """
        self.SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
        self.token_path = Path(token_path or "tokens.json")
        self.service = self._load_service()
    def _load_service(self):
        suffix = self.token_path.suffix.lower()
        try:
            if suffix == ".json":
                creds = self._load_credentials_from_json()
            elif suffix == ".pickle":
                creds = self._load_credentials_from_pickle()
            else:
                raise RuntimeError(
                    f"Unsupported token file format: {suffix}. Expected .json or .pickle"
                )
        except Exception as err:
            raise RuntimeError(
                f"Could not load token file '{self.token_path}'. "
                "Supported formats: .json, .pickle"
            ) from err
        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise RuntimeError(
                        "Invalid or missing credentials. Please run auth_setup.py."
                    )
            except RefreshError as err:
                raise RuntimeError(
                    f"Error refreshing token: {err}. Please run auth_setup.py again to re-authenticate."
                ) from err
        return build("drive", "v3", credentials=creds)
    def _load_credentials_from_json(self):
        return Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
    def _load_credentials_from_pickle(self):
        with self.token_path.open("rb") as f:
            return pickle.load(f)
    def search_files(self, query: str) -> dict[str, Any]:
        """Search files in Google Drive."""
        try:
            results = (
                self.service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                )
                .execute()
            )
            return self._format_search_response(results)
        except Exception as e:
            raise RuntimeError(f"Error searching files: {e}") from e
    def download_file(self, file_id: str) -> dict[str, Any]:
        """Download a file from Google Drive."""
        try:
            metadata = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, webViewLink",
                )
                .execute()
            )
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return {
                "metadata": {
                    "id": metadata["id"],
                    "name": metadata["name"],
                    "mimeType": metadata["mimeType"],
                    "webViewLink": metadata.get("webViewLink"),
                },
                "content": fh.getvalue(),
            }
        except Exception as e:
            raise RuntimeError(f"Error downloading file: {e}") from e
    def _format_search_response(self, response: dict[str, Any]) -> dict[str, Any]:
        items = response.get("files", [])
        formatted_files = []
        for item in items:
            formatted_file = {
                "id": item["id"],
                "name": item["name"],
                "mimeType": item["mimeType"],
                "webViewLink": item.get("webViewLink"),
            }
            formatted_files.append(formatted_file)
        return {"files": formatted_files}
def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Google Drive MCP Server")
    parser.add_argument("--token", default="tokens.json", help="Path to token file")
    args = parser.parse_args()
    client = GoogleDriveClient(token_path=args.token)
    mcp = FastMCP()
    @mcp.command("search")
    def search(query: str):
        return client.search_files(query)
    @mcp.command("download")
    def download(file_id: str):
        return client.download_file(file_id)
    mcp.run()
if __name__ == "__main__":
    main()
