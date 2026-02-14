"""YouTube upload provider using YouTube Data API v3.

Handles OAuth2 authentication and resumable video uploads.
Uses the project's secrets system for credential storage.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# OAuth2 scopes needed for upload
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Where to store OAuth tokens (in project artifacts dir)
DEFAULT_TOKEN_DIR = Path.home() / ".claude-studio" / "youtube"


@dataclass
class UploadResult:
    """Result from a YouTube upload."""
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None


class YouTubeUploader:
    """Upload videos to YouTube using the Data API v3.
    
    Authentication flow:
    1. First run: opens browser for OAuth2 consent, stores refresh token in keychain
    2. Subsequent runs: uses stored refresh token (no browser needed)
    
    Secrets stored in OS keychain (no files on disk):
        cs secrets set YOUTUBE_CLIENT_ID <client_id>
        cs secrets set YOUTUBE_CLIENT_SECRET <client_secret>
    
    Or legacy file-based approach:
        cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/client_secrets.json
    """
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 client_secrets_path: Optional[str] = None, token_dir: Optional[Path] = None):
        self.token_dir = token_dir or DEFAULT_TOKEN_DIR
        self.token_dir.mkdir(parents=True, exist_ok=True)
        self.token_path = self.token_dir / "token.json"
        self.client_id = client_id
        self.client_secret = client_secret
        self.client_secrets_path = client_secrets_path
        self._service = None

    def _build_client_config(self) -> Dict[str, Any]:
        """Build OAuth2 client config from individual secrets."""
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

    def _get_credentials(self):
        """Get or refresh OAuth2 credentials."""
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Prefer individual secrets over file path
                if self.client_id and self.client_secret:
                    client_config = self._build_client_config()
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                elif self.client_secrets_path and Path(self.client_secrets_path).exists():
                    flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, SCOPES)
                else:
                    raise FileNotFoundError(
                        "YouTube OAuth2 credentials not configured.\n"
                        "Set via keychain (recommended):\n"
                        "  cs secrets set YOUTUBE_CLIENT_ID <your_client_id>\n"
                        "  cs secrets set YOUTUBE_CLIENT_SECRET <your_client_secret>\n"
                        "Or via file:\n"
                        "  cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/client_secrets.json"
                    )
                flow = flow if isinstance(flow, InstalledAppFlow) else flow
                creds = flow.run_local_server(port=0)

            # Save refresh token for future runs
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
            os.chmod(str(self.token_path), 0o600)

        return creds

    def _get_service(self):
        """Get authenticated YouTube API service."""
        if self._service is None:
            from googleapiclient.discovery import build
            creds = self._get_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def upload(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        category_id: str = "27",  # Education
        privacy: str = "unlisted",  # unlisted|public|private
        notify_subscribers: bool = False,
    ) -> UploadResult:
        """Upload a video to YouTube.
        
        Args:
            video_path: Path to the video file
            title: Video title (max 100 chars)
            description: Video description (max 5000 chars)
            tags: List of tags
            category_id: YouTube category (27=Education, 28=Science&Tech)
            privacy: Privacy status (unlisted, public, private)
            notify_subscribers: Whether to notify channel subscribers
            
        Returns:
            UploadResult with video_id and URL on success
        """
        from googleapiclient.http import MediaFileUpload

        video_file = Path(video_path)
        if not video_file.exists():
            return UploadResult(success=False, error=f"Video file not found: {video_path}")

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
                "notifySubscribers": notify_subscribers,
            },
        }

        media = MediaFileUpload(
            str(video_file),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        try:
            service = self._get_service()
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response["id"]
            return UploadResult(
                success=True,
                video_id=video_id,
                video_url=f"https://youtu.be/{video_id}",
            )

        except Exception as e:
            return UploadResult(success=False, error=str(e))

    def check_auth(self) -> bool:
        """Check if YouTube authentication is set up."""
        try:
            self._get_service()
            return True
        except Exception:
            return False
