from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pathlib import Path

import base64
import email
from email import policy
from datetime import datetime
from re import match, sub
from pydantic import BaseModel, AfterValidator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated


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


def process_env_list(l: str) -> list[str]:
    print(l)
    # Format a string that represents a list into a list of strings
    # i.e. "[a,b,something_else]" -> ["a", "b", "something_else"]
    return [sub(r"[\s\[\]]", "", i) for i in l.split(",")]


class settings(BaseSettings):
    GMAIL_SECRET_PATH: str
    GMAIL_MAIN_ACCOUNT: str
    GMAIL_SCOPES: list[str]
    email_path: Path
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class boom_email(BaseModel):
    date: datetime
    body: str


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
        print(
            f"Authorising gmail with scope {self.gmail_context.scopes} of type {type(self.gmail_context.scopes)}"
        )
        self._creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if Path(self.gmail_context.token).exists():
            self._creds = Credentials.from_authorized_user_file(
                self.gmail_context.token, self.gmail_context.scopes
            )
        # If there are no (valid) credentials available, let the user log in.
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "gmail-secret.json", self.gmail_context.scopes
                )
                self._creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.gmail_context.token, "w") as token:
                token.write(self._creds.to_json())

    def get_attachment_flow(
        self, source_account: Annotated[str, AfterValidator(email_validator)]
    ) -> None:
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
                        with open(
                            self.email_dir / f"attach_{current_attach}.txt", "w"
                        ) as f:
                            f.write(email_for_agent.model_dump_json(indent=2))
                        current_attach += 1
