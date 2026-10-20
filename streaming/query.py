"""Run one read-only Spark SQL query against the lakehouse and print the result.

Run in the Spark image: `make query SQL="SELECT ... FROM lakehouse.bronze.recentchange"`.
Only reads are accepted (streaming/readonly.py). Examples: docs/DATA_MODEL.md.
"""

from __future__ import annotations

import sys

from streaming.config import LakehouseSettings
from streaming.readonly import is_read_only
from streaming.session import build_session

MAX_ROWS = 100
# Wide enough for most fields; a bronze value (a whole JSON event) is cut at this length.
MAX_COLUMN_WIDTH = 120
USAGE = 'usage: make query SQL="SELECT ... FROM lakehouse.bronze.recentchange"'


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(USAGE)
        sys.exit(2)
    sql = sys.argv[1]
    if not is_read_only(sql):
        print("refused: make query runs reads only (SELECT, WITH, SHOW, DESCRIBE, EXPLAIN)")
        sys.exit(2)
    spark = build_session("query", LakehouseSettings())
    spark.sql(sql).show(MAX_ROWS, truncate=MAX_COLUMN_WIDTH)
    spark.stop()


if __name__ == "__main__":
    main()
