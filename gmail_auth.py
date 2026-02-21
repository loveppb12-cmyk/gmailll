import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Gmail API scopes - we only need read-only access
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate_gmail():
    """Run OAuth 2.0 flow to get Gmail token"""
    creds = None
    token_file = 'token.json'
    
    # Token file stores the user's access and refresh tokens
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # You need to download credentials.json from Google Cloud Console
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        
        print(f"✅ Authentication successful! Token saved to {token_file}")
        print(f"Access Token: {creds.token}")
        print(f"Refresh Token: {creds.refresh_token}")
        print(f"Token Expiry: {creds.expiry}")
    else:
        print(f"✅ Valid token already exists at {token_file}")
    
    return creds

if __name__ == '__main__':
    print("🔐 Gmail Authentication Setup")
    print("=" * 40)
    print("This script will help you generate OAuth tokens for Gmail API")
    print("\nBefore running, make sure you have:")
    print("1. Created a project in Google Cloud Console")
    print("2. Enabled Gmail API")
    print("3. Downloaded credentials.json")
    print("=" * 40)
    
    authenticate_gmail()
