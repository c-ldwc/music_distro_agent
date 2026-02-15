import base64
import email
from datetime import datetime
from email import policy
from pathlib import Path
from re import match, sub
from typing import Annotated

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import AfterValidator, BaseModel

from .classes import boom_email


def json_path_validator(p: str) -> str:
    if p[-5:] != ".json":
        raise ValueError("This path is not a json")
    return p


def email_validator(e: str) -> str:
    # Bog standard email regex
    if match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", e) is None:
        raise ValueError(f"{e} is not a valid email")
    return e

    # def path_validator(p: str | Path) -> Path:
    #    if type(p) is str:
    #        p: Path = Path(p)
    #    return p


def process_env_list(list_str: str) -> list[str]:
    print(list_str)
    # Format a string that represents a list into a list of strings
    # i.e. "[a,b,something_else]" -> ["a", "b", "something_else"]
    return [sub(r"[\s\[\]]", "", i) for i in list_str.split(",")]


class gmail_auth_context(BaseModel):
    token: Annotated[str, AfterValidator(json_path_validator)]
    secret: Annotated[str, AfterValidator(json_path_validator)]
    scopes: list[str]


class gmail(BaseModel):
    email_dir: Path
    gmail_context: gmail_auth_context
    _creds: Credentials | None

    def model_post_init(self, __context) -> None:
        # set up the email dir
        self.email_dir.mkdir(exist_ok=True)

    def auth(self) -> None:
        print(f"Authorising gmail with scope {self.gmail_context.scopes} of type {type(self.gmail_context.scopes)}")
        self._creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if Path(self.gmail_context.token).exists():
            self._creds = Credentials.from_authorized_user_file(self.gmail_context.token, self.gmail_context.scopes)
        # If there are no (valid) credentials available, let the user log in.
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.gmail_context.secret, self.gmail_context.scopes)
                self._creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.gmail_context.token, "w") as token:
                token.write(self._creds.to_json())

    def get_attachment_flow(self, source_account: Annotated[str, AfterValidator(email_validator)]) -> None:
        """
        One off to populate the boomkat directory. I sent
        an email with a bunch of boomkat messages attached as emls
        Read this email and pull the attachments
        """
        # Call the Gmail API
        service = build("gmail", "v1", credentials=self._creds)
        # Get my user profile and email
        profile = service.users().getProfile(userId="me").execute()
        userID = profile["emailAddress"]
        # Get the message api and list all messages from my main account()
        message_api = service.users().messages()
        messages = message_api.list(userId=userID, q=f"from:{source_account}").execute()

        current_attach = 0  # For appending to emailbody file names
        if len(messages["messages"]) > 0:
            for m in messages["messages"]:
                this_email = message_api.get(userId=userID, id=m["id"]).execute()
                for part in this_email["payload"]["parts"]:
                    # If any attachments in payload PendingDeprecationWarning
                    if "attachmentId" in part["body"]:
                        attach = (
                            message_api.attachments()
                            .get(
                                userId=userID,
                                messageId=m["id"],
                                id=part["body"]["attachmentId"],
                            )
                            .execute()
                        )
                        # attachment data is urlsafe base64 encoded
                        bytes_eml = base64.urlsafe_b64decode(
                            attach["data"]  # + ("=" * (-len(attach["data"]) % 4))
                        )

                        # We now have a set of bytes, decode them to eml
                        eml = email.message_from_bytes(bytes_eml, policy=policy.default)
                        date: str | None = eml.get("Date")
                        # Date has format like Fri, 19 Dec .... Split on , and get datetime string
                        date = date.split(",")[1][:-5].strip()
                        body: str = eml.get_body(preferencelist=("plain")).get_content()
                        date = datetime.strptime(date, "%d %b %Y %H:%M:%S")
                        email_for_agent = boom_email(date=date, body=body)
                        with open(self.email_dir / f"attach_{current_attach}.txt", "w") as f:
                            f.write(email_for_agent.model_dump_json(indent=2))
                        current_attach += 1

    def _get_email_body(self, payload: dict) -> str:
        """
        Recursively extract the plain text body from an email payload.
        Handles nested multipart emails.
        """
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                # If we find a plain text part with data, return it
                if part["mimeType"] == "text/plain" and "data" in part["body"]:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                # If it's a multipart container, recurse into it
                elif part["mimeType"].startswith("multipart/"):
                    body = self._get_email_body(part)
                    if body:
                        return body
        # Handle case where payload itself is text/plain (not multipart)
        elif payload.get("mimeType") == "text/plain" and "body" in payload and "data" in payload["body"]:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        return body

    def fetch_new_emails(self) -> None:
        """
        Fetch new/unread emails and save them to the email_dir.
        Emails are saved as JSON files with date and body content.
        Handles both direct emails and emails forwarded as .eml attachments.
        """
        from .classes import boom_email

        service = build("gmail", "v1", credentials=self._creds)
        profile = service.users().getProfile(userId="me").execute()
        userID = profile["emailAddress"]

        message_api = service.users().messages()
        # Query for unread messages
        messages = message_api.list(userId=userID, q="is:unread").execute()

        if "messages" not in messages or len(messages["messages"]) == 0:
            print("No new emails found")
            return

        # Find the highest existing file number to continue numbering
        existing_files = list(self.email_dir.glob("attach_*.txt"))
        current_attach = len(existing_files)

        for m in messages["messages"]:
            this_email = message_api.get(userId=userID, id=m["id"]).execute()

            found_attachments = False
            # Check for attachments first (e.g. forwarded emails as attachments)
            if "parts" in this_email["payload"]:
                for part in this_email["payload"]["parts"]:
                    # Check if it's an email attachment (usually .eml file or message/rfc822)
                    if (
                        "filename" in part and part["filename"].endswith(".eml") or part["mimeType"] == "message/rfc822"
                    ) and "attachmentId" in part["body"]:
                        found_attachments = True
                        attach = (
                            message_api.attachments()
                            .get(
                                userId=userID,
                                messageId=m["id"],
                                id=part["body"]["attachmentId"],
                                # Set a large maxBytes limit to prevent truncation
                                # Gmail API default can truncate at 25MB, but we increase to 50MB
                                maxBytes=52428800,  # 50MB in bytes
                            )
                            .execute()
                        )
                        # Attachment data is urlsafe base64 encoded
                        # Add padding if needed for proper base64 decoding
                        attachment_data = attach["data"]
                        padding_needed = (4 - len(attachment_data) % 4) % 4
                        if padding_needed:
                            attachment_data += "=" * padding_needed
                        bytes_eml = base64.urlsafe_b64decode(attachment_data)

                        # Parse .eml content
                        eml = email.message_from_bytes(bytes_eml, policy=policy.default)

                        # Extract date
                        date_val: str | None = eml.get("Date")
                        if date_val:
                            try:
                                # Format is usually like "Fri, 19 Dec 2024 10:00:39 +0000"
                                # We take the part between comma and timezone offset roughly
                                date_clean = date_val.split(",")[1][:-5].strip()
                                date = datetime.strptime(date_clean, "%d %b %Y %H:%M:%S")
                            except (ValueError, IndexError):
                                date = datetime.now()
                        else:
                            date = datetime.now()

                        # Extract body from the attached email
                        try:
                            body = eml.get_body(preferencelist=("plain"))
                            if body:
                                body_content = body.get_content()
                            else:
                                # Fallback if get_body fails to find plain text
                                body_content = ""
                                if eml.is_multipart():
                                    for sub_part in eml.walk():
                                        if sub_part.get_content_type() == "text/plain":
                                            body_content = sub_part.get_content()
                                            break
                                else:
                                    body_content = eml.get_payload(decode=True).decode("utf-8")
                        except Exception as e:
                            print(f"Error parsing body from attachment: {e}")
                            body_content = ""

                        # Save attached email content
                        if body_content:
                            email_for_agent = boom_email(date=date, body=body_content)
                            with open(self.email_dir / f"attach_{current_attach}.txt", "w") as f:
                                f.write(email_for_agent.model_dump_json(indent=2))
                            current_attach += 1

            # If no email attachments found, process the main email body
            if not found_attachments:
                # Extract date and body from email
                headers = this_email["payload"]["headers"]
                date_str = next((h["value"] for h in headers if h["name"] == "Date"), None)

                if date_str:
                    try:
                        date_str_clean = date_str.split(",")[1][:-5].strip()
                        date = datetime.strptime(date_str_clean, "%d %b %Y %H:%M:%S")
                    except (ValueError, IndexError):
                        date = datetime.now()
                else:
                    date = datetime.now()

                # Extract body using recursive helper
                body = self._get_email_body(this_email["payload"])

                if body:
                    # Save email to file
                    email_for_agent = boom_email(date=date, body=body)
                    with open(self.email_dir / f"attach_{current_attach}.txt", "w") as f:
                        f.write(email_for_agent.model_dump_json(indent=2))
                    current_attach += 1

            # Mark parent email as read
            message_api.modify(userId=userID, id=m["id"], body={"removeLabelIds": ["UNREAD"]}).execute()

        print(f"Successfully saved {current_attach - len(existing_files)} new emails")
