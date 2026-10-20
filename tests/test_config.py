from pathlib import Path

import pytest
from pydantic import ValidationError

from ingestion.config import Settings, Topics


@pytest.fixture(autouse=True)
def no_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads `.env` from the working directory. Keep a developer's file out."""
    monkeypatch.chdir(tmp_path)


def test_live_and_replay_topics_are_separate_by_default() -> None:
    config = Settings()

    assert config.live_topics == Topics(raw="wiki.raw", dlq="wiki.dlq")
    assert config.replay_topics == Topics(raw="wiki.replay", dlq="wiki.replay.dlq")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("REPLAY_RAW_TOPIC", "wiki.raw"),
        ("REPLAY_DLQ_TOPIC", "wiki.dlq"),
        ("REPLAY_RAW_TOPIC", "wiki.dlq"),
        ("RAW_TOPIC", "wiki.replay"),
    ],
)
def test_a_replay_topic_that_is_also_a_live_topic_is_rejected(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    """Otherwise a replay would write where the live producer looks for its resume point."""
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError, match="replay topics must differ"):
        Settings()
