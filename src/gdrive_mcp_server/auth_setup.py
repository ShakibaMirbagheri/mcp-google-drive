"""Authentication setup for Google Drive."""
import argparse
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
def setup_auth(credentials_path: str, token_path: str = "tokens.json") -> None:
    """Set up Google Drive authentication and save the refresh token.
    Args:
        credentials_path: Path to the credentials.json file
        token_path: Path to save the token.json file
    """
    creds = None
    token_path = Path(token_path)
    # Check if token exists and is valid
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path)
    # If no valid creds, go through OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes=[
                "https://www.googleapis.com/auth/drive.readonly"
            ])
            creds = flow.run_local_server(port=0)
        # Save the new token
        token_path.write_text(creds.to_json())
def main() -> None:
    parser = argparse.ArgumentParser(description="Google Drive Authentication Setup")
    parser.add_argument("--credentials", required=True, help="Path to credentials.json file")
    parser.add_argument(
        "--token",
        default="tokens.json",
        help="Path to save the token (default: tokens.json)",
    )
    args = parser.parse_args()
    setup_auth(args.credentials, args.token)
if __name__ == "__main__":
    main()







