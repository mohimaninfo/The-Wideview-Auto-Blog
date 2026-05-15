import json
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/blogger"]


def get_blogger_credentials():
    """
    Bulletproof OAuth loader for GitHub Actions + local runs.
    Never fails due to missing token fields.
    """

    raw = os.environ.get("BLOGGER_OAUTH_CREDENTIALS_JSON")

    if not raw:
        raise ValueError("Missing BLOGGER_OAUTH_CREDENTIALS_JSON")

    data = json.loads(raw)

    # HARD validation (fail early, not inside Google SDK)
    for f in ["refresh_token", "client_id", "client_secret"]:
        if not data.get(f):
            raise ValueError(f"Missing OAuth field: {f}")

    creds = Credentials(
        token=None,  # always start clean
        refresh_token=data["refresh_token"],
        token_uri=TOKEN_URI,
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=SCOPES,
    )

    # FORCE VALID TOKEN
    try:
        creds.refresh(Request())
    except Exception as e:
        raise RuntimeError(f"OAuth refresh failed: {str(e)}")

    return creds
