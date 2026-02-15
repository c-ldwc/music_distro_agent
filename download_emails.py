"""
Script to run email helpers and download new emails from Gmail.
This script authenticates with Gmail and fetches unread emails,
saving them to the configured email directory.
"""

from src.config import load_config
from src.email_utils import gmail, gmail_auth_context


def main():
    """Main function to download emails"""
    print("Starting email download process...")

    # Get configuration
    config = load_config()

    # Create gmail auth context
    gmail_context = gmail_auth_context(
        token=str(config.gmail.token_path),
        secret=str(config.gmail.secret_path),
        scopes=[config.gmail.scopes],
    )
    print(gmail_context)
    # Initialize gmail client
    gmail_client = gmail(
        email_dir=config.email.path,
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
