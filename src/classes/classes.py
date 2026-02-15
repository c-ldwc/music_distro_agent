from datetime import datetime
from typing import Any

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

# T = TypeVar("T")
from ..helpers import retry


class boom_email(BaseModel):
    date: datetime
    body: str


class album(BaseModel):
    artists: list[str]
    title: str
    id: str


class extract_release(BaseModel):
    artist: list[str]
    album: str


class playlist(BaseModel):
    releases: list[album]
    title: str


class track(BaseModel):
    artist: str
    album: str
    track_id: str


class playlist_library(BaseModel):
    playlists: list[playlist] = []

    def add_playlist(self, playlist: playlist) -> None:
        self.playlists.append(playlist)


class Agent[T](BaseModel):
    model_name: str = "claude-haiku-4-5-20251001"
    api_key: str
    model: Any = None
    prompt: str
    response_format: dict[str, Any] | None = None
    temperature: float = 0.0  # Deterministic by default
    max_tokens: int = 4096  # Control output length

    def model_post_init(self, context: Any, /) -> None:  # noqa: ARG002
        self.model = ChatAnthropic(
            model_name=self.model_name,
            api_key=self.api_key,
            response_format=self.response_format,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def run(self, **kwargs) -> T | None:
        return retry(method=self._run, args=kwargs, retries=3)

    # Todo
    def _run(self, **kwargs) -> T:
        pass
