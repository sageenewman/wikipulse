import pytest

from streaming.readonly import is_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM lakehouse.bronze.recentchange",
        "  select 1",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "SHOW TABLES IN lakehouse.bronze",
        "DESCRIBE lakehouse.bronze.recentchange",
        "EXPLAIN SELECT 1",
        "-- the busiest wikis\nSELECT 1",
        # Write keywords inside quoted text or comments are not statements.
        "SELECT * FROM t WHERE title = 'Drop table'",
        "SELECT `delete` FROM t",
        "SELECT 1 /* not a DELETE */",
    ],
)
def test_reads_are_allowed(sql: str) -> None:
    assert is_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE lakehouse.bronze.recentchange",
        "DELETE FROM lakehouse.bronze.recentchange WHERE kafka_offset < 10",
        "INSERT INTO lakehouse.bronze.recentchange SELECT * FROM t",
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE",
        "CALL lakehouse.system.expire_snapshots('bronze.recentchange')",
        "CREATE TABLE x (id INT)",
        "ALTER TABLE t ADD COLUMN c INT",
        "TRUNCATE TABLE t",
        # A read keyword first does not make a write harmless.
        "WITH t AS (SELECT 1) INSERT INTO x SELECT * FROM t",
        "SELECT 1; DROP TABLE t",
        "",
        "   ",
        "-- only a comment",
    ],
)
def test_writes_and_empty_statements_are_refused(sql: str) -> None:
    assert not is_read_only(sql)
