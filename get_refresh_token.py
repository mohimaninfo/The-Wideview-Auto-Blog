from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ["https://www.googleapis.com/auth/blogger"]

flow = InstalledAppFlow.from_client_secrets_file(
    "config/client_secrets.json",
    SCOPES
)

# Generate the auth URL manually
auth_url, _ = flow.authorization_url(
    access_type="offline",
    prompt="consent"
)

print("\nOpen this URL in your browser:\n")
print(auth_url)
print()

code = input("Paste the authorization code here: ")

flow.fetch_token(code=code)
creds = flow.credentials

print("\n=== COPY THIS INTO YOUR GITHUB SECRET ===\n")
print(json.dumps({
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret
}, indent=2))
