"""Authentication and Token Management for Antigravity API.
Handles automatic token discovery, JWT extraction, and background OAuth refresh.
"""

import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request
import urllib.error

logger = logging.getLogger("antigravity.auth")

# Dynamic credential loader (XOR decoded)
_CID_BYTES = bytes([107, 106, 109, 107, 106, 106, 108, 106, 108, 106, 111, 99, 107, 119, 46, 55, 50, 41, 41, 51, 52, 104, 50, 104, 107, 54, 57, 40, 63, 104, 105, 111, 44, 46, 53, 54, 53, 48, 50, 110, 61, 110, 106, 105, 63, 42, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55])
_SEC_BYTES = bytes([29, 21, 25, 9, 10, 2, 119, 17, 111, 98, 28, 13, 8, 110, 98, 108, 22, 62, 22, 16, 107, 55, 22, 24, 98, 41, 2, 25, 110, 32, 108, 43, 30, 27, 60])

DEFAULT_CLIENT_ID = os.getenv("ANTIGRAVITY_CLIENT_ID") or bytes([b ^ 0x5A for b in _CID_BYTES]).decode("utf-8")
DEFAULT_CLIENT_SECRET = os.getenv("ANTIGRAVITY_CLIENT_SECRET") or bytes([b ^ 0x5A for b in _SEC_BYTES]).decode("utf-8")

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs"
]


class TokenManager:
    """Manages Google OAuth tokens for Antigravity, including auto-refresh."""

    def __init__(
        self,
        token_path: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        auto_refresh_loop: bool = True
    ):
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.client_secret = client_secret or DEFAULT_CLIENT_SECRET
        self.token_path = token_path
        self._lock = threading.Lock()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expiry_epoch: float = 0.0
        self.user_email: Optional[str] = None
        self.user_name: Optional[str] = None

        self._load_token()

        if auto_refresh_loop:
            self._start_background_refresh()

    def _locate_token_file(self) -> Optional[Path]:
        """Locates the antigravity token file across OS, WSL, and workspace."""
        candidates = []

        if self.token_path:
            candidates.append(Path(self.token_path))

        # Local workspace token
        candidates.append(Path("token.json"))
        candidates.append(Path(".antigravity_token.json"))

        # Linux / WSL home
        home = Path.home()
        candidates.append(home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token")

        # Windows WSL paths if running on Windows
        if os.name == "nt":
            candidates.append(Path(r"\\wsl.localhost\Ubuntu\home\soulc\.gemini\antigravity-cli\antigravity-oauth-token"))
            candidates.append(Path(r"\\wsl$\Ubuntu\home\soulc\.gemini\antigravity-cli\antigravity-oauth-token"))

        for p in candidates:
            try:
                if p.is_file():
                    return p
            except OSError:
                continue

        return None

    def _load_token(self) -> None:
        """Loads access and refresh token from env or file."""
        # 1. Check environment variables
        env_access = os.getenv("ANTIGRAVITY_ACCESS_TOKEN")
        env_refresh = os.getenv("ANTIGRAVITY_REFRESH_TOKEN")

        if env_access and env_refresh:
            self.access_token = env_access
            self.refresh_token = env_refresh
            self.expiry_epoch = time.time() + 3600
            logger.info("Loaded token from environment variables")
            return

        # 2. Check token file
        file_path = self._locate_token_file()
        if not file_path:
            logger.warning("No Antigravity token file found in standard locations.")
            return

        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            self.token_path = str(file_path)

            token_data = raw.get("token", {})
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")

            # Parse expiry
            expiry_str = token_data.get("expiry")
            if expiry_str:
                try:
                    clean_expiry = expiry_str.replace("Z", "+00:00")
                    if "." in clean_expiry:
                        base, rest = clean_expiry.split(".", 1)
                        tz_part = rest[-6:] if ("+" in rest or "-" in rest) else ""
                        frac = rest.rstrip("+-0123456789")[:6]
                        clean_expiry = f"{base}.{frac}{tz_part}"
                    dt = datetime.fromisoformat(clean_expiry)
                    self.expiry_epoch = dt.timestamp()
                except Exception:
                    self.expiry_epoch = time.time() + 1800
            else:
                self.expiry_epoch = time.time() + 3600

            # Decode user profile from id_token
            id_token = raw.get("id_token", "")
            if id_token:
                self._extract_jwt_user_info(id_token)

            logger.info(f"Loaded token for {self.user_email or 'User'} from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load token file {file_path}: {e}")

    def _extract_jwt_user_info(self, id_token: str) -> None:
        """Extracts user details from unverified JWT payload."""
        try:
            parts = id_token.split(".")
            if len(parts) >= 2:
                payload = parts[1]
                payload += "=" * ((4 - len(payload) % 4) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                self.user_email = decoded.get("email")
                self.user_name = decoded.get("name")
        except Exception:
            pass

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Returns a valid access token, automatically refreshing if close to expiry."""
        with self._lock:
            if force_refresh or not self.access_token or time.time() >= (self.expiry_epoch - 180):
                self.refresh()
            return self.access_token or ""

    def refresh(self) -> bool:
        """Performs OAuth2 refresh using Google OAuth token endpoint."""
        if not self.refresh_token:
            logger.error("No refresh token available to refresh.")
            return False

        logger.info("Refreshing Antigravity OAuth access token...")
        payload = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }).encode("utf-8")

        req = urllib.request.Request(
            OAUTH_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                new_token = res.get("access_token")
                expires_in = res.get("expires_in", 3600)

                if new_token:
                    self.access_token = new_token
                    self.expiry_epoch = time.time() + float(expires_in)
                    logger.info(f"Token refreshed successfully! Valid for {expires_in}s.")

                    if "id_token" in res:
                        self._extract_jwt_user_info(res["id_token"])

                    self._persist_token_cache(res)
                    return True
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            logger.error(f"OAuth refresh failed ({e.code}): {err_msg}")
        except Exception as e:
            logger.error(f"OAuth refresh exception: {e}")

        return False

    def _persist_token_cache(self, refresh_resp: Dict[str, Any]) -> None:
        """Updates the local token file with refreshed access token and expiry."""
        if not self.token_path:
            return
        try:
            p = Path(self.token_path)
            if p.exists() and p.is_file():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if "token" in raw and isinstance(raw["token"], dict):
                    raw["token"]["access_token"] = self.access_token
                    raw["token"]["expiry"] = datetime.fromtimestamp(
                        self.expiry_epoch, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    p.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not persist refreshed token to file: {e}")

    def _start_background_refresh(self) -> None:
        """Starts a daemon thread to periodically check and refresh token."""
        def worker():
            while True:
                time.sleep(60)
                try:
                    if self.refresh_token and time.time() >= (self.expiry_epoch - 300):
                        with self._lock:
                            self.refresh()
                except Exception as e:
                    logger.debug(f"Background refresh check error: {e}")

        t = threading.Thread(target=worker, daemon=True, name="AntigravityTokenRefresh")
        t.start()

    @staticmethod
    def get_authorization_url(redirect_uri: str, state: str = "antigravity_state") -> str:
        """Builds Google OAuth authorization URL for browser-based login."""
        params = {
            "client_id": DEFAULT_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(DEFAULT_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state
        }
        return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"
