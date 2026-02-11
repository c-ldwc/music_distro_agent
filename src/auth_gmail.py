from email_utils import gmail, gmail_auth_context
from .classes import env_settings

def main():
    env_settings = env_settings()

    gmail_context = gmail_auth_context(
        secret=env_settings.GMAIL_SECRET_PATH,
        token="token.json",
        scopes=env_settings.GMAIL_SCOPES,
    )
    gmail_obj = gmail(email_dir=env_settings.email_path, gmail_context=gmail_context)
    gmail_obj.auth()
    gmail_obj.get_attachment_flow(env_settings.GMAIL_MAIN_ACCOUNT)


if __name__ == "__main__":
    main()
