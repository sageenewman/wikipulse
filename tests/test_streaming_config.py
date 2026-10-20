import pytest
from pydantic import ValidationError

from streaming.config import LIVE_BRONZE_TABLE, LIVE_TOPIC, BronzeSettings


def test_defaults_read_the_live_topic_into_the_live_table() -> None:
    settings = BronzeSettings()
    assert settings.bronze_source_topic == LIVE_TOPIC
    assert settings.bronze_table == LIVE_BRONZE_TABLE


def test_another_topic_cannot_write_to_the_live_table() -> None:
    with pytest.raises(ValidationError, match="only wiki.raw may be written"):
        BronzeSettings(bronze_source_topic="wiki.replay")


def test_another_topic_can_write_to_its_own_table() -> None:
    settings = BronzeSettings(
        bronze_source_topic="wiki.replay", bronze_table="lakehouse.bronze_replay.recentchange"
    )
    assert settings.bronze_table == "lakehouse.bronze_replay.recentchange"


def test_each_table_gets_its_own_checkpoint() -> None:
    live = BronzeSettings()
    replay = BronzeSettings(
        bronze_source_topic="wiki.replay", bronze_table="lakehouse.bronze_replay.recentchange"
    )
    assert live.checkpoint_dir != replay.checkpoint_dir
    assert live.checkpoint_dir == "/checkpoints/lakehouse.bronze.recentchange"


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRONZE_TRIGGER_SECONDS", "10")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
    settings = BronzeSettings()
    assert settings.bronze_trigger_seconds == 10
    assert settings.kafka_bootstrap_servers == "broker:9092"
