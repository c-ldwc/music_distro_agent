"""
Script to run email helpers and download new emails from Gmail.
This script authenticates with Gmail and fetches unread emails,
saving them to the configured email directory.
"""

from dotenv import load_dotenv

from src.email_utils import gmail, gmail_auth_context
from src.email_utils import settings as email_settings

# Load environment variables
load_dotenv()

def main():
    """Main function to download emails"""
    print("Starting email download process...")

    # Get settings from environment
    settings = email_settings()

    # Create gmail auth context
    gmail_context = gmail_auth_context(
        token="token.json",
        secret=settings.GMAIL_SECRET_PATH,
        scopes=settings.GMAIL_SCOPES,
    )
    print(gmail_context)
    # Initialize gmail client
    gmail_client = gmail(
        email_dir=settings.email_path,
        gmail_context=gmail_context,
    )

    # Authenticate with Gmail
    print("Authenticating with Gmail...")
    gmail_client.auth()
    print("✓ Authentication successful")

    # Fetch new emails
    print("Fetching new emails...")
    gmail_client.fetch_new_emails()
    print("✓ Email download complete")


if __name__ == "__main__":
    main()
