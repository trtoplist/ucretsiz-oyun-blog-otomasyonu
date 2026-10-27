"""Create a Blogger OAuth refresh token locally; never writes credentials to disk."""
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = "https://www.googleapis.com/auth/blogger"
client_id = os.environ.get("GOOGLE_CLIENT_ID")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
if not client_id:
    sys.exit("Set GOOGLE_CLIENT_ID (and GOOGLE_CLIENT_SECRET if provided) in your local terminal first.")

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}
flow = InstalledAppFlow.from_client_config(client_config, scopes=[SCOPE])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
if not creds.refresh_token:
    sys.exit("Google did not return a refresh token. Revoke the app grant and run again with consent.")
print("\nCopy this value directly into the GitHub repository secret GOOGLE_REFRESH_TOKEN. Do not commit or share it:\n")
print(creds.refresh_token)
