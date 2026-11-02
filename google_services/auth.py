"""
google_services/auth.py — Google OAuth 2.0 token management.
Handles first-time authentication, silent background refresh, and token persistence.
"""
import os

# Allow OAuthLib to accept Google's aliased / remapped scopes
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_IGNORE_SCOPE_CHANGE"] = "1"

import base64
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_THAPAR_TOKEN_PATH, GOOGLE_SCOPES
from utils.logger import logger


def _get_token_path(account: str = "default") -> str:
    """Return token filepath based on account identifier."""
    if account.lower() in ("thapar", "college", "university"):
        return GOOGLE_THAPAR_TOKEN_PATH
    return GOOGLE_TOKEN_PATH


def has_thapar_account() -> bool:
    """Check if a Thapar token file is present."""
    return os.path.exists(GOOGLE_THAPAR_TOKEN_PATH)


def get_google_credentials(account: str = "default") -> Credentials:
    """
    Get valid Google OAuth credentials for the specified account (default or thapar).
    """
    creds = None
    token_path = _get_token_path(account)

    # Step 1: Check existing token file
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, GOOGLE_SCOPES)
            logger.debug(f"Loaded existing token for '{account}' from {token_path}")
        except Exception as e:
            logger.warning(f"Failed to read {token_path}: {e}")
            creds = None

    # Step 2: Check validity and refresh if expired
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info(f"OAuth token for '{account}' has expired. Refreshing...")
            creds.refresh(Request())
            logger.info(f"✅ Token for '{account}' successfully refreshed.")
            _save_token(creds, token_path)
            return creds
        except Exception as e:
            logger.error(f"Silent refresh for '{account}' failed: {e}. Re-authenticating...")
            creds = None

    # Step 3: First-time authentication flow
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"❌ OAuth credentials file not found at '{GOOGLE_CREDENTIALS_PATH}'."
        )

    logger.info(f"Starting browser OAuth 2.0 flow for account '{account}'...")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            GOOGLE_CREDENTIALS_PATH,
            GOOGLE_SCOPES
        )
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
        logger.info(f"✅ OAuth completed for '{account}'!")
        _save_token(creds, token_path)
        return creds
    except Exception as e:
        logger.error(f"OAuth authorization flow failed for '{account}': {e}")
        raise


def _save_token(creds: Credentials, token_path: str = GOOGLE_TOKEN_PATH) -> None:
    """Persist authorized user credentials to token file."""
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    logger.debug(f"Saved token to {token_path}")


def build_service(api_name: str, api_version: str, account: str = "default"):
    """
    Construct a Google API service client instance for specified account.
    """
    creds = get_google_credentials(account=account)
    service = build(api_name, api_version, credentials=creds, cache_discovery=False)
    logger.debug(f"Initialized Google {api_name} {api_version} client for '{account}'.")
    return service
