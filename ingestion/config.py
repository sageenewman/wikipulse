"""Service configuration, read from environment variables (and `.env` in development)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:19092"
    raw_topic: str = "wiki.raw"
    dlq_topic: str = "wiki.dlq"

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
