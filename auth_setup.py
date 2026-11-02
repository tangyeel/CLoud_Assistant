"""
auth_setup.py — One-time setup utility for Google OAuth 2.0.
Run this script on your local computer to authenticate and generate credentials/token.json.
Also generates Base64 encoded strings for easy cloud deployment on Render, Zeabur, or Hugging Face.
"""
import os

# Allow OAuthLib to accept Google's aliased / remapped scopes
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_IGNORE_SCOPE_CHANGE"] = "1"

import argparse
import base64
from pathlib import Path
from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_THAPAR_TOKEN_PATH
from google_services.auth import get_google_credentials

def main():
    parser = argparse.ArgumentParser(description="Google Workspace OAuth 2.0 Setup Utility")
    parser.add_argument(
        "--thapar",
        action="store_true",
        help="Authenticate secondary Thapar University Google Account",
    )
    args = parser.parse_args()

    account = "thapar" if args.thapar else "default"
    target_token_path = GOOGLE_THAPAR_TOKEN_PATH if args.thapar else GOOGLE_TOKEN_PATH
    label = "Thapar University Google Account" if args.thapar else "Primary Google Account"

    print("=" * 65)
    print(f"  Google Workspace OAuth 2.0 Setup: {label}")
    print("=" * 65)

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        print(f"\n❌ Missing client credentials at: {GOOGLE_CREDENTIALS_PATH}")
        print("\nPlease follow these quick steps:")
        print("1. Visit https://console.cloud.google.com/")
        print("2. Ensure Gmail, Google Calendar, Google Tasks, and Google Classroom APIs are enabled.")
        print("3. Under APIs & Services -> Credentials -> Create Credentials -> OAuth Client ID:")
        print("   Select Application Type: 'Desktop app'.")
        print("4. Download the client JSON file and save it as:")
        print(f"   {os.path.abspath(GOOGLE_CREDENTIALS_PATH)}")
        return

    print(f"\nFound credentials at: {GOOGLE_CREDENTIALS_PATH}")
    print(f"Opening your browser for one-time approval for {label}...")
    print("⚠️ IMPORTANT: In the browser, make sure to log in with your:")
    if args.thapar:
        print("   👉 Thapar University email (@thapar.edu)")
    else:
        print("   👉 Primary Personal email")
    print("(If you see 'Google hasn't verified this app' -> Click 'Advanced' -> 'Go to app')\n")

    try:
        creds = get_google_credentials(account=account)
        print("\n" + "=" * 65)
        print("✅ OAuth Authentication Succeeded!")
        print(f"Token file created at: {os.path.abspath(target_token_path)}")
        print("=" * 65)

        # Output Base64 strings for Cloud deployment
        if os.path.exists(target_token_path):
            with open(target_token_path, "rb") as tf:
                token_b64 = base64.b64encode(tf.read()).decode("utf-8")

            var_name = "GOOGLE_THAPAR_TOKEN_B64" if args.thapar else "GOOGLE_TOKEN_B64"
            print("\n📋 Cloud Deployment Environment Variable:")
            print(f"{var_name}={token_b64}\n")
            print("=" * 65)
            print(f"Authentication for {label} complete! Token saved and ready.")

    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")

if __name__ == "__main__":
    main()
