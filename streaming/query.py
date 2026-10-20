"""Run one Spark SQL query against the lakehouse and print the result.

Run in the Spark image: `make query SQL="SELECT ... FROM lakehouse.bronze.recentchange"`.
Examples: docs/DATA_MODEL.md.
"""

from __future__ import annotations

import sys

from streaming.config import LakehouseSettings
from streaming.session import build_session

MAX_ROWS = 100
# Wide enough for most fields; a bronze value (a whole JSON event) is cut at this length.
MAX_COLUMN_WIDTH = 120


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print('usage: make query SQL="SELECT ... FROM lakehouse.bronze.recentchange"')
        sys.exit(2)
    spark = build_session("query", LakehouseSettings())
    spark.sparkContext.setLogLevel("ERROR")
    spark.sql(sys.argv[1]).show(MAX_ROWS, truncate=MAX_COLUMN_WIDTH)
    spark.stop()


if __name__ == "__main__":
    main()
