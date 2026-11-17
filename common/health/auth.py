"""OAuth for the Google Health API.

Google Health data is personal, so unlike every other source here it needs a
signed-in user. One-time setup:

1. In Google Cloud console, create a project, enable the **Google Health API**,
   configure the OAuth consent screen (add yourself as a test user), and create
   an OAuth client of type **Desktop app**.
2. Download its JSON to ``~/.config/data_scrape/google_client_secret.json``
   (or point ``$GOOGLE_HEALTH_CLIENT_SECRETS`` at it).
3. ``python -m common.health auth`` -- opens a browser, saves a refresh token
   next to the client secret. Later runs refresh it silently.

Both files live under :data:`common.paths.CONFIG_ROOT`, outside ``build/`` and
outside the repo, so ``rm -rf build/`` doesn't log you out and nothing secret
can be committed.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from ..paths import CONFIG_ROOT

log = logging.getLogger(__name__)

SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth."

#: Read-only access to the commonly useful categories. Add e.g. "ecg" or
#: "reproductive_health" here (or pass ``scopes=``) if you need them.
DEFAULT_SCOPES = tuple(
    SCOPE_PREFIX + s + ".readonly"
    for s in (
        "activity_and_fitness",
        "health_metrics_and_measurements",
        "sleep",
        "nutrition",
    )
)

INSTALL_HINT = "Google Health needs the OAuth libraries: pip install -e '.[health]'"


class AuthError(RuntimeError):
    """No usable credentials -- the message says what to do about it."""


class GoogleHealthAuth:
    """Loads, refreshes and stores the user's OAuth token."""

    def __init__(
        self,
        client_secrets: Path | str | None = None,
        token_path: Path | str | None = None,
        scopes: Sequence[str] = DEFAULT_SCOPES,
    ) -> None:
        self.client_secrets = Path(
            client_secrets
            or os.environ.get("GOOGLE_HEALTH_CLIENT_SECRETS", "")
            or CONFIG_ROOT / "google_client_secret.json"
        )
        self.token_path = Path(token_path or CONFIG_ROOT / "google_health_token.json")
        self.scopes = list(scopes)
        self._creds = None

    def login(self, port: int = 0):
        """Run the browser consent flow and save the resulting token."""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as e:  # pragma: no cover
            raise AuthError(INSTALL_HINT) from e
        if not self.client_secrets.exists():
            raise AuthError(
                f"no OAuth client at {self.client_secrets}. Create a Desktop-app "
                "OAuth client for the Google Health API in Google Cloud console "
                "and save its JSON there (see common/health/auth.py)."
            )
        client = json.loads(self.client_secrets.read_text()).get("installed", {})
        if not client.get("client_secret"):
            raise AuthError(
                f"{self.client_secrets} has no client_secret. Google requires it even "
                "for Desktop apps: copy it from the OAuth client's page in Google "
                "Cloud console (or re-download the client JSON over this file)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets), self.scopes)
        self._creds = flow.run_local_server(port=port, access_type="offline", prompt="consent")
        self._save()
        log.info("saved Google Health token to %s", self.token_path)
        return self._creds

    def token(self) -> str:
        """A valid access token, refreshed if needed."""
        creds = self._load()
        if not creds.valid:
            try:
                from google.auth.transport.requests import Request
            except ImportError as e:  # pragma: no cover
                raise AuthError(INSTALL_HINT) from e
            if not creds.refresh_token:
                raise AuthError("token expired and has no refresh token; run: python -m common.health auth")
            creds.refresh(Request())
            self._save()
        return creds.token

    def _load(self):
        if self._creds is not None:
            return self._creds
        try:
            from google.oauth2.credentials import Credentials
        except ImportError as e:  # pragma: no cover
            raise AuthError(INSTALL_HINT) from e
        if not self.token_path.exists():
            raise AuthError(
                f"not signed in to Google Health (no {self.token_path}); "
                "run: python -m common.health auth"
            )
        self._creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
        return self._creds

    def _save(self) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        # Create with owner-only permissions *before* writing the secret.
        fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(self._creds.to_json())
