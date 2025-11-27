#!/usr/bin/env python3
"""
MCP server for Google Drive integration.
This server exposes methods to interact with Google Drive files and folders.
"""

import argparse
import io
import pickle
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from mcp.server.fastmcp import FastMCP

load_dotenv()


class GoogleDriveClient:
    """Client for interacting with the Google Drive API."""

    def __init__(self, token_path: Optional[str] = None):
        """Initialize the Google Drive client.

        Args:
            token_path:
                Path to the token file. If None, defaults to 'tokens.json'
                in the current directory.
        """
        self.SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
        self.token_path = Path(token_path) if token_path else Path("tokens.json")
        self.service = self._get_service()

    def _get_credentials(self) -> Credentials:
        """Get credentials from the saved token file."""
        if not self.token_path.exists():
            raise FileNotFoundError(
                f"Token file not found at {self.token_path}. "
                "Please run auth_setup.py first to set up authentication."
            )

        suffix = self.token_path.suffix.lower()

        # Load token by expected format, fall back gracefully
        try:
            if suffix == ".json":
                creds = self._load_credentials_from_json()
            elif suffix in {".pickle", ".pkl"}:
                creds = self._load_credentials_from_pickle()
            else:
                # Try json then pickle
                try:
                    creds = self._load_credentials_from_json()
                except Exception:
                    creds = self._load_credentials_from_pickle()
        except Exception as err:
            raise RuntimeError(
                f"Could not load token file '{self.token_path}'. "
                "Supported formats: .json, .pickle"
            ) from err

        # Validate / refresh credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as err:
                    raise RuntimeError(
                        f"Error refreshing token: {err}. "
                        "Please run auth_setup.py again to re-authenticate."
                    ) from err
            else:
                raise RuntimeError(
                    "Invalid or missing credentials. "
                    "Please run auth_setup.py to set up authentication."
                )

        return creds

    def _load_credentials_from_json(self) -> Credentials:
        """Load credentials stored as JSON."""
        try:
            return Credentials.from_authorized_user_file(
                str(self.token_path), scopes=self.SCOPES
            )
        except Exception as err:
            raise RuntimeError(f"Error loading token JSON file: {err}") from err

    def _load_credentials_from_pickle(self) -> Credentials:
        """Load credentials stored as a pickle."""
        try:
            with open(self.token_path, "rb") as token:
                return pickle.load(token)
        except (pickle.UnpicklingError, EOFError) as err:
            raise RuntimeError(
                f"Error loading token pickle file: {err}"
            ) from err

    def _get_service(self):
        """Get the Google Drive service instance."""
        try:
            creds = self._get_credentials()
            return build("drive", "v3", credentials=creds)
        except Exception as err:
            raise RuntimeError(
                f"Error initializing Google Drive service: {err}"
            ) from err

    def search_files(
        self,
        query: str,
        page_size: int = 10,
        page_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search for files in Google Drive."""
        try:
            results = (
                self.service.files()
                .list(
                    q=f"name contains '{query}'",
                    pageSize=page_size,
                    pageToken=page_token,
                    fields=(
                        "nextPageToken, files(id, name, mimeType, webViewLink)"
                    ),
                )
                .execute()
            )
            return self._format_search_response(results)
        except Exception as err:
            return {"error": str(err)}

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Get file content and metadata."""
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
                    "mime_type": metadata["mimeType"],
                    "web_view_link": metadata["webViewLink"],
                },
                "content": fh.getvalue().decode("utf-8"),
            }
        except Exception as err:
            return {"error": str(err)}

    def _format_search_response(self, response: dict) -> dict:
        """Format the Google Drive search response."""
        items = response.get("files", [])
        formatted_files = [
            {
                "id": item["id"],
                "name": item["name"],
                "mime_type": item["mimeType"],
                "web_view_link": item["webViewLink"],
            }
            for item in items
        ]

        return {
            "files": formatted_files,
            "next_page_token": response.get("nextPageToken"),
        }


# MCP server setup
mcp = FastMCP(
    name="Google Drive MCP Server",
    host="0.0.0.0",
    port=8000,
)


@mcp.tool()
def search_files(query: str, page_size: int = 10) -> dict[str, Any]:
    return drive_client.search_files(query=query, page_size=page_size)


@mcp.tool()
def get_file(file_id: str) -> dict[str, Any]:
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
