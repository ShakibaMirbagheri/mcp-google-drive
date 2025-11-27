#!/usr/bin/env python3
"""
MCP server for Google Drive integration.
This server exposes methods to interact with Google Drive files and folders.
"""

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

# Load environment variables
load_dotenv()

print("Starting Google Drive MCP server!")


class GoogleDriveClient:
    """Client for interacting with the Google Drive API."""

    def __init__(self, token_path: Optional[str] = None) -> None:
        """
        Initialize the Google Drive client.

        Args:
            token_path: Path to the token file. If None, defaults to 'tokens.json'.
        """
        self.scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        self.token_path = Path(token_path) if token_path else Path("tokens.json")
        self.service = self._get_service()

    def _get_credentials(self) -> Credentials:
        """Load credentials from token file."""
        if not self.token_path.exists():
            raise FileNotFoundError(
                f"Token file not found at {self.token_path}. "
                "Run auth_setup.py first."
            )

        suffix = self.token_path.suffix.lower()

        loader_sequence = []
        if suffix == ".json":
            loader_sequence = [
                self._load_credentials_from_json,
                self._load_credentials_from_pickle,
            ]
        elif suffix in {".pickle", ".pkl"}:
            loader_sequence = [
                self._load_credentials_from_pickle,
                self._load_credentials_from_json,
            ]
        else:
            loader_sequence = [
                self._load_credentials_from_json,
                self._load_credentials_from_pickle,
            ]

        creds: Optional[Credentials] = None

        for loader in loader_sequence:
            try:
                creds = loader()
                break
            except Exception:
                continue

        if creds is None:
            raise RuntimeError(
                f"Could not load token from {self.token_path}. "
                "Supported formats: .json, .pickle"
            )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    raise RuntimeError(
                        f"Error refreshing token: {exc}. "
                        "Please re-run auth_setup.py."
                    ) from exc
            else:
                raise RuntimeError(
                    "Invalid credentials. Please run auth_setup.py."
                )

        return creds

    def _load_credentials_from_json(self) -> Credentials:
        """Load credentials stored as JSON."""
        try:
            return Credentials.from_authorized_user_file(
                str(self.token_path),
                scopes=self.scopes,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Error loading token JSON file: {exc}"
            ) from exc

    def _load_credentials_from_pickle(self) -> Credentials:
        """Load credentials stored as pickle."""
        try:
            with self.token_path.open("rb") as token:
                loaded = pickle.load(token)

            if not isinstance(loaded, Credentials):
                raise RuntimeError("Pickle did not contain valid credentials")

            return loaded

        except Exception as exc:
            raise RuntimeError(
                f"Error loading token pickle file: {exc}"
            ) from exc

    def _get_service(self):
        """Initialize Google Drive API service."""
        creds = self._get_credentials()
        return build("drive", "v3", credentials=creds)

    def search_files(
        self, query: str, page_size: int = 10, page_token: Optional[str] = None
    ) -> dict[str, Any]:
        """Search for files in Google Drive."""
        try:
            results = (
                self.service.files()
                .list(
                    q=f"name contains '{query}'",
                    pageSize=page_size,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                )
                .execute()
            )
            return self._format_search_response(results)
        except Exception as exc:
            return {"error": str(exc)}

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Retrieve file metadata and content."""
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
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            return {
                "metadata": {
                    "id": metadata["id"],
                    "name": metadata["name"],
                    "mime_type": metadata["mimeType"],
                    "web_view_link": metadata["webViewLink"],
                },
                "content": buffer.getvalue().decode("utf-8", errors="replace"),
            }

        except Exception as exc:
            return {"error": str(exc)}

    def _format_search_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Format Google Drive search output."""
        files = [
            {
                "id": item["id"],
                "name": item["name"],
                "mime_type": item["mimeType"],
                "web_view_link": item["webViewLink"],
            }
            for item in response.get("files", [])
        ]

        return {
            "files": files,
            "next_page_token": response.get("nextPageToken"),
        }


# Initialize MCP server
mcp = FastMCP(name="Google Drive MCP Server", host="0.0.0.0", port=8000)


@mcp.tool()
def search_files(query: str, page_size: int = 10) -> dict[str, Any]:
    """Search Google Drive for files."""
    return drive_client.search_files(query=query, page_size=page_size)


@mcp.tool()
def get_file(file_id: str) -> dict[str, Any]:
    """Retrieve file data from Google Drive."""
    return drive_client.get_file(file_id=file_id)


def main() -> None:
    """Run the MCP server."""
    parser = argparse.ArgumentParser(description="Google Drive MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--token", type=str, help="Path to token file")
    args = parser.parse_args()

    global drive_client
    drive_client = GoogleDriveClient(token_path=args.token)

    if args.http:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
