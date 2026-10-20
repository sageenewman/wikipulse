"""Service configuration, read from environment variables (and `.env` in development)."""

from dataclasses import dataclass
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Topics:
    """Where one source of messages is written: valid events and dead letters."""

    raw: str
    dlq: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:19092"
    raw_topic: str = "wiki.raw"
    dlq_topic: str = "wiki.dlq"
    # A replay writes here, never to the live topics. The live producer finds its
    # resume position in the newest message of the live topics, so it must be
    # their only writer (ADR-0008).
    replay_raw_topic: str = "wiki.replay"
    replay_dlq_topic: str = "wiki.replay.dlq"

    stream_url: str = "https://stream.wikimedia.org/v2/stream/recentchange"
    # Wikimedia asks every client to identify itself with contact information.
    user_agent: str = "wikipulse/0.1 (https://github.com/sageenewman/wikipulse)"

    # No data for this long means the connection is dead, even if the socket is open.
    stream_read_timeout_seconds: float = 60.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0

    # On startup, continue from the position of the last message written to Kafka.
    # When false, or when the topics are empty, start from the live edge.
    resume_on_start: bool = True

    stats_interval_seconds: float = 30.0
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _replay_topics_are_not_live_topics(self) -> Self:
        shared = {self.replay_raw_topic, self.replay_dlq_topic} & {self.raw_topic, self.dlq_topic}
        if shared:
            raise ValueError(
                f"replay topics must differ from the live topics, but both use {sorted(shared)}"
            )
        return self

    @property
    def live_topics(self) -> Topics:
        return Topics(raw=self.raw_topic, dlq=self.dlq_topic)

    @property
    def replay_topics(self) -> Topics:
        return Topics(raw=self.replay_raw_topic, dlq=self.replay_dlq_topic)
